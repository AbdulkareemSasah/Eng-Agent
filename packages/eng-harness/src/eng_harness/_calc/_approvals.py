"""approvals.yaml: schema, strict loader, status resolution and `check_approvals` (spec 0003 4.5, AC8, AC9).

Purpose: `approved` and `withdrawn` come only from this owner-maintained file. A matching `withdrawn` entry wins, then
an exact `approvals` match (calc id, version, content hash), else the calc's declared `verification`. The file is read
by the strict YAML loader of the templates package (no second YAML library), so tags, anchors, duplicate keys and
other documents are refused before the schema is checked. Units: none.
Errors: `ApprovalsError` with `reason` `yaml_invalid`, `not_found`, `schema_invalid` or `unknown_calc`, and `path`,
the entry path of the first problem (for example `approvals[0].approver`); the message holds no file contents.
"""

import re
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from eng_harness.calc import CalcDef, CalcRegistry, CalcStatus
from eng_harness.templates._model import TemplateInvalid
from eng_harness.templates._yaml import load_strict

APPROVALS_PATH = Path(__file__).resolve().parents[1] / "calcs" / "approvals.yaml"
_RECORD = re.compile(r"^docs/verification/calcs/[A-Za-z0-9_.-]+\.md$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ApprovalsError(ValueError):
    """approvals.yaml breaks the schema of spec 0003 4.5; `reason` is the key, `path` the offending entry."""

    def __init__(self, reason: str, path: str, file: str | None = None) -> None:
        """Build the error; the message holds only the reason key and the path."""
        self.reason = reason
        self.path = path
        self.file = file
        super().__init__(f"approvals invalid: {reason} at {path or '<root>'}")


def _iso_date(value: str) -> str:
    """Accept only a real calendar date written YYYY-MM-DD."""
    if not _DATE.fullmatch(value):
        raise ValueError("must be YYYY-MM-DD")
    date.fromisoformat(value)
    return value


_Text = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
_Date = Annotated[str, StringConstraints(strict=True), AfterValidator(_iso_date)]
_Version = Annotated[int, Field(strict=True, ge=1, le=9999)]
_Sha = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]
_CalcId = Annotated[str, StringConstraints(strict=True, min_length=1)]
_MODEL = ConfigDict(frozen=True, extra="forbid")


class ApprovalEntry(BaseModel):
    """One approval: the owner approved this exact content hash of one calc version."""

    model_config = _MODEL
    calc_id: _CalcId
    version: _Version
    content_sha256: _Sha
    approver: _Text
    date: _Date
    verification_record: Annotated[str, StringConstraints(strict=True, pattern=_RECORD.pattern)]
    pull_request: Annotated[int, Field(strict=True, ge=1)]


class WithdrawnEntry(BaseModel):
    """One withdrawal of a calc version, for one content hash or (`any`) for every hash."""

    model_config = _MODEL
    calc_id: _CalcId
    version: _Version
    content_sha256: Annotated[str, StringConstraints(strict=True, pattern=r"^([0-9a-f]{64}|any)$")]
    date: _Date
    reason: _Text
    advisory: _Text


class ApprovalsFile(BaseModel):
    """The whole file: schema 1, `approvals` and `withdrawn`."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=False)
    schema_version: Literal[1] = Field(alias="schema")
    approvals: tuple[ApprovalEntry, ...]
    withdrawn: tuple[WithdrawnEntry, ...]

    @model_validator(mode="after")
    def _no_duplicates(self) -> Self:
        keys = [(e.calc_id, e.version, e.content_sha256) for e in self.approvals]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate approval entry")
        return self


@dataclass(frozen=True, slots=True)
class ApprovalFinding:
    """A `check_approvals` result: `kind` is `stale_approval` or `unknown_calc`."""

    kind: Literal["stale_approval", "unknown_calc"]
    calc_id: str


def _path(loc: tuple[int | str, ...]) -> str:
    return "".join(f"[{p}]" if isinstance(p, int) else (f".{p}" if i else str(p)) for i, p in enumerate(loc))


def load_approvals(path: Path, known_ids: Collection[str]) -> ApprovalsFile:
    """Read and validate `path`; every calc id must be in `known_ids` (a registry works).

    Raises:
        ApprovalsError: any rule of the module docstring is broken.
    """
    try:
        data = load_strict(path)
    except TemplateInvalid as error:
        raise ApprovalsError(error.reason, error.path, path.name) from error
    try:
        loaded = ApprovalsFile.model_validate(data)
    except ValidationError as error:
        first = error.errors()[0]
        raise ApprovalsError("schema_invalid", _path(first["loc"]), path.name) from error
    ids = [("approvals", i, e.calc_id) for i, e in enumerate(loaded.approvals)]
    ids += [("withdrawn", i, e.calc_id) for i, e in enumerate(loaded.withdrawn)]
    for section, index, calc_id in ids:
        if calc_id not in known_ids:
            raise ApprovalsError("unknown_calc", f"{section}[{index}].calc_id", path.name)
    return loaded


def resolve_status(definition: CalcDef, content_sha256: str, approvals: ApprovalsFile) -> CalcStatus:
    """Status of one calc: withdrawn, else approved on an exact (id, version, hash) match, else as declared."""
    for gone in approvals.withdrawn:
        if (gone.calc_id, gone.version) == (definition.id, definition.version) and gone.content_sha256 in (
            "any",
            content_sha256,
        ):
            return CalcStatus.WITHDRAWN
    for entry in approvals.approvals:
        if (entry.calc_id, entry.version, entry.content_sha256) == (definition.id, definition.version, content_sha256):
            return CalcStatus.APPROVED
    return CalcStatus(definition.verification)


def check_approvals(registry: CalcRegistry, approvals: ApprovalsFile) -> list[ApprovalFinding]:
    """List approvals of the registry's calcs whose hash no longer matches, and entries of unregistered calcs."""
    findings: list[ApprovalFinding] = []
    for entry in approvals.approvals:
        if entry.calc_id not in registry:
            findings.append(ApprovalFinding("unknown_calc", entry.calc_id))
        elif entry.version == registry[entry.calc_id].version and entry.content_sha256 != registry.content_hash(
            entry.calc_id
        ):
            findings.append(ApprovalFinding("stale_approval", entry.calc_id))
    return findings
