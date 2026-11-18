"""Revision files of the edit cycle (spec 0007 4.5.1, 4.10; plan 0007 T5).

`Revisions` keeps one run's files in its copies folder: a snapshot is a verified copy of the working file `W` (the file
the host has open), its SHA-256 recorded in `run_dir/adapter/revisions.json`; a restore copies a snapshot whose hash is
still the recorded one to a new working file. Nothing is overwritten. Errors (`ContractError`): `CONFLICT` (a file at
the target, a copy or snapshot whose hash differs), `NOT_FOUND` (a name no save of this run made, or its file gone).
"""

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import ParamModel
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from eng_harness.ports import ToolInfo

__all__ = ["CsiToolInfo", "OpenRevisionArgs", "Revisions", "SaveModelArgs", "SavedFile"]


class SaveModelArgs(ParamModel):
    """`csi_save_model`: the open file in place, and with `as_new_revision` also a snapshot of it."""

    model: str
    as_new_revision: bool = False


class OpenRevisionArgs(ParamModel):
    """`csi_open_revision`: `revision` is the base name of a snapshot (`saved_file.name` of the save that made it)."""

    model: str
    revision: str


class SavedFile(BaseModel):
    """The `saved_file` of a result summary: the base name of the file written and its SHA-256 (engine 4.6)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CsiToolInfo(ToolInfo):
    """`ToolInfo` that knows which calls write a new file (engine 4.8 `saves_new_file`, spec 0007 4.10) and which open
    changes no model content (`opens_model_without_writing`, B-562)."""

    def saves_new_file(self, args: Mapping[str, JsonValue]) -> bool:
        """True for `csi_open_revision` and for `csi_save_model` with `as_new_revision` true."""
        return self.name == "csi_open_revision" or (
            self.name == "csi_save_model" and args.get("as_new_revision") is True
        )

    def opens_model_without_writing(self, args: Mapping[str, JsonValue]) -> bool:
        """True only for `csi_open_model` without `path`: the step 2 open of the original (spec 0002 4.5.9, AC52)."""
        return self.name == "csi_open_model" and "path" not in args


class Revisions:
    """The snapshots of one run in `folder`, with the hash recorded for each in the file `record`."""

    def __init__(self, folder: Path, record: Path) -> None:
        self._folder, self._record = folder, record

    def target(self, working: Path) -> Path:
        """The path of the next snapshot of `working`; `CONFLICT` when a file is already there."""
        path = self._folder / f"{working.stem}.rev{len(self._book()) + 1:03d}{working.suffix}"
        if path.exists():
            raise ContractError(ErrorCode.CONFLICT, "a file is already at the snapshot's path", received=path.name)
        return path

    def snapshot(self, working: Path, target: Path) -> SavedFile:
        """Copy `working` to `target` (from `target`), verify the copy and record its hash."""
        saved = SavedFile(name=target.name, sha256=self._copy(working, target))
        self._write({**self._book(), saved.name: saved.sha256})
        return saved

    def reopen(self, name: str) -> tuple[Path, SavedFile]:
        """Copy the snapshot `name` to the first free working file name and return it; the snapshot is unchanged."""
        recorded = self._book().get(name)
        source = self._folder / name
        if recorded is None or not source.is_file():
            raise ContractError(ErrorCode.NOT_FOUND, "no snapshot of this run has that name", received=name)
        number = 1
        while (path := self._folder / f"{source.stem}.w{number}{source.suffix}").exists():
            number += 1
        return path, SavedFile(name=path.name, sha256=self._copy(source, path, recorded))

    def is_snapshot(self, path: Path) -> bool:
        """True when `path` is a snapshot of this run."""
        return path.resolve().parent == self._folder.resolve() and path.name in self._book()

    def _copy(self, source: Path, target: Path, expected: str | None = None) -> str:
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if expected is not None and digest != expected:
            raise ContractError(
                ErrorCode.CONFLICT, "the snapshot's hash differs from the recorded one", received=source.name
            )
        try:
            with target.open("xb") as handle:  # never over an existing file
                handle.write(data)
        except FileExistsError:
            raise ContractError(ErrorCode.CONFLICT, "a file is already at the target", received=target.name) from None
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            target.unlink()
            raise ContractError(ErrorCode.CONFLICT, "the copy's hash differs from the original", received=target.name)
        return digest

    def _book(self) -> dict[str, str]:
        if not self._record.is_file():
            return {}
        book: dict[str, str] = json.loads(self._record.read_text(encoding="utf-8"))["snapshots"]
        return book

    def _write(self, book: Mapping[str, str]) -> None:
        self._record.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._record.with_suffix(".json.tmp")
        temporary.write_text(json.dumps({"snapshots": book}), encoding="utf-8")
        os.replace(temporary, self._record)
