"""Model identity and revision state (spec 4.5.5; 04 sections 3.3, 3.4): one file per model under `.eng/state/models/`.

Units: none. Errors: `ContractError` with `INVALID_ARGUMENT` (malformed id), `NOT_FOUND`, `CONFLICT`;
`StoreWriteError` and `StoreIntegrityError` (`INTERNAL`). There is no lock: the compare-and-set detects a lost update.
"""

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from eng_contract._fs import FileSystem, RealFileSystem, StoreIntegrityError, checked_id, write_atomic
from eng_contract._types import Sha256Hex
from eng_contract.canonical import CanonicalJsonError, canonical_json, loads
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import Clock, ModelId, SystemIdSource, Timestamp
from eng_contract.store._workspace import Workspace

_MODEL_ID = TypeAdapter(ModelId)


class ModelState(BaseModel):
    """Persisted identity and revision of a host model (spec 4.5.5)."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, strict=False)

    contract: Literal["eng-contract/1"] = "eng-contract/1"
    model_id: ModelId
    revision: int = Field(ge=0)
    derived_from: ModelId | None = None
    promoted_from: list[ModelId] = Field(default_factory=list)
    fingerprint: str | None = Field(default=None, max_length=200)
    file_sha256: Sha256Hex | None = None
    updated_at: Timestamp


class ModelStateStore:
    """Reads and writes `ModelState` files; state files are mutable (`os.replace`), unlike records."""

    def __init__(
        self,
        workspace: Workspace,
        clock: Clock,
        fs: FileSystem | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """`fs` defaults to the real disk; `sleep` (seconds) is injected so tests need no waiting."""
        self._ws, self._clock, self._sleep = workspace, clock, sleep
        self._fs = RealFileSystem() if fs is None else fs
        self._ids = SystemIdSource(clock)  # incident ids only

    def _path(self, model_id: str) -> Path:
        return self._ws.models_dir / f"{checked_id(_MODEL_ID, model_id)}.json"

    def get(self, model_id: str) -> ModelState | None:
        """The state, or None when the model has none.

        Raises:
            StoreIntegrityError: the file does not parse, validate or belong to `model_id`.
        """
        path = self._path(model_id)
        if not self._fs.exists(path):
            return None
        try:
            state = ModelState.model_validate(loads(self._fs.read(path)))
            if state.model_id != model_id:
                raise ValueError("the state file holds another model id")
        except (CanonicalJsonError, OSError, ValueError) as exc:
            raise StoreIntegrityError(f"state of {model_id} is damaged: {exc}", self._ids) from exc
        return state

    def _save(self, state: ModelState, *, replace: bool) -> ModelState:
        path = self._path(state.model_id)
        self._fs.makedirs(path.parent)
        data = canonical_json(state.model_dump(mode="json"))
        write_atomic(self._fs, path, data, self._ids, self._sleep, replace=replace)
        return state

    def _changed(self, state: ModelState, **fields: Any) -> ModelState:
        return ModelState.model_validate({**state.model_dump(), "updated_at": self._clock.now(), **fields})

    def _existing(self, model_id: str) -> ModelState:
        if (state := self.get(model_id)) is None:
            raise ContractError(ErrorCode.NOT_FOUND, f"no state for model {model_id}", received=model_id)
        return state

    def create(self, model_id: str, derived_from: str | None = None) -> ModelState:
        """Create the state at revision 0 (exclusive create).

        Raises:
            ContractError: `CONFLICT` if the state exists, `INVALID_ARGUMENT` for a malformed id.
        """
        if derived_from is not None:
            checked_id(_MODEL_ID, derived_from)
        if self.get(model_id) is not None:
            raise ContractError(ErrorCode.CONFLICT, f"model {model_id} already has a state", received=model_id)
        state = ModelState(model_id=model_id, revision=0, derived_from=derived_from, updated_at=self._clock.now())
        return self._save(state, replace=False)

    def increment(
        self, model_id: str, expected_revision: int, fingerprint: str | None = None, file_sha256: str | None = None
    ) -> ModelState:
        """Compare-and-set: revision `expected_revision` becomes the next one, with the new fingerprint and file hash
        (None clears them: they describe the earlier revision).

        Raises:
            ContractError: `NOT_FOUND` (no state), `CONFLICT` (the stored revision differs; nothing is written).
        """
        state = self._existing(model_id)
        if state.revision != expected_revision:
            raise ContractError(
                ErrorCode.CONFLICT,
                f"model {model_id} is at revision {state.revision}",
                expected={"revision": expected_revision},
                received=state.revision,
            )
        changed = self._changed(state, revision=state.revision + 1, fingerprint=fingerprint, file_sha256=file_sha256)
        return self._save(changed, replace=True)

    def record_promotion(self, target: str, source: str) -> ModelState:
        """Record that `target` was promoted from `source` (once); the revision is unchanged.

        Raises:
            ContractError: `NOT_FOUND` (no state for `target`), `INVALID_ARGUMENT` (malformed id).
        """
        checked_id(_MODEL_ID, source)
        state = self._existing(target)
        if source in state.promoted_from:
            return state
        return self._save(self._changed(state, promoted_from=[*state.promoted_from, source]), replace=True)
