"""Harness-side model identity (plan 0002 T10; ADR-0032 decisions 2 to 4, spec 0002 AC30)."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, NoReturn

from eng_contract.canonical import canonical_json
from eng_contract.errors import ContractError, ErrorCode, WarningCode
from eng_contract.ids import IdSource, ModelId, new_model_id
from eng_contract.store import ModelState, ModelStateStore, Workspace
from pydantic import BaseModel, ConfigDict, Field


class Resolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: ModelId
    revision: int = Field(ge=0)
    derived_from: ModelId | None = None
    warnings: tuple[WarningCode, ...] = ()


class IdentityStore:
    def __init__(self, *, workspace: Workspace, states: ModelStateStore, ids: IdSource) -> None:
        self._root = workspace.root / ".eng" / "state" / "model-files"
        self._states, self._ids = states, ids

    def resolve(self, path: Path) -> Resolution:
        path = path.resolve()
        digest = _sha256(path)
        content, location = self._content(digest), self._location(_path_hash(path))
        if content is not None and (location is None or location[0] == content[0]):
            return self._derive(content[0], path, digest) if location is None else self._known(content[0])
        if content is not None and location is not None:
            return self._known(location[0])  # the path's identity is the one this path hash matches
        if location is None:
            created = self._states.create(new_model_id(self._ids))
            self._write_content(digest, created.model_id, created.revision)
            self._write_location(path, created.model_id, digest)
            return self._known(created.model_id)
        return self._outside(location[0], path, digest)

    def record_save(self, model_id: str, path: Path) -> ModelState:
        path = path.resolve()
        digest, state = _sha256(path), self._require(model_id)
        updated = self._states.increment(model_id, state.revision, state.fingerprint, digest)
        self._write_content(digest, updated.model_id, updated.revision, keep_older=True)
        self._write_location(path, updated.model_id, digest)
        return updated

    def _derive(self, older: str, path: Path, digest: str) -> Resolution:
        created = self._states.create(new_model_id(self._ids), derived_from=older)
        self._write_location(path, created.model_id, digest)  # the content index keeps the older identity
        return self._known(created.model_id)

    def _outside(self, model_id: str, path: Path, digest: str) -> Resolution:
        state = self._require(model_id)
        updated = self._states.increment(model_id, state.revision, state.fingerprint, digest)
        self._write_content(digest, updated.model_id, updated.revision, keep_older=True)
        self._write_location(path, updated.model_id, digest)
        return self._known(model_id, (WarningCode.MODEL_CHANGED_OUTSIDE,))

    def _known(self, model_id: str, warnings: tuple[WarningCode, ...] = ()) -> Resolution:
        s = self._require(model_id)
        return Resolution(model_id=s.model_id, revision=s.revision, derived_from=s.derived_from, warnings=warnings)

    def _require(self, model_id: str) -> ModelState:
        if (state := self._states.get(model_id)) is None:
            raise ContractError(ErrorCode.NOT_FOUND, f"no state for model {model_id}", received=model_id)
        return state

    def _content(self, digest: str) -> tuple[str, int] | None:
        return self._pair("by-sha256", digest, "model_id", "revision", str, int)

    def _location(self, path_hash: str) -> tuple[str, str] | None:
        return self._pair("by-path", path_hash, "model_id", "last_file_sha256", str, str)

    def _write_content(self, digest: str, model_id: str, revision: int, *, keep_older: bool = False) -> None:
        current = self._content(digest)
        if not (keep_older and current is not None and current[0] != model_id):
            self._write("by-sha256", digest, {"model_id": model_id, "revision": revision})

    def _write_location(self, path: Path, model_id: str, digest: str) -> None:
        self._write("by-path", _path_hash(path), {"model_id": model_id, "last_file_sha256": digest})

    def _pair(self, folder: str, name: str, a: str, b: str, ta: type[Any], tb: type[Any]) -> tuple[Any, Any] | None:
        body = self._read(folder, name)
        if body is None:
            return None
        first, second = body.get(a), body.get(b)
        if isinstance(first, ta) and isinstance(second, tb):
            return first, second
        self._damaged()

    def _read(self, folder: str, name: str) -> dict[str, Any] | None:
        path = self._root / folder / f"{name}.json"
        if not path.is_file():
            return None
        body = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(body, dict):
            return body
        self._damaged()

    def _write(self, folder: str, name: str, payload: dict[str, object]) -> None:
        path = self._root / folder / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(canonical_json(payload))
        os.replace(temporary, path)

    def _damaged(self) -> NoReturn:
        raise ContractError(ErrorCode.INTERNAL, "the identity index is damaged", incident_id=self._ids.new_ulid())


def _sha256(path: Path) -> str:
    if not path.is_file():
        raise ContractError(ErrorCode.NOT_FOUND, "the model file is not there", received=path.name)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _path_hash(path: Path) -> str:
    return hashlib.sha256(os.path.normcase(str(path.resolve())).encode()).hexdigest()  # ADR-0032 decision 2
