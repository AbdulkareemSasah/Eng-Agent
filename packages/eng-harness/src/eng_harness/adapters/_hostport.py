"""HostPort file and instance methods (plan 0002 T10; spec 0002 sections 4.4.2, 4.5.8, 4.5.9)."""

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from eng_contract.envelope import Envelope, HostInfo
from eng_contract.errors import ContractError, ContractWarning, ErrorCode, Precondition, WarningCode
from eng_contract.ids import Clock, IdSource, Timestamp
from eng_contract.store import ModelStateStore

from eng_harness.adapters._identity import IdentityStore
from eng_harness.adapters.csi import products
from eng_harness.adapters.csi._checks import ReadBack, check_envelope, issues_of, snapshot
from eng_harness.adapters.csi._session_ops import CsiSession, OpenedInstance
from eng_harness.adapters.csi._state import CsiStateReader, StateRead
from eng_harness.ports import HostInstance, HostLease, HostModelState, SavedModel, ServerCheck, UnitsState
from eng_harness.servers._guard import ProcessGuard, StartedInstance
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity, ProcessInspector
from eng_harness.servers._session import ServerManager


class AdapterHostPort:
    def __init__(
        self, *, identity: IdentityStore, sessions: ServerManager, guard: ProcessGuard, inspector: ProcessInspector,
        locks: HostLocks, clock: Clock, ids: IdSource, run_dir: Path, product: str, program: str, exe_name: str,
        files: Mapping[str, Path], server: str = "csi", host_key: str = "csi", states: ModelStateStore | None = None,
        readback: ReadBack | None = None,
    ) -> None:  # fmt: skip
        self._identity, self._clock, self._ids, self._sessions, self._locks = identity, clock, ids, sessions, locks
        self._run_dir, self._program, self._host_key = run_dir, program, host_key
        self._product, self._profile, self._readback = product, products.profile(product), readback
        self._files = {key: path.resolve() for key, path in files.items()}
        self._models: dict[str, str] = {}
        self._bound: dict[str, str] = {}
        self._instances: dict[str, OpenedInstance] = {}
        self._units: dict[str, str] = {}
        self._states = states  # without it an outside edit of the model in memory (4.6.4) cannot raise the revision
        self._reads: dict[str, StateRead] = {}
        self._written: set[str] = set()
        self._warnings: list[tuple[str, WarningCode]] = []
        self._session = CsiSession(
            sessions, guard, inspector, locks, ids, server=server, product=product, program=program, exe_name=exe_name
        )
        self._reader = CsiStateReader(product=product, call=self._session._call)  # B-451: no public read on CsiSession
        self._load(files)

    async def preflight(self, min_builds: Mapping[str, str]) -> list[ServerCheck]:
        return await self._sessions.preflight(min_builds)

    def session_epoch(self, host_key: str) -> int:
        return self._sessions.session_epoch(host_key)

    async def acquire(self, host_key: str) -> HostLease:
        """Lease the host: lock again each live instance of the run state (`HOST_LOCKED` when held elsewhere)."""
        if host_key == self._host_key:
            for opened in self._instances.values():
                if self._session.alive(opened):
                    self._locks.acquire(self._program, ProcessIdentity(opened.pid, opened.started_at, opened.exe_name))
        return HostLease(host_key=host_key, lease_id=self._ids.new_ulid())

    async def release(self, lease: HostLease) -> None:
        self._locks.release_all()

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
        fingerprint = (await self._reader.read(opened.pid, path)).fingerprint  # B-451 L3: the saved state's own
        s = self._identity.record_save(self._models[model_key], path, fingerprint)
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

    async def model_state(self, model_key: str, instance_id: str) -> HostModelState:
        """The state of the model in `instance_id` (spec 4.6.4); `loaded` false when it is absent from that instance.

        A fingerprint that changed with no `wrote` mark since the last read, or a file saved outside, is an outside
        edit: the revision rises and `take_warnings` gives `MODEL_CHANGED_OUTSIDE`.
        """
        held = await self.locate(model_key)
        if held is None or held.instance_id != instance_id:
            return HostModelState(loaded=False)
        path, opened = self._held(model_key)
        read = await self._reader.read(opened.pid, path)
        resolved = self._identity.resolve(path)
        revision, outside = resolved.revision, bool(resolved.warnings)
        previous = self._reads.get(model_key)
        marked = model_key in self._written
        self._written.discard(model_key)
        if previous is not None and previous.fingerprint != read.fingerprint and not (marked or outside):
            outside = True
            if self._states is not None:  # the unsaved state is a new revision with no file hash
                revision = self._states.increment(resolved.model_id, revision, read.fingerprint, None).revision
        if outside:
            self._warnings.append((model_key, WarningCode.MODEL_CHANGED_OUTSIDE))
        self._reads[model_key] = read
        return HostModelState(
            loaded=True, model_id=resolved.model_id, revision=revision, fingerprint=read.fingerprint,
            file_sha256=_file_sha256(path),
        )  # fmt: skip

    async def check_model(self, model_key: str) -> Envelope:
        """The `issues.model_check/1` of `model_key` (spec 4.5.8): the items written since the last check read back.

        The envelope carries the `MODEL_CHANGED_OUTSIDE` warnings of `take_warnings` (OQ-Q67). `ContractError`:
        `PRECONDITION_FAILED` (`model_open`), `INTERNAL` without `readback`, and the state reader's errors.
        """
        if self._readback is None:
            raise ContractError(ErrorCode.INTERNAL, "no read-back wiring", incident_id=self._ids.new_ulid())
        path, opened = self._held(model_key)
        started, began = self._clock.now(), self._clock.now_ms()
        read = await self._reader.read(opened.pid, path)
        target = {"target": {"product": self._product, "pid": opened.pid}}
        snap = await snapshot(self._reader._rows, target, read, self._profile)  # B-451: the reader's validated read
        issues = issues_of(self._readback, model_key, snap)
        resolved = self._identity.resolve(path)
        host = HostInfo(
            program=self._program, version=read.status.program_version, model_id=resolved.model_id,
            model_revision=resolved.revision,
        )  # fmt: skip
        outside = [
            ContractWarning(code=code, message=f"{key} changed outside the harness since the last read")
            for key, code in self.take_warnings()
        ]
        envelope = check_envelope(self._readback, issues, outside, host, started, self._clock.now_ms() - began)
        self._readback.written.clear(model_key)  # only now: a failed store leaves the items to the next check
        return envelope

    def last_read(self, model_key: str) -> StateRead | None:
        """The payloads, status and fingerprint of the last `model_state` of `model_key`, or `None`."""
        return self._reads.get(model_key)

    def wrote(self, model_key: str) -> None:
        """Mark an adapter write: the next fingerprint change of `model_key` is the adapter's, not an outside edit."""
        self._written.add(model_key)

    def reopened(self, model_key: str, path: Path) -> None:
        """Bind `model_key` to `path`, the file the bound instance now has open (spec 0007 4.10: `csi_open_revision`).

        The binding keeps its model id and the file is recorded as its next revision (spec 0007 Q16 is open). The last
        state read is dropped, so the next `model_state` is a new baseline. `ContractError` `NOT_FOUND`: no such key.
        """
        self._file(model_key)
        resolved = path.resolve()
        self._files[model_key] = resolved
        self._identity.record_save(self._models[model_key], resolved)
        self._reads.pop(model_key, None)
        self._written.discard(model_key)
        self._persist()

    def take_warnings(self) -> list[tuple[str, WarningCode]]:
        """The `MODEL_CHANGED_OUTSIDE` warnings (model key, code) noted by `model_state` since the last call."""
        taken, self._warnings = self._warnings, []
        return taken

    async def read_units(self, model_key: str, instance_id: str) -> UnitsState:
        """The present units against those recorded at open (spec 4.5.4); never raises for a model that is absent."""
        expected = self._units.get(model_key, "")
        held = await self.locate(model_key)
        if held is None or held.instance_id != instance_id:
            return UnitsState(loaded=False, ok=True, present=None, expected=expected)
        present = await self._session.units(self._held(model_key)[1])
        return UnitsState(loaded=True, ok=present == expected, present=present, expected=expected)

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
        self._reads.pop(model_key, None)  # a reopened file starts a new baseline for outside-edit detection
        self._written.discard(model_key)
        self._bound[model_key] = opened.instance_id
        self._instances[opened.instance_id] = opened

    def _host(self, opened: OpenedInstance) -> HostInstance:
        at = opened.observed_at
        return HostInstance(
            instance_id=opened.instance_id, pid=opened.pid, process_started_at=at, program=self._program
        )

    def _load(self, files: Mapping[str, Path]) -> None:
        """Take the run state of an earlier port as a cache (spec 4.5.9; the journal wins); instances get session -1."""
        path = self._run_dir / "adapter" / "state.json"
        if not path.is_file():
            return
        saved = json.loads(path.read_text(encoding="utf-8"))
        for r in saved["instances"]:
            opened = OpenedInstance(
                r["instance_id"],
                r["pid"],
                r["started_at"],
                Timestamp(r["observed_at"]),
                r["exe_name"],
                -1,
                r["visible"],
            )
            self._instances[opened.instance_id] = opened
        for key, b in saved["bindings"].items():
            self._bound[key], self._models[key] = b["instance_id"], b["model_id"]
            self._files.setdefault(key, Path(b["file"]))
        self._units.update(saved["expected_units"])
        self._files.update({key: path.resolve() for key, path in files.items()})  # the constructor's files win

    def _persist(self) -> None:
        path = self._run_dir / "adapter" / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "instance_id": i.instance_id, "pid": i.pid, "visible": i.visible, "started_at": i.started_at,
                "observed_at": i.observed_at, "exe_name": i.exe_name,
            }
            for i in self._instances.values()
        ]  # fmt: skip
        bound: dict[str, dict[str, str]] = {}
        for key in self._bound:
            bound[key] = {"instance_id": self._bound[key], "model_id": self._models[key], "file": str(self._files[key])}
        body = json.dumps({"expected_units": self._units, "instances": rows, "bindings": bound})
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(body, encoding="utf-8")
        os.replace(temporary, path)


def _file_sha256(path: Path) -> str:
    with path.open("rb") as handle:  # in chunks: a model file is not loaded whole into memory
        return hashlib.file_digest(handle, "sha256").hexdigest()


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
