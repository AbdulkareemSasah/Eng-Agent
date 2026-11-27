"""Setup interface to the approval page (spec 0004 section 4.6, AC26, AC27).

Purpose: `build_setup_view` turns a `BasisDraft` into the read-only view the page shows; `BasisSetupAnswer` is what the
page returns. The answer names confirmed sections or a rejection and has no member that carries a value, so values
arrive only through the values file (ADR-0027). No HTML here; spec 0006 implements the page against `BasisSetupPort`.
Units: rows carry the canonical unit of their field. Errors: a malformed answer raises pydantic `ValidationError`.
"""

from typing import Annotated, Literal, Protocol, Self

from eng_contract.cited import Cited
from eng_contract.ids import Timestamp
from pydantic import BaseModel, ConfigDict, JsonValue, StringConstraints, model_validator

from eng_harness.basis._build import BasisDraft, DraftField, DraftTemplate, DraftWarning
from eng_harness.basis._fields import FieldSpec

_MODEL = ConfigDict(frozen=True, extra="forbid")
_ULID = StringConstraints(strict=True, pattern=r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")
_SHA256 = StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")

Banner = Literal["draft_template", "synthetic_template"]
State = Literal["provided", "detected", "missing"]


class SetupRow(BaseModel):
    """One field as the page shows it; `state` is `missing` when the draft holds no value for it."""

    model_config = _MODEL
    path: str
    label: str
    value: JsonValue
    unit: str | None
    source: str | None
    citation: str | None
    state: State
    required: bool
    min: Cited | None
    max: Cited | None


class SetupSection(BaseModel):
    """The rows under one top-level key; `confirmable` is false while a required row is missing."""

    model_config = _MODEL
    name: str
    confirmable: bool
    rows: tuple[SetupRow, ...]


class BasisSetupView(BaseModel):
    """Everything the page shows for one draft, identified by `setup_id` and `draft_sha256`."""

    model_config = _MODEL
    setup_id: Annotated[str, _ULID]
    draft_sha256: str
    workflow: str
    template: DraftTemplate | None
    banners: tuple[Banner, ...]
    sections: tuple[SetupSection, ...]
    warnings: tuple[DraftWarning, ...]
    unused: tuple[str, ...]


class BasisSetupAnswer(BaseModel):
    """The engineer's answer: confirmed section names with `by` and `at`, or a `rejected` reason. Never a value."""

    model_config = _MODEL
    setup_id: Annotated[str, _ULID]
    draft_sha256: Annotated[str, _SHA256]
    confirmed_sections: tuple[str, ...] | None = None
    by: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)] | None = None
    at: Timestamp | None = None
    rejected: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=500)] | None = None

    @model_validator(mode="after")
    def _one_form(self) -> Self:
        confirms = (self.confirmed_sections, self.by, self.at)
        if self.rejected is not None:
            if any(part is not None for part in confirms):
                raise ValueError("an answer either confirms sections or rejects, not both")
        elif not self.confirmed_sections or self.by is None or self.at is None:
            raise ValueError("a confirmation needs confirmed_sections, by and at")
        return self


class BasisSetupPort(Protocol):
    """The page side of the setup: show a view, then read the answer (None while there is none yet)."""

    def present(self, view: BasisSetupView) -> None:
        """Show `view` to the engineer."""
        ...

    def answer(self, setup_id: str, *, wait: bool) -> BasisSetupAnswer | None:
        """Return the answer for `setup_id`; with `wait` false return None when there is none yet."""
        ...


def _row(spec: FieldSpec, found: DraftField | None) -> SetupRow:
    state: State = "missing"
    if found is not None:
        state = "detected" if (found.source or "").startswith("model:") else "provided"
    return SetupRow(
        path=spec.path,
        label=spec.label,
        value=None if found is None else found.value,
        unit=spec.unit,
        source=None if found is None else found.source or found.origin,
        citation=None if found is None else found.citation,
        state=state,
        required=spec.required,
        min=spec.min,
        max=spec.max,
    )


def _banners(template: DraftTemplate | None) -> tuple[Banner, ...]:
    if template is None:
        return ()
    draft: tuple[Banner, ...] = ("draft_template",) if template.status == "draft" else ()
    synthetic: tuple[Banner, ...] = ("synthetic_template",) if template.synthetic else ()
    return draft + synthetic


def build_setup_view(draft: BasisDraft, *, workflow: str, setup_id: str) -> BasisSetupView:
    """Build the page view of `draft`: sections by top-level key in name order, rows by path (AC26)."""
    grouped: dict[str, list[SetupRow]] = {}
    for spec in sorted(draft.specs, key=lambda item: item.path):
        grouped.setdefault(spec.path.partition(".")[0], []).append(_row(spec, draft.fields.get(spec.path)))
    sections = tuple(
        SetupSection(
            name=name,
            confirmable=not any(row.required and row.state == "missing" for row in rows),
            rows=tuple(rows),
        )
        for name, rows in sorted(grouped.items())
    )
    return BasisSetupView(
        setup_id=setup_id,
        draft_sha256=draft.sha256,
        workflow=workflow,
        template=draft.template,
        banners=_banners(draft.template),
        sections=sections,
        warnings=draft.warnings,
        unused=draft.unused,
    )
