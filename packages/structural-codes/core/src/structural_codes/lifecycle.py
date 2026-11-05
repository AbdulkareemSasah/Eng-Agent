"""Lifecycle state of a check and the `approvals.yaml` file (spec 0001 section 4.8; AC23, AC24).

Purpose: the runtime state of a check, computed from the pack's shipped `approvals.yaml` and the check's content hash
only (never case files, which are not installed). `withdrawn` wins; `approved` needs an entry with the current hash and,
for an inherited check, the kind `inherited-confirmed` and an approved base check; otherwise `draft`. `verified` is a
verification-time state (`verify_check`) and is never returned here. R1 module: a mistake here lets an unapproved check
run in production. Units: none.
Errors: `ApprovalsFileError` for an invalid or unreadable `approvals.yaml`. A pack whose file is absent has no approval
and every check of it is `draft` (the safe side).
"""

import datetime as dt
import logging
import re
from collections.abc import Collection
from importlib.resources import files
from typing import Annotated, Any, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from structural_codes._yaml import load_yaml
from structural_codes.check import Check
from structural_codes.content_hash import content_hash
from structural_codes.errors import ApprovalsFileError
from structural_codes.overlay import InheritedCheck
from structural_codes.pack import Pack, Registry

__all__ = ["Approval", "ApprovalsFile", "State", "Withdrawal", "resolve_state"]

State = Literal["draft", "verified", "approved", "withdrawn"]
"""Lifecycle states of a check (10 section 4); `resolve_state` returns `draft`, `approved` or `withdrawn`."""

FORMAT: Final = "structural-codes-approvals/1"
_log = logging.getLogger(__name__)
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_Text = Annotated[str, StringConstraints(min_length=1)]
_Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_Url = Annotated[str, StringConstraints(pattern=r"^https://\S+$")]


def _iso_date(value: Any) -> Any:
    """Accept a YAML date or a quoted `YYYY-MM-DD` text; refuse a timestamp and any other form."""
    if isinstance(value, str) and _ISO_DATE.fullmatch(value):
        try:
            return dt.date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"not a calendar date: {value!r}") from exc
    if type(value) is dt.date:
        return value
    raise ValueError("date must be YYYY-MM-DD")


class _Strict(BaseModel):
    """Base of the file models: frozen, unknown fields refused."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("date", mode="before", check_fields=False)
    @classmethod
    def _date(cls, value: Any) -> Any:
        return _iso_date(value)


class Approval(_Strict):
    """The owner's approval of one check at one content hash (`kind` fits approved or inherited checks)."""

    check_id: _Text
    content_sha256: _Sha256
    kind: Literal["approved", "inherited-confirmed"]
    approver: _Text
    date: dt.date
    verification_record: _Text
    pull_request: _Url


class Withdrawal(_Strict):
    """The withdrawal of a check; it wins over any approval."""

    check_id: _Text
    reason: _Text
    issue: _Text
    date: dt.date


class ApprovalsFile(_Strict):
    """A pack's `approvals.yaml`; only the owner adds entries (CODEOWNERS), the core validates shape and kind."""

    format: Literal["structural-codes-approvals/1"]
    approvals: tuple[Approval, ...]
    withdrawn: tuple[Withdrawal, ...]

    @classmethod
    def parse(cls, text: str, *, inherited: Collection[str] = ()) -> Self:
        """Parse and validate the text of an `approvals.yaml`.

        `inherited` holds the ids of the pack's inherited checks: they take the kind `inherited-confirmed`, all
        others the kind `approved`.

        Raises:
            ApprovalsFileError: invalid YAML, a repeated key, a missing field, an unknown key, a malformed hash or
                date, or a kind that does not fit the check (AC23).
        """
        try:
            parsed = cls.model_validate(load_yaml(text, ApprovalsFileError))
        except ValueError as exc:  # pydantic's ValidationError, or YAML's own refusal of a date such as 2026-13-45
            raise ApprovalsFileError(f"invalid approvals file: {exc}") from exc
        for a in parsed.approvals:
            if (a.kind == "inherited-confirmed") != (a.check_id in inherited):
                raise ApprovalsFileError(
                    f"{a.check_id}: kind {a.kind!r} does not fit "
                    f"{'an inherited' if a.check_id in inherited else 'a non-inherited'} check"
                )
        return parsed

    @classmethod
    def load(cls, pack: Pack, *, inherited: Collection[str] = ()) -> Self:
        """Read the pack's `approvals.yaml` from its package resource (`Pack.approvals`) and `parse` it.

        An absent file gives an empty one (nothing is approved).

        Raises:
            ApprovalsFileError: the file is unreadable or invalid (see `parse`).
        """
        resource = files(pack.name).joinpath(*pack.approvals.split("/"))
        if not resource.is_file():
            _log.warning("approvals file absent", extra={"pack": pack.name})
            return cls(format=FORMAT, approvals=(), withdrawn=())
        try:
            text = resource.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ApprovalsFileError(f"{pack.name}: cannot read {pack.approvals}: {exc}") from exc
        return cls.parse(text, inherited=inherited)


def resolve_state(check: Check, registry: Registry, *, digest: str | None = None) -> State:
    """Return the runtime state of `check`: `withdrawn`, `approved` or `draft` (never `verified`, AC24).

    `digest` is the check's content hash when the caller has it already. The packs come from `registry`: the
    check's own pack and, for an inherited check, the pack of its base check.

    Raises:
        ApprovalsFileError: a pack's `approvals.yaml` is invalid.
        CheckDefinitionError: the content hash cannot be computed (see `content_hash`).
    """
    pack = next(p for p in registry.packs if p.name == check.meta.pack)
    inherited_ids = {
        c.meta.check_id for c in registry.checks if c.meta.pack == pack.name and isinstance(c, InheritedCheck)
    }
    approvals = ApprovalsFile.load(pack, inherited=inherited_ids)
    check_id = check.meta.check_id
    if any(w.check_id == check_id for w in approvals.withdrawn):
        return "withdrawn"
    kind = "inherited-confirmed" if isinstance(check, InheritedCheck) else "approved"
    current = digest or content_hash(check)
    if not any(a.check_id == check_id and a.content_sha256 == current and a.kind == kind for a in approvals.approvals):
        return "draft"
    if isinstance(check, InheritedCheck) and resolve_state(check.base, registry) != "approved":
        return "draft"
    return "approved"
