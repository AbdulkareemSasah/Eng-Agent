"""Revit HostPort session operations (plan 0011 T11; AC23 to AC26, §4.9, §4.12).

Purpose: working-copy open with reply checks, `NotImplementedGap` for save/restore (R-G1, R-G2), empty
`started_instances`, engineer-save hash registration via injected fingerprints, and the host lock keyed by a hash of
the pipe name. The adapter never starts, exits or closes Revit or a document. Units: none for paths.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

from eng_contract.envelope import Envelope
from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.ids import Clock, IdSource, Timestamp

from eng_harness.adapters._identity import IdentityStore
from eng_harness.errors import NotImplementedGap
from eng_harness.ports import HostInstance, HostLease, HostModelState, SavedModel, ServerCheck, UnitsState
from eng_harness.servers import CallEffect, ServerManager
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._session import reply_body

__all__ = [
    "RevitHostPort",
    "pipe_lock_key",
    "raise_gap",
]

_PROGRAM = "revit"
_UNITS = "revit_schema/1"  # fixed declaration of spec 0011 §4.6 / T7 document capabilities
_WRITE_ROLE = "write"  # revit_open_model is on the write role (spec 0011 §4.3)

# Spec 0011 section 11: gap ids and the recommendation text that becomes the refusal message.
_GAPS: Mapping[str, str] = {
    "R-G1": "No save tool (S12-G11): HostPort.save is NotImplementedGap; edits stay unsaved",
    "R-G2": (
        "No close or revert tool: the working copy stays open, restore unavailable, promotion by file copy impossible"
    ),
}


def pipe_lock_key(pipe_name: str) -> str:
    """Opaque lock key: sha256 of the pipe name (spec 0011 AC26 / §4.12)."""
    return hashlib.sha256(pipe_name.encode("utf-8")).hexdigest()


def raise_gap(gap_id: str) -> NoReturn:
    """Raise `NotImplementedGap` for `gap_id`; `KeyError` for an unknown identifier."""
    raise NotImplementedGap(_GAPS[gap_id], evidence=(gap_id,))


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


class RevitHostPort:
    """HostPort for Revit: working copy, gaps, pipe-keyed lock; the harness never starts Revit."""

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
        pipe_name: str,
        server: str = "revit",
        host_key: str = "revit",
    ) -> None:
        self._identity = identity
        self._sessions = sessions
        self._locks = locks
        self._clock = clock
        self._ids = ids
        self._run_dir = run_dir.resolve()
        self._server = server
        self._host_key = host_key
        self._pipe_name = pipe_name
        self._files = {key: path.resolve() for key, path in files.items()}
        self._models: dict[str, str] = {}
        self._bound: dict[str, str] = {}
        self._instances: dict[str, HostInstance] = {}
        self._fingerprints: dict[str, str] = {}

    @property
    def identity_store(self) -> IdentityStore:
        """The identity store used for `derived_from` lineage (ADR-0032)."""
        return self._identity

    async def preflight(self, min_builds: Mapping[str, str]) -> list[ServerCheck]:
        return await self._sessions.preflight(min_builds)

    def session_epoch(self, host_key: str) -> int:
        return self._sessions.session_epoch(host_key)

    async def acquire(self, host_key: str) -> HostLease:
        """Lease the pipe-keyed lock of §4.12 (`HOST_LOCKED` when held elsewhere)."""
        if host_key == self._host_key:
            self._locks.acquire_key(_PROGRAM, pipe_lock_key(self._pipe_name))
        return HostLease(host_key=host_key, lease_id=self._ids.new_ulid())

    async def release(self, lease: HostLease) -> None:
        self._locks.release_all()

    async def working_copy(self, model_key: str, folder: Path) -> str:
        """Copy the model, open the copy, check the reply (AC23); record `derived_from` identity."""
        source = self._file(model_key)
        self._identity.resolve(source)
        dest = _copied(source, folder)
        body = await self._open_model(dest)
        self._check_open_reply(body, dest)
        resolved = self._identity.resolve(dest)
        instance = self._bind_file(f"{model_key}@copy", dest, resolved.model_id)
        self._instances[instance.instance_id] = instance
        return f"{model_key}@copy"

    async def locate(self, model_key: str) -> HostInstance | None:
        """Bound document when the metadata path equals the file; `HostInstance.pid` is None (§4.12)."""
        instance_id = self._bound.get(model_key)
        if instance_id is None:
            return None
        path = self._files.get(model_key)
        if path is None or not path.is_file():
            return None
        if not await self._document_loaded(path):
            return None
        return self._instances.get(instance_id)

    async def model_state(self, model_key: str, instance_id: str) -> HostModelState:
        held = await self.locate(model_key)
        if held is None or held.instance_id != instance_id:
            return HostModelState(loaded=False)
        path = self._file(model_key)
        resolved = self._identity.resolve(path)
        fingerprint = self._fingerprints.get(model_key, "")
        return HostModelState(
            loaded=True,
            model_id=resolved.model_id,
            revision=resolved.revision,
            fingerprint=fingerprint,
            file_sha256=_file_sha256(path),
        )

    async def check_model(self, model_key: str) -> Envelope:
        """Attended checks land in T9 (`_checks.py`); until then there is no read-back wiring."""
        raise ContractError(ErrorCode.INTERNAL, "no read-back wiring", incident_id=self._ids.new_ulid())

    async def save(self, model_key: str, role: str) -> SavedModel:
        """No save tool (R-G1); nothing is sent."""
        raise_gap("R-G1")

    async def restore(self, model_key: str, saved: SavedModel) -> HostInstance:
        """No close or revert tool (R-G2); nothing is sent."""
        raise_gap("R-G2")

    async def read_units(self, model_key: str, instance_id: str) -> UnitsState:
        held = await self.locate(model_key)
        if held is None or held.instance_id != instance_id:
            return UnitsState(loaded=False, ok=True, present=None, expected=_UNITS)
        return UnitsState(loaded=True, ok=True, present=_UNITS, expected=_UNITS)

    def model_files(self, model_key: str) -> tuple[Path, ...]:
        return (self._file(model_key),)

    async def started_instances(self, host_key: str) -> list[HostInstance]:
        """Empty: the harness never starts Revit (spec 0011 §4.12)."""
        return []

    async def close_started(self, host_key: str, instances: Sequence[HostInstance]) -> None:
        """No-op: the adapter never exits or closes Revit or a document (AC24)."""
        return None

    def register_engineer_save(self, model_key: str, *, fingerprint: str) -> None:
        """Register a new file hash when the engineer saved; same fingerprint keeps the revision (AC25)."""
        path = self._file(model_key)
        model_id = self._models[model_key]
        previous = self._fingerprints.get(model_key, fingerprint)
        resolution = self._identity.register_hash(
            model_id, path, fingerprint=fingerprint, previous_fingerprint=previous
        )
        self._models[model_key] = resolution.model_id
        self._fingerprints[model_key] = fingerprint

    def note_fingerprint(self, model_key: str, fingerprint: str) -> None:
        """Record the adapter's last known state fingerprint for a later engineer-save check."""
        self._fingerprints[model_key] = fingerprint

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

    async def _open_model(self, path: Path) -> dict[str, Any]:
        # Never send allow_discard_unsaved_changes (AC23); activate the copy.
        arguments: dict[str, Any] = {"path": str(path), "activate": True}
        result = await self._sessions.call(self._server, _WRITE_ROLE, "revit_open_model", arguments, CallEffect.WRITE)
        if result.is_error:
            raise ContractError(
                ErrorCode.PRECONDITION_FAILED,
                "revit_open_model failed",
                precondition=Precondition.model_open,
            )
        body = reply_body(result)
        if body is None:
            raise ContractError(
                ErrorCode.PRECONDITION_FAILED,
                "revit_open_model returned no body",
                precondition=Precondition.model_open,
            )
        return body

    def _check_open_reply(self, body: Mapping[str, Any], expected: Path) -> None:
        """AC23 reply checks: path equals the copy, not workshared, no local file created."""
        reported = body.get("path")
        if not isinstance(reported, str) or Path(reported).resolve() != expected.resolve():
            raise ContractError(
                ErrorCode.PRECONDITION_FAILED,
                f"open_model path {reported!r} is not the working copy",
                precondition=Precondition.model_open,
            )
        if body.get("is_workshared") is not False:
            raise ContractError(
                ErrorCode.PRECONDITION_FAILED,
                "open_model reported a workshared model",
                precondition=Precondition.model_open,
            )
        # Absent local_file_created means false; an explicit true (or a local_path) refuses (R-G9 / AC23).
        if body.get("local_file_created", False) is not False or body.get("local_path"):
            raise ContractError(
                ErrorCode.PRECONDITION_FAILED,
                "open_model created a local file of a central model",
                precondition=Precondition.model_open,
            )

    async def _document_loaded(self, bound: Path) -> bool:
        result = await self._sessions.call(self._server, "read", "revit_get_model_metadata", {}, CallEffect.READ)
        if result.is_error:
            return False
        body = reply_body(result)
        if body is None:
            return False
        reported = body.get("path")
        return isinstance(reported, str) and Path(reported).resolve() == bound.resolve()
