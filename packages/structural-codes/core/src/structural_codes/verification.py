"""Verification case files, the tolerance and the verification runner (spec 0001 section 4.9; AC30 to AC32).

Purpose: evaluate each case of a check's case file in `trial` mode, compare with the expected numbers and list the
unmet conditions of 10-structural-codes section 6. R1 module: a mistake here lets an unverified check look verified.
Units: an expected quantity's unit must equal the result's unit (no conversion).
Errors: `VerificationDataError` for an invalid case file or a file for another check.
"""

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from eng_contract.cited import Cited
from eng_contract.errors import ContractError
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.verdicts import Subject, VerdictStatus
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

from structural_codes._runner import evaluate
from structural_codes._yaml import load_yaml
from structural_codes.check import Check
from structural_codes.content_hash import content_hash
from structural_codes.errors import VerificationDataError
from structural_codes.pack import Pack, Registry

__all__ = ["Case", "CaseFile", "VerificationReport", "compare", "verify_check", "verify_pack"]

DEFAULT_REL_TOL = Cited(value=0.005, unit="1", source="10-structural-codes §6 default relative tolerance")  # 0.5 %

_Text = Annotated[str, StringConstraints(min_length=1)]
_Label = _Text | int  # an edition, page or example number may be written as a number in YAML


