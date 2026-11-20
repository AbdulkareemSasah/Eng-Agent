"""IDEA HostPort session operations (plan 0014 T6/T7; spec 0014 AC4, AC5, AC10, section 4.10).

Purpose: working-copy hashes and lineage, path guards inside the run folder, route preconditions, and the HostPort
methods that do not launch IDEA or the REST service (`started_instances` is empty). Acquire keys the lock as
`idea:<hash of service_url>` (route rest) or `idea:<hash of working copy path>` (route native). After a successful
`set_loads` write, rebind the model key to `out_path` (new revision and hash; old file kept) and keep the last write's
requested/got/dropped_zero/tolerance/connection/load-map status so `check_model` returns the §4.10 integrity set.
Units: none for paths; `read_units` returns the fixed declaration of section 4.6. Errors: `ContractError`
`HOST_NOT_CONNECTED`, `INVALID_ARGUMENT`, `CONFLICT`, `NOT_FOUND`, `PRECONDITION_FAILED`, `INTERNAL`.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eng_contract.envelope import Envelope, HostInfo, Provenance, make_success
from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.ids import Clock, IdSource, Timestamp
from eng_contract.issues import CheckModelSummary, ModelIssue, Severity
from eng_contract.kinds.issues import ModelCheck
from eng_contract.refs import RecordSource
from eng_contract.store import ResultStore

from eng_harness.adapters._identity import IdentityStore
from eng_harness.adapters.idea._replies import parse_status
from eng_harness.kinds.idea import IdeaStatus
from eng_harness.ports import HostInstance, HostLease, HostModelState, SavedModel, ServerCheck, UnitsState
from eng_harness.servers import CallEffect, ServerManager
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity
from eng_harness.servers._session import reply_body

__all__ = [
    "IdeaHostPort",
    "new_out_path",
    "require_inside_run",
]


@dataclass(frozen=True, slots=True)
class _LoadsIntegrity:
    """Last `set_loads` inputs kept for `check_model` (spec 0014 section 4.10)."""

    requested: tuple[Mapping[str, Any], ...]
    got: tuple[Mapping[str, Any], ...] | None
    dropped_zero: tuple[str, ...]
    tolerance_ratio: float | None
    connection: str
    load_map_status: str


_PROGRAM = "idea"
_IDEA_CON = ".ideaCon"
_UNITS = "N,N.m"  # fixed declaration of spec 0014 section 4.6; IDEA has no unit state to restore


def require_inside_run(path: Path, run_dir: Path) -> Path:
    """Return `path` resolved when it lies under `run_dir`; else `INVALID_ARGUMENT` (`path`)."""
    resolved = path.resolve()
    root = run_dir.resolve()
    if resolved != root and not resolved.is_relative_to(root):
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT,
            "path must lie inside the run folder",
            field="path",
            received=str(path),
        )
    return resolved


def new_out_path(path: Path, run_dir: Path) -> Path:
    """A new `.ideaCon` path under `run_dir`, distinct from `path` (spec 0014 AC4)."""
    require_inside_run(path, run_dir)
    root = run_dir.resolve()
    stem = path.stem or "model"
    candidate = root / f"{stem}.out{_IDEA_CON}"
    if candidate.resolve() == path.resolve() or candidate.exists():
        digest = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:12]
        candidate = root / f"{stem}.{digest}.out{_IDEA_CON}"
    if candidate.resolve() == path.resolve():
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT,
            "out_path must be a new file distinct from path",
            field="out_path",
        )
    return candidate


def _file_sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _copied(source: Path, folder: Path) -> Path:
    data = source.read_bytes()
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / source.name
    if dest.exists():
        raise ContractError(ErrorCode.CONFLICT, "the working copy already exists")
    dest.write_bytes(data)
    if _file_sha256(dest) != hashlib.sha256(data).hexdigest():
        dest.unlink()
        raise ContractError(ErrorCode.CONFLICT, "the copy's hash differs from the original")
    return dest.resolve()


def _lock_identity(key: str) -> ProcessIdentity:
    """Synthetic identity for the IDEA lock key `idea:<hash>` (spec 0014 section 4.10)."""
    digest = hashlib.sha256(key.encode()).hexdigest()
    pid = (int(digest[:8], 16) % (2**31 - 2)) + 1
    return ProcessIdentity(pid, digest[:16], "idea-lock")


class IdeaHostPort:
    """HostPort for IDEA: file working copies and route preconditions; the harness never starts IDEA."""

    def __init__(
        self,
        *,
        identity: IdentityStore,
        sessions: ServerManager,
        locks: HostLocks,
        clock: Clock,
        ids: IdSource,
        run_dir: Path,
        files: Mapping[str, Path],
        store: ResultStore | None = None,
        server: str = "idea",
        host_key: str = "idea",
        route: str,
        service_url: str | None = None,
    ) -> None:
        if route not in ("native", "rest"):
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "route must be native or rest", field="route")
        if route == "rest" and not service_url:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, "service_url is required for route rest", field="service_url"
            )
        self._identity = identity
        self._sessions = sessions
        self._locks = locks
        self._clock = clock
        self._ids = ids
        self._run_dir = run_dir.resolve()
        self._store = store
        self._server = server
        self._host_key = host_key
        self._route = route
        self._service_url = service_url
        self._files = {key: path.resolve() for key, path in files.items()}
        self._models: dict[str, str] = {}
        self._bound: dict[str, str] = {}
        self._instances: dict[str, HostInstance] = {}
        self._hashes: dict[str, str] = {}  # journaled file sha256 per model key
        self._loads_integrity: dict[str, _LoadsIntegrity] = {}

    @property
    def identity_store(self) -> IdentityStore:
        """The identity store used for `derived_from` lineage (ADR-0032)."""
        return self._identity

    async def preflight(self, min_builds: Mapping[str, str]) -> list[ServerCheck]:
        return await self._sessions.preflight(min_builds)

    def session_epoch(self, host_key: str) -> int:
        return self._sessions.session_epoch(host_key)

    async def acquire(self, host_key: str) -> HostLease:
        """Lease the IDEA lock key of section 4.10 (`HOST_LOCKED` when held elsewhere)."""
        if host_key == self._host_key:
            self._locks.acquire(_PROGRAM, _lock_identity(self._lock_key()))
        return HostLease(host_key=host_key, lease_id=self._ids.new_ulid())

    async def release(self, lease: HostLease) -> None:
        self._locks.release_all()

    async def working_copy(self, model_key: str, folder: Path) -> str:
        """Copy the model into `folder` without launching a host (spec 0014 AC4, section 4.10)."""
        source = self._file(model_key)
        self._identity.resolve(source)
        dest = _copied(source, folder)
        require_inside_run(dest, self._run_dir)
        copy_key = f"{model_key}@copy"
        resolved = self._identity.resolve(dest)
        instance = self._bind_file(copy_key, dest, resolved.model_id)
        self._hashes[copy_key] = _file_sha256(dest)
        self._instances[instance.instance_id] = instance
        return copy_key

    async def ensure_route_ready(self, model_key: str) -> None:
        """Raise `HOST_NOT_CONNECTED` when the route's preconditions of AC5 are missing."""
        path = self._file(model_key)
        if self._route == "native":
            await self._ensure_native(path)
            return
        await self._ensure_rest(path)

    async def locate(self, model_key: str) -> HostInstance | None:
        """Bound file on route native when the hash matches; open project on route rest when paths match."""
        instance_id = self._bound.get(model_key)
        if instance_id is None:
            return None
        path = self._files.get(model_key)
        if path is None or not path.is_file():
            return None
        digest = _file_sha256(path)
        if digest != self._hashes.get(model_key):
            return None
        if self._route == "rest" and not await self._rest_path_matches(path):
            return None
        return self._instances.get(instance_id)

    async def model_state(self, model_key: str, instance_id: str) -> HostModelState:
        held = await self.locate(model_key)
        if held is None or held.instance_id != instance_id:
            return HostModelState(loaded=False)
        path = self._file(model_key)
        resolved = self._identity.resolve(path)
        return HostModelState(
            loaded=True,
            model_id=resolved.model_id,
            revision=resolved.revision,
            fingerprint=self._hashes.get(model_key, ""),
            file_sha256=_file_sha256(path),
        )

    def remember_set_loads(
        self,
        model_key: str,
        *,
        requested: Sequence[Mapping[str, Any]],
        got: Sequence[Mapping[str, Any]] | None,
        dropped_zero: Sequence[str],
        tolerance_ratio: float | None,
        connection: str,
        load_map_status: str,
    ) -> None:
        """Keep the last `set_loads` requested/got/dropped_zero/tolerance/connection/map status for `check_model`."""
        self._loads_integrity[model_key] = _LoadsIntegrity(
            requested=tuple(dict(item) for item in requested),
            got=None if got is None else tuple(dict(item) for item in got),
            dropped_zero=tuple(str(name) for name in dropped_zero if name),
            tolerance_ratio=tolerance_ratio,
            connection=connection,
            load_map_status=load_map_status,
        )

    def rebind_to_out_path(self, model_key: str, out_path: Path) -> None:
        """AC10: rebind `model_key` to `out_path` (new revision, new hash); the previous file is kept on disk."""
        resolved = require_inside_run(out_path, self._run_dir)
        if not resolved.is_file():
            raise ContractError(ErrorCode.NOT_FOUND, "out_path does not exist", received=str(out_path))
        model_id = self._models.get(model_key)
        if model_id is None or model_key not in self._bound:
            raise ContractError(ErrorCode.PRECONDITION_FAILED, "not open", precondition=Precondition.model_open)
        digest = _file_sha256(resolved)
        state = self._identity.record_save(model_id, resolved, fingerprint=digest)
        instance = self._bind_file(model_key, resolved, state.model_id)
        self._hashes[model_key] = digest
        self._instances[instance.instance_id] = instance

    async def set_loads(
        self,
        model_key: str,
        *,
        plan: Any,
        load_map: Any,
        source: RecordSource,
        readback_relative_tolerance_ratio: float,
        approved: bool,
        role: str = "main",
    ) -> Any:
        """Write loads through `_loads.set_loads`, remember integrity inputs, rebind to `out_path` (AC10)."""
        from eng_harness.adapters.idea import _loads as loads

        path = self._file(model_key)
        if model_key not in self._bound:
            raise ContractError(ErrorCode.PRECONDITION_FAILED, "not open", precondition=Precondition.model_open)

        bound_id = self._models[model_key]

        def current_revision(model_id: str) -> int | None:
            if model_id != bound_id:
                return None
            return self._identity.resolve(path).revision

        # Ensure the plan path matches the bound working copy (caller may have built it from model_files).
        if Path(plan.path).resolve() != path.resolve():
            plan = plan.model_copy(update={"path": str(path)})
        result = await loads.set_loads(
            sessions=self._sessions,
            server=self._server,
            role=role,
            plan=plan,
            load_map=load_map,
            source=source,
            current_revision=current_revision,
            run_dir=self._run_dir,
            readback_relative_tolerance_ratio=readback_relative_tolerance_ratio,
            approved=approved,
            ids=self._ids,
        )
        self.remember_set_loads(
            model_key,
            requested=result.requested,
            got=result.read_back,
            dropped_zero=result.dropped_zero,
            tolerance_ratio=readback_relative_tolerance_ratio,
            connection=plan.connection,
            load_map_status=load_map.status,
        )
        self.rebind_to_out_path(model_key, result.out_path)
        return result

    async def check_model(self, model_key: str) -> Envelope:
        """Return `issues.model_check/1` from the last `set_loads` integrity set (spec 0014 section 4.10)."""
        from eng_harness.adapters.idea import _checks as checks
        from eng_harness.adapters.idea._loads import LoadMap

        if self._store is None:
            raise ContractError(ErrorCode.INTERNAL, "no result store for check_model", incident_id=self._ids.new_ulid())
        path = self._file(model_key)
        if model_key not in self._bound:
            raise ContractError(ErrorCode.PRECONDITION_FAILED, "not open", precondition=Precondition.model_open)
        started = self._clock.now()
        began = self._clock.now_ms()
        issues: list[ModelIssue] = []
        held = self._loads_integrity.get(model_key)
        if held is not None:
            status_map = LoadMap(
                status=held.load_map_status,
                sign_convention="",
                components={},
                source="last set_loads",
            )
            info = checks.load_map_status_issue(status_map, connection=held.connection)
            if info is not None:
                issues.append(info)
            issues.extend(
                checks.issues_from_set_loads_reply(
                    {"dropped_zero": list(held.dropped_zero)},
                    connection=held.connection,
                )
            )
            issues.extend(
                checks.compare_loads_readback(
                    requested=held.requested,
                    got=None if held.got is None else list(held.got),
                    tolerance_ratio=held.tolerance_ratio,
                    connection=held.connection,
                )
            )
        tally = Counter(issue.severity for issue in issues)
        summary = CheckModelSummary(
            errors=tally[Severity.ERROR],
            warnings=tally[Severity.WARNING],
            infos=tally[Severity.INFO],
            clean=not tally[Severity.ERROR],
        )
        payload = ModelCheck(summary=summary, issues=issues).model_dump(mode="json")
        resolved = self._identity.resolve(path)
        host = HostInfo(
            program=_PROGRAM,
            version="",
            model_id=resolved.model_id,
            model_revision=resolved.revision,
        )
        producer = Provenance(
            tool="harness/check_model",
            tool_version="1",
            host=host,
            inputs={},
            started_at=started,
            duration_ms=self._clock.now_ms() - began,
        )
        record = self._store.put("issues.model_check/1", payload, producer)
        return make_success(record, summary.model_dump(mode="json"), [])

    async def save(self, model_key: str, role: str) -> SavedModel:
        """No host call: `SavedModel` of the bound file hash (spec 0014 section 4.10)."""
        path = self._file(model_key)
        if model_key not in self._bound:
            raise ContractError(ErrorCode.PRECONDITION_FAILED, "not open", precondition=Precondition.model_open)
        model_id = self._models[model_key]
        digest = _file_sha256(path)
        state = self._identity.record_save(model_id, path, fingerprint=digest)
        self._hashes[model_key] = digest
        recorded = state.file_sha256
        if recorded is None:
            raise ContractError(ErrorCode.INTERNAL, "the save recorded no file hash", incident_id=self._ids.new_ulid())
        return SavedModel(
            model_id=state.model_id,
            revision=state.revision,
            fingerprint=state.fingerprint or digest,
            file_sha256=recorded,
            file_name=path.name,
        )

    async def restore(self, model_key: str, saved: SavedModel) -> HostInstance:
        """Rebind to a journaled file whose hash equals `saved.file_sha256`; on rest close and reopen."""
        path = self._file(model_key)
        if _file_sha256(path) != saved.file_sha256:
            raise ContractError(ErrorCode.CONFLICT, "the saved file's hash differs from the record")
        if self._route == "rest":
            await self._close_project()
            await self._open_live(path)
        instance = self._bind_file(model_key, path, saved.model_id)
        self._hashes[model_key] = saved.file_sha256
        self._instances[instance.instance_id] = instance
        return instance

    async def read_units(self, model_key: str, instance_id: str) -> UnitsState:
        """Fixed declaration of section 4.6; never fails for a missing model (returns not loaded)."""
        held = await self.locate(model_key)
        if held is None or held.instance_id != instance_id:
            return UnitsState(loaded=False, ok=True, present=None, expected=_UNITS)
        return UnitsState(loaded=True, ok=True, present=_UNITS, expected=_UNITS)

    def model_files(self, model_key: str) -> tuple[Path, ...]:
        return (self._file(model_key),)

    async def started_instances(self, host_key: str) -> list[HostInstance]:
        """Empty: the harness never starts IDEA or the service (spec 0014 section 4.10)."""
        return []

    async def close_started(self, host_key: str, instances: Sequence[HostInstance]) -> None:
        return None

    def _lock_key(self) -> str:
        if self._route == "rest":
            if self._service_url is None:
                raise ContractError(ErrorCode.INTERNAL, "service_url missing on route rest")
            material = self._service_url
        else:
            # Prefer a bound working copy when present; else a stable run-folder key.
            bound = next((self._files[k] for k in self._bound if k in self._files), None)
            material = str(bound) if bound is not None else str(self._run_dir)
        return f"idea:{hashlib.sha256(material.encode()).hexdigest()}"

    def _file(self, model_key: str) -> Path:
        try:
            return self._files[model_key]
        except KeyError:
            raise ContractError(ErrorCode.NOT_FOUND, f"no file is bound for {model_key}", received=model_key) from None

    def _bind_file(self, model_key: str, path: Path, model_id: str) -> HostInstance:
        instance_id = self._ids.new_ulid()
        observed: Timestamp = self._clock.now()
        instance = HostInstance(instance_id=instance_id, pid=None, process_started_at=observed, program=_PROGRAM)
        self._files[model_key] = path.resolve()
        self._models[model_key] = model_id
        self._bound[model_key] = instance_id
        return instance

    async def _ensure_native(self, path: Path) -> None:
        if path.suffix != _IDEA_CON:
            raise ContractError(
                ErrorCode.HOST_NOT_CONNECTED,
                "native route requires a .ideaCon working copy",
            )
        status = await self._status()
        if not any(item.hidden_calculator for item in status.installed):
            raise ContractError(
                ErrorCode.HOST_NOT_CONNECTED,
                "native route requires an installed IDEA version with a hidden calculator",
            )

    async def _ensure_rest(self, path: Path) -> None:
        status = await self._status()
        if not status.service.reachable:
            raise ContractError(ErrorCode.HOST_NOT_CONNECTED, "IDEA Connection REST service is not reachable")
        require_inside_run(path, self._run_dir)
        try:
            opened = await self._open_live(path)
        except ContractError:
            await self._close_project()
            raise
        if opened.get("backend") != "rest" or opened.get("live_project") is not True:
            await self._close_project()
            raise ContractError(
                ErrorCode.HOST_NOT_CONNECTED,
                "rest route requires backend=rest with live_project=true",
            )

    async def _status(self) -> IdeaStatus:
        result = await self._sessions.call(self._server, "main", "idea_status", {}, CallEffect.READ)
        if result.is_error:
            raise ContractError(ErrorCode.HOST_NOT_CONNECTED, "idea_status failed")
        body = reply_body(result)
        if body is None:
            raise ContractError(ErrorCode.HOST_NOT_CONNECTED, "idea_status returned no body")
        # The host may send extras (for example current_project); the kind forbids them.
        payload = {
            "installed": body.get("installed", []),
            "service": body.get("service", {}),
            "read_only": body.get("read_only", False),
            "script_enabled": body.get("script_enabled", False),
        }
        return parse_status(payload)

    async def _open_live(self, path: Path) -> dict[str, Any]:
        result = await self._sessions.call(
            self._server,
            "main",
            "idea_open_project",
            {"path": str(path)},
            CallEffect.WRITE,
        )
        if result.is_error:
            raise ContractError(ErrorCode.HOST_NOT_CONNECTED, "idea_open_project failed")
        body = reply_body(result)
        if body is None:
            raise ContractError(ErrorCode.HOST_NOT_CONNECTED, "idea_open_project returned no body")
        return body

    async def _close_project(self) -> None:
        try:
            await self._sessions.call(self._server, "main", "idea_close_project", {}, CallEffect.WRITE)
        except ContractError:
            return

    async def _rest_path_matches(self, path: Path) -> bool:
        result = await self._sessions.call(self._server, "main", "idea_list_connections", {}, CallEffect.READ)
        if result.is_error:
            return False
        body = reply_body(result)
        if body is None:
            return False
        reported = body.get("file_path")
        return isinstance(reported, str) and Path(reported).resolve() == path.resolve()
