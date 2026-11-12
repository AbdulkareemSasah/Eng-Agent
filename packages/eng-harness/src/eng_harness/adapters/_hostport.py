"""HostPort file and instance methods (plan 0002 T10; spec 0002 sections 4.4.2, 4.5.8, 4.5.9)."""

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.ids import Clock, IdSource

from eng_harness.adapters._identity import IdentityStore
from eng_harness.adapters.csi._session_ops import CsiSession, OpenedInstance
from eng_harness.ports import HostInstance, SavedModel
from eng_harness.servers._guard import ProcessGuard, StartedInstance
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessInspector
from eng_harness.servers._session import ServerManager


class AdapterHostPort:
    def __init__(
        self, *, identity: IdentityStore, sessions: ServerManager, guard: ProcessGuard, inspector: ProcessInspector,
        locks: HostLocks, clock: Clock, ids: IdSource, run_dir: Path, product: str, program: str, exe_name: str,
        files: Mapping[str, Path], server: str = "csi", host_key: str = "csi",
    ) -> None:  # fmt: skip
        self._identity, self._clock, self._ids = identity, clock, ids
        self._run_dir, self._program, self._host_key = run_dir, program, host_key
        self._files = {key: path.resolve() for key, path in files.items()}
        self._models: dict[str, str] = {}
        self._bound: dict[str, str] = {}
        self._instances: dict[str, OpenedInstance] = {}
        self._units: dict[str, str] = {}
        self._session = CsiSession(
            sessions, guard, inspector, locks, ids, server=server, product=product, program=program, exe_name=exe_name
        )

    async def working_copy(self, model_key: str, folder: Path) -> str:
        source = self._file(model_key)
        self._identity.resolve(source)
        dest = _copied(source, folder)
        copy_key = f"{model_key}@copy"
        opened = await self._session.open_file(dest, self._reusable(), self._clock.now())
        self._keep(copy_key, dest, self._identity.resolve(dest).model_id, opened)
        self._units[copy_key] = await self._session.units(opened)
        self._persist()
        return copy_key

    async def save(self, model_key: str, role: str) -> SavedModel:
        path, opened = self._held(model_key)
        await self._session.save(path, opened)
        s = self._identity.record_save(self._models[model_key], path)
        digest = s.file_sha256
        if digest is None:
            raise ContractError(ErrorCode.INTERNAL, "the save recorded no file hash", incident_id=self._ids.new_ulid())
        fp, name = s.fingerprint or "", path.name
        return SavedModel(model_id=s.model_id, revision=s.revision, fingerprint=fp, file_sha256=digest, file_name=name)

    async def restore(self, model_key: str, saved: SavedModel) -> HostInstance:
        path = self._file(model_key)
        if hashlib.sha256(path.read_bytes()).hexdigest() != saved.file_sha256:
            raise ContractError(ErrorCode.CONFLICT, "the saved file's hash differs from the record")
        opened = await self._session.open_file(path, self._bound_instance(model_key), self._clock.now())
        self._keep(model_key, path, saved.model_id, opened)
        self._units[model_key] = await self._session.units(opened)
        self._persist()
        return self._host(opened)

    async def locate(self, model_key: str) -> HostInstance | None:
        opened = self._bound_instance(model_key)
        if opened is None or not self._session.alive(opened):
            return None
        reported = await self._session.model_path(opened)
        if reported is None or reported.resolve() != self._files.get(model_key):
            return None
        return self._host(opened)

    def model_files(self, model_key: str) -> tuple[Path, ...]:
        return (self._file(model_key),)

    async def started_instances(self, host_key: str) -> list[HostInstance]:
        if host_key != self._host_key:
            return []
        return [self._host(item) for item in self._instances.values()]

    async def close_started(self, host_key: str, instances: Sequence[HostInstance]) -> None:
        if host_key != self._host_key:
            return
        started: list[StartedInstance] = []
        for item in instances:
            opened = self._instances.get(item.instance_id)
            if opened is not None and opened.pid == item.pid:
                started.append(StartedInstance(opened.pid, opened.started_at, opened.exe_name, opened.visible))
        await self._session.close(started)

    def _reusable(self) -> OpenedInstance | None:
        return next((i for i in self._instances.values() if self._session.owns(i) and self._session.alive(i)), None)

    def _file(self, model_key: str) -> Path:
        try:
            return self._files[model_key]
        except KeyError:
            raise ContractError(ErrorCode.NOT_FOUND, f"no file is bound for {model_key}", received=model_key) from None

    def _bound_instance(self, model_key: str) -> OpenedInstance | None:
        return self._instances.get(self._bound.get(model_key, ""))

    def _held(self, model_key: str) -> tuple[Path, OpenedInstance]:
        opened = self._bound_instance(model_key)
        if opened is None:
            raise ContractError(ErrorCode.PRECONDITION_FAILED, "not open", precondition=Precondition.model_open)
        return self._file(model_key), opened

    def _keep(self, model_key: str, path: Path, model_id: str, opened: OpenedInstance) -> None:
        self._files[model_key], self._models[model_key] = path, model_id
        self._bound[model_key] = opened.instance_id
        self._instances[opened.instance_id] = opened

    def _host(self, opened: OpenedInstance) -> HostInstance:
        at = opened.observed_at
        return HostInstance(
            instance_id=opened.instance_id, pid=opened.pid, process_started_at=at, program=self._program
        )

    def _persist(self) -> None:
        path = self._run_dir / "adapter" / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = [{"instance_id": i.instance_id, "pid": i.pid, "visible": i.visible} for i in self._instances.values()]
        bound: dict[str, dict[str, str]] = {}
        for key in self._bound:
            bound[key] = {"instance_id": self._bound[key], "model_id": self._models[key], "file": str(self._files[key])}
        body = json.dumps({"expected_units": self._units, "instances": rows, "bindings": bound})
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(body, encoding="utf-8")
        os.replace(temporary, path)


def _copied(source: Path, folder: Path) -> Path:
    data = source.read_bytes()
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / source.name
    if dest.exists():
        raise ContractError(ErrorCode.CONFLICT, "the working copy already exists")
    dest.write_bytes(data)
    if hashlib.sha256(dest.read_bytes()).hexdigest() != hashlib.sha256(data).hexdigest():
        dest.unlink()
        raise ContractError(ErrorCode.CONFLICT, "the copy's hash differs from the original")
    return dest.resolve()