class _Strict(BaseModel):
    """Base of the case-file models: frozen, unknown fields refused, no NaN or infinity."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class _Book(_Strict):
    title: _Text
    edition: _Label
    page: _Label
    example: _Label


class _CodeExample(_Strict):
    document: _Text
    edition: _Label
    example: _Label


class _Source(_Strict):
    """Where a case comes from; which fields are allowed depends on the case kind (spec 4.9.1, AC30)."""

    derivation: _Text | None = None
    book: _Book | None = None
    code_example: _CodeExample | None = None
    program: _Text | None = None
    program_version: _Text | None = None
    record: _Text | None = None
    status: Literal["needs_local_test"] | None = None
    assumption_differences: tuple[_Text, ...] = ()


class _Expect(_Strict):
    """An expected quantity: `abs_tol` is required; `rel_tol` defaults to `DEFAULT_REL_TOL`."""

    value: float
    unit: _Text
    abs_tol: Annotated[float, Field(ge=0)]
    rel_tol: Annotated[float, Field(ge=0)] | None = None


class _Expected(_Strict):
    status: VerdictStatus
    values: dict[str, _Expect] = {}


class Case(_Strict):
    """One verification case. `covers` (boundary cases only) names the precondition or gap ids it exercises."""

    id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.-]+$")]
    kind: Literal["hand_check", "worked_example", "program_comparison", "boundary"]
    source: _Source = _Source()
    subject: Subject
    inputs: dict[str, Any]
    expected: _Expected
    covers: tuple[_Text, ...] = ()

    @model_validator(mode="after")
    def _source_matches_kind(self) -> Self:
        given = {n for n in self.source.model_fields_set if getattr(self.source, n) is not None}
        given.discard("assumption_differences")
        program = {"program", "program_version"}
        allowed_by_kind: dict[str, list[set[str]]] = {
            "hand_check": [{"derivation"}],
            "worked_example": [{"book"}, {"code_example"}],
            "program_comparison": [program | {"record"}, program | {"status"}],
            "boundary": [set()],
        }
        if given not in allowed_by_kind[self.kind] or (
            self.kind != "program_comparison" and self.source.assumption_differences
        ):
            raise ValueError(f"case {self.id}: source fields {sorted(given)} do not fit kind {self.kind}")
        return self


class _NotAvailable(_Strict):
    not_available: _Text


class _Review(_Strict):
    content_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    author: _Text
    reviewer: _Text
    date: dt.date
    boundary_tests: tuple[_Text, ...] = ()
    property_tests: tuple[_Text, ...] = ()


class CaseFile(_Strict):
    """The case file of one check (spec 4.9.1)."""

    format: Literal["structural-codes-verification/1"]
    check_id: _Text
    program_comparison: _NotAvailable | None = None
    cases: tuple[Case, ...]
    review: _Review | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        ids = [c.id for c in self.cases]
        if len(set(ids)) != len(ids):
            raise ValueError("a case id is used twice")
        if self.program_comparison is not None and any(c.kind == "program_comparison" for c in self.cases):
            raise ValueError("program_comparison.not_available contradicts the program_comparison cases")
        return self

    @classmethod
    def from_yaml(cls, text: str) -> Self:
        """Parse and validate a case file.

        Raises:
            VerificationDataError: invalid YAML, a duplicate key or any schema violation (AC30).
        """
        try:
            return cls.model_validate(load_yaml(text, VerificationDataError))
        except ValidationError as exc:
            raise VerificationDataError(f"invalid case file: {exc}") from exc

    @classmethod
    def load(cls, path: Path) -> Self:
        """Read and parse the case file at `path`.

        Raises:
            VerificationDataError: the file cannot be read, or `from_yaml` rejects it.
        """
        try:
            return cls.from_yaml(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            raise VerificationDataError(f"cannot read {path.name}: {exc}") from exc


@dataclass(frozen=True, slots=True)
class CaseResult:
    """Outcome of one case: `pass`, `fail` or `pending` (a program comparison that needs a local test)."""

    id: str
    kind: str
    outcome: Literal["pass", "fail", "pending"]
    detail: str = ""


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """The case results and every unmet requirement of spec 4.9.4, numbered as there, for one content hash."""

    check_id: str
    content_sha256: str
    cases: tuple[CaseResult, ...]
    unmet: tuple[str, ...]

    @property
    def verified(self) -> bool:
        """True only when no requirement is unmet."""
        return not self.unmet


def compare(actual: float, expected: float, *, abs_tol: float, rel_tol: float = DEFAULT_REL_TOL.value) -> bool:
    """True iff `abs(actual - expected) <= max(rel_tol * abs(expected), abs_tol)` (AC31); NaN never passes.

    Units: `actual`, `expected` and `abs_tol` share one unit; `rel_tol` is a fraction.
    """
    return abs(actual - expected) <= max(rel_tol * abs(expected), abs_tol)


def _actuals(payload: VerdictSet) -> dict[str, tuple[float, str]]:
    """Numeric values of the single trace by name with their units, plus the governing verdict's names."""
    trace = payload.traces[0]
    found: dict[str, tuple[float, str]] = {
        i.name: (float(i.value), i.unit or "1")
        for i in trace.inputs
        if isinstance(i.value, int | float) and not isinstance(i.value, bool)
    }
    found.update({c.name: (float(c.cited.value), c.cited.unit) for c in trace.constants})
    found.update({s.name: (float(s.value), s.unit or "1") for s in trace.steps if not isinstance(s.value, bool)})
    sized = next((v for v in payload.verdicts if v.governing), None)
    if sized is not None:
        quantities = {"demand": sized.demand, "capacity": sized.capacity}
        found.update({n: (q.value, q.unit) for n, q in quantities.items() if q is not None})
        if sized.ratio is not None:
            found["ratio"] = (sized.ratio, "1")
    return found


def _run_case(check_id: str, case: Case, registry: Registry) -> CaseResult:
    """Evaluate one case in `trial` mode and compare its status and values; a refused evaluation fails the case."""
    if case.kind == "program_comparison" and case.source.status == "needs_local_test":
        return CaseResult(case.id, case.kind, "pending", "needs local test")
    try:
        payload = evaluate(check_id, case.inputs, subject=case.subject, mode="trial", registry=registry).payload
    except ContractError as exc:
        return CaseResult(case.id, case.kind, "fail", f"{exc.detail.code.value}: {exc.detail.message}")
    status, actuals, problems = payload.traces[0].status, _actuals(payload), []
    if status is not case.expected.status:
        problems.append(f"status {status.value if status else None}, expected {case.expected.status.value}")
    for name, want in case.expected.values.items():
        rel = DEFAULT_REL_TOL.value if want.rel_tol is None else want.rel_tol
        if name not in actuals:
            problems.append(f"{name}: no such value in the result")
        elif actuals[name][1] != want.unit:
            problems.append(f"{name}: unit {actuals[name][1]}, expected {want.unit}")
        elif not compare(actuals[name][0], want.value, rel_tol=rel, abs_tol=want.abs_tol):
            got = actuals[name][0]
            problems.append(
                f"{name}: {got:.10g}, expected {want.value:.10g} (abs_tol {want.abs_tol:g}, rel_tol {rel:g})"
            )
    return CaseResult(case.id, case.kind, "fail" if problems else "pass", "; ".join(problems))


