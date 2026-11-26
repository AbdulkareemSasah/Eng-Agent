"""Verify a Revit column update plan against before and after reads (spec 0013 §4.4.6, B1 to B4)."""

from fractions import Fraction
from typing import Any, Literal

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.kinds.model import Sections
from eng_contract.params import eng_param
from eng_contract.refs import JsonPointer
from pydantic import BaseModel, ConfigDict

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs._compare import as_fraction
from eng_harness.calcs.column_design.column_select import read_tolerance
from eng_harness.calcs.column_design.revit_update import _role_mm
from eng_harness.kinds.column_design import RevitColumnUpdate
from eng_harness.kinds.revit import RevitStructure

__all__ = ["BASIS_FIELDS", "RevitReadbackBody", "RevitReadbackInput", "revit_column_readback"]

_LENGTH = "compare.length_mm"
BASIS_FIELDS = (_LENGTH,)
_REFS = ("plan", "before", "after", "basis", "sections")
_IssueCode = Literal["ELEMENT_MISSING", "TYPE_MISMATCH", "VALUE_MISMATCH", "UNEXPECTED_TYPE_CHANGE", "NOT_READ"]


def _ref(kind: str, *, stale_ok: bool = False) -> Any:
    return eng_param(ref_capable=True, ref_kinds={kind}, engineering_quantity=True, stale_ok=stale_ok)


class RevitReadbackInput(CalcInput):
    """The plan, two Revit reads, the plan's ETABS sections and the design basis."""

    plan: RevitColumnUpdate = _ref("harness.revit_column_update/1")
    before: RevitStructure = _ref("harness.revit_structure/1", stale_ok=True)
    after: RevitStructure = _ref("harness.revit_structure/1")
    basis: DesignBasis = _ref("basis.design_basis/1")
    sections: Sections = _ref("model.sections/1")


class _Issue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    unique_id: str
    code: _IssueCode


class RevitReadbackBody(BaseModel):
    """The read-back payload without its calc identity and trace."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["PASS", "FAIL"]
    issues: list[_Issue]
    before_revision: int
    after_revision: int


def _type_issues(
    inp: RevitReadbackInput, sections_id: str, tolerance: Fraction
) -> dict[tuple[str, str], set[_IssueCode]]:
    """B2 and B4 compare each planned new type once, retaining each issue code once."""
    sections = inp.sections.model_dump(mode="json")
    after_types = {(row.family, row.name): row for row in inp.after.types}
    issues: dict[tuple[str, str], set[_IssueCode]] = {}
    for target in inp.plan.expected.types:
        identity = (target.family, target.name)
        actual = after_types.get(identity)
        codes = issues.setdefault(identity, set())
        for role, ref in target.roles.items():
            source, _, pointer = ref.partition("#")
            tokens = JsonPointer.parse(pointer, field="plan")
            match tokens:
                case ("frame_sections", _, "shape", "b_mm" | "h_mm" | "D_mm") if source == sections_id:
                    wanted = as_fraction(JsonPointer.evaluate(sections, tokens, field="plan"))
                case _:
                    wanted = None
            if wanted is None:
                raise ContractError(
                    ErrorCode.INVALID_ARGUMENT, "planned role must reference a length in sections", field="plan"
                )
            value = _role_mm(actual.parameters.get(role)) if actual is not None else None
            if value is None:
                codes.add("NOT_READ")
            elif abs(value - wanted) > tolerance:
                codes.add("VALUE_MISMATCH")
    return issues


@calc(
    id="harness.revit_column_readback",
    version=1,
    output_kind="harness.revit_column_readback/1",
    title="Revit column read-back against the update plan",
    method_source="eng-harness spec 0013 §4.4.6 (B1 to B4)",
    verification="draft",
)
def revit_column_readback(inp: RevitReadbackInput, meta: InputMeta, trace: TraceBuilder) -> RevitReadbackBody:
    """Check type identities, attribute new-type issues to present assignees and detect other type changes."""
    for field in _REFS:
        if field not in meta.refs:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"{field} must be a record reference", field=field)
    before_ref, after_ref = meta.refs["before"], meta.refs["after"]
    before_revision, after_revision = before_ref.model_revision, after_ref.model_revision
    if before_ref.model_id is None or before_revision is None:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "before must identify a model and revision", field="before")
    if after_ref.model_id != before_ref.model_id or after_revision is None:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "after must name a revision of the same model", field="after")

    tolerance = read_tolerance(inp.basis)
    type_issues = _type_issues(inp, meta.refs["sections"].result_id, tolerance)
    before = {row.unique_id: row for row in inp.before.elements}
    after = {row.unique_id: row for row in inp.after.elements}
    planned_ids = {row.unique_id for row in inp.plan.expected.elements}
    issues: list[_Issue] = []
    for target in inp.plan.expected.elements:
        identity = target.unique_id
        if (actual := after.get(identity)) is None:
            issues.append(_Issue(unique_id=identity, code="ELEMENT_MISSING"))
            continue
        if target.type_id is not None:
            if str(actual.type_id) != target.type_id:
                issues.append(_Issue(unique_id=identity, code="TYPE_MISMATCH"))
        elif target.family is not None and target.type_name is not None:
            planned_type = (target.family, target.type_name)
            if (actual.family, actual.type_name) != planned_type:
                issues.append(_Issue(unique_id=identity, code="TYPE_MISMATCH"))
            issues.extend(_Issue(unique_id=identity, code=code) for code in type_issues.get(planned_type, ()))

    for identity in (before.keys() & after.keys()) - planned_ids:
        if before[identity].type_id != after[identity].type_id:
            issues.append(_Issue(unique_id=identity, code="UNEXPECTED_TYPE_CHANGE"))
    issues.sort(key=lambda issue: (issue.unique_id, issue.code))
    status: Literal["PASS", "FAIL"] = "PASS" if not issues and after_revision > before_revision else "FAIL"

    trace.input("before_revision", before_revision, ref=before_ref.result_id)
    trace.input("after_revision", after_revision, ref=after_ref.result_id)
    trace.input("planned_elements", len(planned_ids), ref=meta.refs["plan"].result_id)
    trace.input("frame_sections", len(inp.sections.frame_sections), ref=meta.refs["sections"].result_id)
    trace.input(
        "compare_length_mm", float(tolerance), unit="mm", ref=f"{meta.refs['basis'].result_id}#/fields/{_LENGTH}"
    )
    trace.step(
        "issues",
        len(issues),
        formula="planned element and role issues plus unplanned type changes",
        source="spec 0013 §4.4.6 B1 to B4",
        uses=["before_revision", "after_revision", "planned_elements", "frame_sections", "compare_length_mm"],
    )
    trace.step(
        "status",
        status,
        formula="PASS if there are no issues and after_revision exceeds before_revision",
        source="spec 0013 §4.4.6",
        uses=["issues", "before_revision", "after_revision"],
    )
    trace.output("status", "issues", "before_revision", "after_revision")
    return RevitReadbackBody(
        status=status, issues=issues, before_revision=before_revision, after_revision=after_revision
    )
