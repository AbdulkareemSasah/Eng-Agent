"""Payload models of the calc kinds (spec 0003 4.6, 4.7) and `harness.expected_effects/1` (4.8).

Purpose: the stored form of each calc result, with the rules a reader may rely on (counts match rows, lists sorted,
fingerprint form). Every calc payload also carries `calc` (`CalcMeta`), `draft` and the `trace`.
Units: tolerances and property values carry their own unit field; counts are dimensionless.
Errors: `pydantic.ValidationError` for every violated rule.
"""

from collections import Counter
from collections.abc import Iterable
from typing import Annotated, Any, Literal, Self

from eng_contract.kinds import NEUTRAL_KINDS
from eng_contract.refs import RefString
from eng_contract.trace import Trace
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, StringConstraints, model_validator

from eng_harness.calc import CalcStatus

__all__ = ["CALC_KINDS", "CalcMeta", "CalcPayload", "ExpectedEffects", "ModelDiff", "ModelFingerprint"]

_Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_Str = Annotated[str, StringConstraints(min_length=1, max_length=200)]
_Ptr = Annotated[str, StringConstraints(pattern=r"^(/([^~/]|~[01])*)*$")]
_Count = Annotated[int, Field(ge=0)]
_Ratio = Annotated[float, Field(ge=0)] | None


class _P(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


def _ordered(items: Iterable[Any], what: str) -> None:
    keys = list(items)
    if keys != sorted(set(keys)):
        raise ValueError(f"{what} must be sorted and unique")


class CalcMeta(_P):
    """Identity of the calc that made a result: id, version, content hash and status at run time."""

    id: Annotated[str, StringConstraints(pattern=r"^harness\.[a-z][a-z0-9_]*$")]
    version: Annotated[int, Field(ge=1, le=9999)]
    content_sha256: _Sha
    status: CalcStatus


class CalcPayload(_P):
    """Base of the calc payloads; the trace must belong to the calc named in `calc`."""

    calc: CalcMeta
    draft: StrictBool
    trace: Trace

    @model_validator(mode="after")
    def _trace_is_the_calcs(self) -> Self:
        t, c = self.trace, self.calc
        if (t.calc_id, t.calc_version, t.content_sha256) != (c.id, str(c.version), c.content_sha256):
            raise ValueError("trace calc_id, calc_version and content_sha256 must be those of calc")
        return self


class FpSection(_P):
    """One hashed section of a fingerprint."""

    kind: _Str
    result_id: _Str
    items: _Count
    sha256: _Sha
    complete: StrictBool


class ModelFingerprint(CalcPayload):
    """`harness.model_fingerprint/1` (4.6)."""

    method: Literal["harness.fp/1"]
    model_id: _Str
    model_revision: _Count
    sections: list[FpSection]
    covered: list[_Str]
    complete: StrictBool
    fingerprint: Annotated[str, StringConstraints(pattern=r"^fp1:[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def _check(self) -> Self:
        kinds = [s.kind for s in self.sections]
        _ordered(kinds, "sections")
        if self.covered != kinds:
            raise ValueError("covered must list the kinds of sections")
        if self.complete != all(s.complete for s in self.sections):
            raise ValueError("complete must be the conjunction of the sections")
        return self


class Side(_P):
    """One side of a comparison."""

    model_id: _Str
    model_revision: _Count
    covered: list[_Str]


class Tolerance(_P):
    """A tolerance taken from the design basis."""

    value: Annotated[float, Field(ge=0)]
    unit: _Str
    ref: RefString


class PropertyRow(_P):
    """One compared property (rule D3 to D5)."""

    pointer: _Ptr
    before: JsonValue
    after: JsonValue
    unit: str | None
    quantity_kind: str | None
    tolerance: _Ratio
    rule: _Str


class WithinRow(PropertyRow):
    """A property equal within tolerance, with its object."""

    section: _Str
    key: list[str]


class Change(_P):
    """An object that was added, removed, changed or ambiguous."""

    section: _Str
    key: list[str]
    change: Literal["added", "removed", "changed", "ambiguous"]
    before: JsonValue
    after: JsonValue
    properties: list[PropertyRow]

    @model_validator(mode="after")
    def _check(self) -> Self:
        if (self.change == "changed") != bool(self.properties):
            raise ValueError("properties are set exactly for a changed object")
        return self


class SectionCounts(_P):
    """Per section tally of a difference report."""

    added: _Count
    removed: _Count
    changed: _Count
    ambiguous: _Count
    unchanged: _Count
    within_tolerance: _Count


class DiffBody(_P):
    """The difference report without calc fields; embedded in the read-back check."""

    before: Side
    after: Side
    tolerances: dict[str, Tolerance]
    changes: list[Change]
    within_tolerance: list[WithinRow]
    not_compared: list[_Str]
    counts: dict[str, SectionCounts]
    identical: StrictBool
    complete: StrictBool

    @model_validator(mode="after")
    def _check(self) -> Self:
        _ordered([(c.section, tuple(c.key)) for c in self.changes], "changes")
        tally = Counter((c.section, c.change) for c in self.changes)
        within = Counter(w.section for w in self.within_tolerance)
        for section in {c.section for c in self.changes} | set(within) | set(self.counts):
            row = self.counts.get(section)
            got = (row.added, row.removed, row.changed, row.ambiguous, row.within_tolerance) if row else None
            want = (*(tally[section, k] for k in ("added", "removed", "changed", "ambiguous")), within[section])
            if got != want:
                raise ValueError(f"counts of {section} do not match the rows")
        if self.identical != (not self.changes and not self.not_compared and self.complete):
            raise ValueError("identical needs no changes, nothing not compared and complete sides")
        return self


class ModelDiff(CalcPayload, DiffBody):
    """`harness.model_diff/1` (4.7)."""


class Effect(_P):
    """One expected effect of a change set on a model section."""

    item_id: _Str
    section: _Str
    key: list[str]
    op: Literal["set", "add", "remove"]
    pointer: _Ptr | None = None
    value: JsonValue = None
    unit: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.section not in NEUTRAL_KINDS or not self.section.startswith("model."):
            raise ValueError(f"section {self.section!r} is not a neutral model kind")
        has_value = "value" in self.model_fields_set
        if self.op == "set" and (self.pointer is None or not has_value):
            raise ValueError("set needs a pointer and a value")
        if self.op == "add" and (self.pointer is not None or not isinstance(self.value, dict)):
            raise ValueError("add needs an object value and no pointer")
        if self.op == "remove" and (self.pointer is not None or has_value):
            raise ValueError("remove takes neither pointer nor value")
        return self


class ExpectedEffects(_P):
    """`harness.expected_effects/1` (4.8): what a change set should have done; made by spec 0007."""

    change_set: RefString
    model_id: _Str
    effects: list[Effect]

    @model_validator(mode="after")
    def _check(self) -> Self:
        ids = [e.item_id for e in self.effects]
        if duplicated := sorted({i for i in ids if ids.count(i) > 1}):
            raise ValueError(f"duplicate item_id: {duplicated}")
        return self


CALC_KINDS: dict[str, type[BaseModel]] = {
    "harness.model_fingerprint/1": ModelFingerprint,
    "harness.model_diff/1": ModelDiff,
    "harness.expected_effects/1": ExpectedEffects,
}
"""The calc kinds by name, registered in `eng_harness._kinds`."""