def _unmet(check: Check, cases: CaseFile, results: tuple[CaseResult, ...], digest: str) -> tuple[str, ...]:
    """The unmet conditions of spec 4.9.4 in order; whether listed tests pass is CI's job, only listing is checked."""
    outcome = {r.id: r.outcome for r in results}
    kind = {k: [c for c in cases.cases if c.kind == k] for k in ("worked_example", "program_comparison", "boundary")}
    review, unmet = cases.review, []
    if not any(outcome[c.id] == "pass" for c in kind["worked_example"]):
        unmet.append("(1) no passing worked_example case (a hand_check does not count)")
    if kind["program_comparison"]:
        weak = [
            c.id for c in kind["program_comparison"] if outcome[c.id] != "pass" or not c.source.assumption_differences
        ]
        if weak:
            unmet.append(f"(2) program comparisons not passing or without assumption differences: {', '.join(weak)}")
    elif cases.program_comparison is None:
        unmet.append("(2) no program_comparison case and no program_comparison.not_available")
    covered = {p for c in kind["boundary"] for p in c.covers}
    covered |= {t.partition(":")[0].strip() for t in review.boundary_tests} if review else set()
    paths = [p.id for p in check.preconditions] + [g.id for g in check.meta.gaps]
    if missing := [p for p in paths if p not in covered]:
        unmet.append(f"(3) no boundary case or listed boundary test for: {', '.join(missing)}")
    if review is None or not review.property_tests:
        unmet.append("(4) no listed property test")
    if review is None:
        unmet.append("(5) no review block")
    elif review.content_sha256 != digest:
        unmet.append("(5) the review is not for the current content hash")
    elif review.reviewer == review.author:
        unmet.append("(5) the reviewer is the author")
    if failing := [r.id for r in results if r.outcome == "fail"]:
        unmet.append(f"(6) failing cases: {', '.join(failing)}")
    return tuple(unmet)


def verify_check(check: Check, cases: CaseFile, *, registry: Registry | None = None) -> VerificationReport:
    """Run every case of `cases` against `check` (AC32); `registry` must hold it, `None` uses `Registry.discover()`.

    Raises:
        VerificationDataError: the case file names another check.
    """
    if cases.check_id != check.meta.check_id:
        raise VerificationDataError(f"case file is for {cases.check_id}, not {check.meta.check_id}")
    known = registry or Registry.discover()
    results = tuple(_run_case(check.meta.check_id, c, known) for c in cases.cases)
    digest = content_hash(check)
    return VerificationReport(check.meta.check_id, digest, results, _unmet(check, cases, results, digest))


def verify_pack(pack: Pack, directory: Path) -> tuple[VerificationReport, ...]:
    """Verify every check of `pack` with `<directory>/<check_id>.yaml`, in check_id order (no file: not verified).

    Raises:
        VerificationDataError: a case file is invalid or names another check.
    """
    registry, reports = Registry.of([pack]), []
    for check in sorted(pack.checks, key=lambda c: c.meta.check_id):
        path = directory / f"{check.meta.check_id}.yaml"
        if path.is_file():
            reports.append(verify_check(check, CaseFile.load(path), registry=registry))
        else:
            missing = (f"no case file {path.name}",)
            reports.append(VerificationReport(check.meta.check_id, content_hash(check), (), missing))
    return tuple(reports)
