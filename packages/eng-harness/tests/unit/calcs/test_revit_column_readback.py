"""Unit tests of `harness.revit_column_readback` refusals, tolerance boundary, identities and ordering.

Plan 0013 T8; spec 0013 section 4.4.6 (B1 to B4). The golden cases pin one body per issue code; these tests pin
the `INVALID_ARGUMENT` refusals (missing record references, the before/after model and revision identity, the
`compare.length_mm` basis field, planned role references that are not lengths in the sections record), the exact
tolerance boundary (equal, just inside, just outside, both sides), the `type_id` and (`family`, `type_name`)
identity comparisons in both sort orders, per-assignee issue attribution, the (`unique_id`, `code`) issue
ordering, the B3 scope, the revision comparison of the status, and the trace, registration and input schema.
Every value is synthetic.
"""

from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode

from eng_harness.calc import InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.column_design.revit_readback import (
    BASIS_FIELDS,
    RevitReadbackInput,
    revit_column_readback,
)

KINDS = {
    "plan": "harness.revit_column_update/1",
    "before": "harness.revit_structure/1",
    "after": "harness.revit_structure/1",
    "basis": "basis.design_basis/1",
    "sections": "model.sections/1",
}
REFS = {name: f"res_01KRC{'0' * 20}{n}" for n, name in enumerate(KINDS, 1)}
SRC = "engineer:synthetic@2026-01-01T00:00:00.000Z"
SHA = "c" * 64
MODEL = "mdl_synthetic_0000000000000001"
MODEL_EARLIER = "mdl_synthetic_0000000000000000"
MODEL_LATER = "mdl_synthetic_0000000000000002"


def _meta_without(
    missing: str | None = None,
    *,
    before_model: str | None = MODEL,
    before_rev: int | None = 1,
    after_model: str | None = MODEL,
    after_rev: int | None = 2,
) -> InputMeta:
    """`InputMeta` for every referenced input, optionally without one entry; before/after name model revisions."""
    return InputMeta(
        refs={
            name: RefMeta(
                result_id=result_id,
                ref=result_id,
                kind=kind,
                complete=True,
                model_id={"before": before_model, "after": after_model}.get(name),
                model_revision={"before": before_rev, "after": after_rev}.get(name),
                parents=(),
                producer_tool="fixture_tool",
            )
            for name, kind, result_id in ((n, KINDS[n], REFS[n]) for n in KINDS)
            if name != missing
        }
    )


def _element(uid: str, eid: int, family: str, type_id: int, type_name: str) -> dict[str, Any]:
    """One structural column element row."""
    return {
        "unique_id": uid,
        "element_id": eid,
        "category": "column",
        "family": family,
        "type_id": type_id,
        "type_name": type_name,
        "level_id": 1,
        "level_name": "L1",
        "location_kind": "point",
        "i": None,
        "j": None,
        "rotation_deg": 0,
        "parameters": {},
    }


def _type_row(
    tid: int, family: str, name: str, params: dict[str, Any], instances: tuple[int, ...] = ()
) -> dict[str, Any]:
    """One family type row with sorted instance ids."""
    return {
        "type_id": tid,
        "family": family,
        "name": name,
        "instance_ids": sorted(set(instances)),
        "parameters": params,
    }


def _qty(value: float, unit: str = "mm") -> dict[str, Any]:
    return {"value": value, "unit": unit}


def _old_type(instances: tuple[int, ...] = (101,)) -> dict[str, Any]:
    """The pre-update type row the fixtures replace."""
    return _type_row(21, "F1", "Told", {"section_b": _qty(400), "section_h": _qty(400)}, instances)


def _role_ref(pointer: str, source: str | None = None) -> str:
    """A role reference against the sections result (or another result, for the refusal tests)."""
    return f"{source or REFS['sections']}#{pointer}"


def _roles() -> dict[str, str]:
    """The two role references of the rectangular C30S fixture section."""
    return {
        "section_b": _role_ref("/frame_sections/0/shape/b_mm"),
        "section_h": _role_ref("/frame_sections/0/shape/h_mm"),
    }


def _plan(elements: list[dict[str, Any]], types: list[dict[str, Any]]) -> dict[str, Any]:
    """A minimal update plan carrying only the read-back expectations the calc reads."""
    return {
        "calc": {"id": "harness.revit_column_update", "version": 1, "content_sha256": SHA, "status": "draft"},
        "draft": True,
        "trace": {
            "calc_id": "harness.revit_column_update",
            "calc_version": "1",
            "content_sha256": SHA,
            "inputs": [],
            "constants": [],
            "steps": [],
            "outputs": [],
        },
        "new_types": [],
        "assignments": [],
        "no_change": [],
        "not_updatable": [],
        "orientation": [],
        "complete": True,
        "expected": {"elements": elements, "types": types},
    }


def _basis(value: Any = 5, confirmed: bool = True) -> dict[str, Any]:
    return {
        "template": None,
        "fields": {
            "compare.length_mm": {
                "value": value,
                "unit": "mm",
                "source": SRC,
                "confirmed": confirmed,
                "citation": None,
            }
        },
    }


def _fields() -> dict[str, Any]:
    """A minimal passing input: u-a has the planned F1/C30S with both roles read exactly."""
    return {
        "plan": _plan(
            [{"unique_id": "u-a", "family": "F1", "type_name": "C30S"}],
            [{"family": "F1", "name": "C30S", "roles": _roles()}],
        ),
        "before": {"elements": [_element("u-a", 101, "F1", 21, "Told")], "types": [_old_type()]},
        "after": {
            "elements": [_element("u-a", 101, "F1", 30, "C30S")],
            "types": [
                _old_type(()),
                _type_row(30, "F1", "C30S", {"section_b": _qty(300), "section_h": _qty(300)}, (101,)),
            ],
        },
        "basis": _basis(),
        "sections": {
            "frame_sections": [
                {"name": "C30S", "material": "C30", "shape": {"type": "rectangular", "b_mm": 300, "h_mm": 300}}
            ],
            "area_sections": [],
        },
    }


def _run(fields: dict[str, Any], meta: InputMeta | None = None, trace: TraceBuilder | None = None) -> dict[str, Any]:
    return revit_column_readback(
        RevitReadbackInput.model_validate(fields), meta or _meta_without(), trace or TraceBuilder()
    ).model_dump(mode="json")


def test_pass_exact_payload() -> None:
    assert _run(_fields()) == {"status": "PASS", "issues": [], "before_revision": 1, "after_revision": 2}


def test_revisions_echoed() -> None:
    body = _run(_fields(), _meta_without(before_rev=4, after_rev=9))
    assert body == {"status": "PASS", "issues": [], "before_revision": 4, "after_revision": 9}


@pytest.mark.parametrize("name", sorted(KINDS))
def test_missing_reference_refused(name: str) -> None:
    with pytest.raises(ContractError) as caught:
        _run(_fields(), _meta_without(name))
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.message) == (
        ErrorCode.INVALID_ARGUMENT,
        name,
        f"{name} must be a record reference",
    )


@pytest.mark.parametrize(
    ("model", "revision"),
    [(None, 1), (MODEL, None)],
    ids=["no-model", "no-revision"],
)
def test_before_without_model_or_revision_refused(model: str | None, revision: int | None) -> None:
    with pytest.raises(ContractError) as caught:
        _run(_fields(), _meta_without(before_model=model, before_rev=revision))
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.message) == (
        ErrorCode.INVALID_ARGUMENT,
        "before",
        "before must identify a model and revision",
    )


@pytest.mark.parametrize(
    ("model", "revision"),
    [(MODEL_EARLIER, 2), (MODEL_LATER, 2), (MODEL, None)],
    ids=["other-model-sorts-before", "other-model-sorts-after", "no-revision"],
)
def test_after_wrong_model_or_no_revision_refused(model: str | None, revision: int | None) -> None:
    with pytest.raises(ContractError) as caught:
        _run(_fields(), _meta_without(after_model=model, after_rev=revision))
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.message) == (
        ErrorCode.INVALID_ARGUMENT,
        "after",
        "after must name a revision of the same model",
    )


@pytest.mark.parametrize(
    ("basis", "why"),
    [
        ({"template": None, "fields": {}}, "is missing (no default)"),
        (_basis(confirmed=False), "is not confirmed"),
        (_basis(value="5"), "must be a number >= 0"),
        (_basis(value=-0.5), "must be a number >= 0"),
    ],
)
def test_basis_field_refused(basis: dict[str, Any], why: str) -> None:
    fields = _fields()
    fields["basis"] = basis
    with pytest.raises(ContractError) as caught:
        _run(fields)
    detail = caught.value.detail
    assert (detail.code, detail.field) == (ErrorCode.INVALID_ARGUMENT, "basis.fields.compare.length_mm")
    assert detail.message == f"basis field compare.length_mm {why}"
    assert detail.hint == "set and confirm compare.length_mm in the design basis"


def test_role_ref_must_name_the_sections_result() -> None:
    """B2 resolves each planned role against the sections record the plan was written from."""
    fields = _fields()
    fields["plan"]["expected"]["types"][0]["roles"]["section_b"] = _role_ref(
        "/frame_sections/0/shape/b_mm", REFS["plan"]
    )
    with pytest.raises(ContractError) as caught:
        _run(fields)
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.message) == (
        ErrorCode.INVALID_ARGUMENT,
        "plan",
        "planned role must reference a length in sections",
    )


def test_role_ref_must_point_at_a_length() -> None:
    """A role pointing at a non-length member (here the shape tag) is not a length in sections."""
    fields = _fields()
    fields["plan"]["expected"]["types"][0]["roles"]["section_b"] = _role_ref("/frame_sections/0/shape/type")
    with pytest.raises(ContractError) as caught:
        _run(fields)
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.message) == (
        ErrorCode.INVALID_ARGUMENT,
        "plan",
        "planned role must reference a length in sections",
    )


def test_role_pointer_malformed_refused() -> None:
    fields = _fields()
    fields["plan"]["expected"]["types"][0]["roles"]["section_b"] = _role_ref("frame_sections/0/shape/b_mm")
    with pytest.raises(ContractError) as caught:
        _run(fields)
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.message) == (
        ErrorCode.REF_POINTER_INVALID,
        "plan",
        "a pointer must be empty or start with '/'",
    )
    assert detail.received == "frame_sections/0/shape/b_mm"


def test_role_index_out_of_range_refused() -> None:
    fields = _fields()
    fields["plan"]["expected"]["types"][0]["roles"]["section_b"] = _role_ref("/frame_sections/5/shape/b_mm")
    with pytest.raises(ContractError) as caught:
        _run(fields)
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.message) == (
        ErrorCode.REF_POINTER_INVALID,
        "plan",
        "array index out of range",
    )
    assert detail.received == "5"


def test_circular_d_role() -> None:
    """B2 resolves the `D_mm` member of a circular section exactly like the rectangular members."""
    fields = _fields()
    fields["sections"] = {
        "frame_sections": [{"name": "C40R", "material": "C30", "shape": {"type": "circular", "D_mm": 400}}],
        "area_sections": [],
    }
    fields["plan"]["expected"] = {
        "elements": [{"unique_id": "u-a", "family": "F1", "type_name": "C40R"}],
        "types": [{"family": "F1", "name": "C40R", "roles": {"section_D": _role_ref("/frame_sections/0/shape/D_mm")}}],
    }
    fields["after"]["elements"] = [_element("u-a", 101, "F1", 30, "C40R")]
    fields["after"]["types"] = [_old_type(()), _type_row(30, "F1", "C40R", {"section_D": _qty(400)}, (101,))]
    assert _run(fields) == {"status": "PASS", "issues": [], "before_revision": 1, "after_revision": 2}
    fields["after"]["types"][1]["parameters"]["section_D"] = {"value": 406, "unit": "mm"}
    assert _run(fields) == {
        "status": "FAIL",
        "issues": [{"unique_id": "u-a", "code": "VALUE_MISMATCH"}],
        "before_revision": 1,
        "after_revision": 2,
    }


@pytest.mark.parametrize(
    ("read", "codes"),
    [
        (300, []),
        (305, []),
        (295, []),
        (304.75, []),
        (295.25, []),
        (305.25, ["VALUE_MISMATCH"]),
        (294.75, ["VALUE_MISMATCH"]),
    ],
    ids=["exact", "at-plus", "at-minus", "inside-plus", "inside-minus", "outside-plus", "outside-minus"],
)
def test_tolerance_boundary(read: float, codes: list[str]) -> None:
    """B2 flags a role only beyond `compare.length_mm`: equal and inside pass, outside fails, both sides."""
    fields = _fields()
    fields["after"]["types"][1]["parameters"]["section_b"] = {"value": read, "unit": "mm"}
    body = _run(fields)
    assert body == {
        "status": "PASS" if not codes else "FAIL",
        "issues": [{"unique_id": "u-a", "code": code} for code in codes],
        "before_revision": 1,
        "after_revision": 2,
    }


def test_missing_element_gets_only_element_missing() -> None:
    """B1: a missing planned element gets only `ELEMENT_MISSING`; later assignees are still checked."""
    fields = _fields()
    fields["plan"]["expected"] = {
        "elements": [
            {"unique_id": "u-a", "family": "F1", "type_name": "C30S"},
            {"unique_id": "u-b", "family": "F1", "type_name": "C30S"},
        ],
        "types": [{"family": "F1", "name": "C30S", "roles": _roles()}],
    }
    fields["before"]["elements"].append(_element("u-b", 102, "F1", 21, "Told"))
    fields["after"]["elements"] = [_element("u-b", 102, "F1", 31, "C30S")]
    fields["after"]["types"] = [_old_type(())]
    assert _run(fields) == {
        "status": "FAIL",
        "issues": [
            {"unique_id": "u-a", "code": "ELEMENT_MISSING"},
            {"unique_id": "u-b", "code": "NOT_READ"},
        ],
        "before_revision": 1,
        "after_revision": 2,
    }


@pytest.mark.parametrize(
    ("actual", "codes"),
    [(22, []), (24, ["TYPE_MISMATCH"]), (21, ["TYPE_MISMATCH"])],
    ids=["match", "greater", "smaller"],
)
def test_reuse_type_id(actual: int, codes: list[str]) -> None:
    """B1 checks a reuse expectation by `type_id`, with a mismatch on either side of the planned id."""
    fields = _fields()
    fields["plan"]["expected"] = {"elements": [{"unique_id": "u-a", "type_id": "22"}], "types": []}
    fields["after"]["elements"] = [_element("u-a", 101, "F1", actual, "T22")]
    body = _run(fields)
    assert body == {
        "status": "PASS" if not codes else "FAIL",
        "issues": [{"unique_id": "u-a", "code": code} for code in codes],
        "before_revision": 1,
        "after_revision": 2,
    }


@pytest.mark.parametrize(
    ("family", "name", "codes"),
    [
        ("FM", "C30S", []),
        ("FA", "C30S", ["TYPE_MISMATCH"]),
        ("FZ", "C30S", ["TYPE_MISMATCH"]),
        ("FM", "Other", ["TYPE_MISMATCH"]),
    ],
    ids=["match", "family-before", "family-after", "name-differs"],
)
def test_new_type_identity(family: str, name: str, codes: list[str]) -> None:
    """B1 checks a new-type expectation by (`family`, `type_name`); either member may differ, either way."""
    fields = _fields()
    fields["plan"]["expected"] = {
        "elements": [{"unique_id": "u-a", "family": "FM", "type_name": "C30S"}],
        "types": [{"family": "FM", "name": "C30S", "roles": _roles()}],
    }
    fields["after"]["elements"] = [_element("u-a", 101, family, 30, name)]
    fields["after"]["types"] = [
        _old_type(()),
        _type_row(30, "FM", "C30S", {"section_b": _qty(300), "section_h": _qty(300)}, (101,)),
    ]
    body = _run(fields)
    assert body == {
        "status": "PASS" if not codes else "FAIL",
        "issues": [{"unique_id": "u-a", "code": code} for code in codes],
        "before_revision": 1,
        "after_revision": 2,
    }


def test_value_mismatch_deduped_per_assignee() -> None:
    """B2/B4: two roles off give one `VALUE_MISMATCH` per present assignee, not one per role."""
    fields = _fields()
    fields["plan"]["expected"] = {
        "elements": [
            {"unique_id": "u-a", "family": "F1", "type_name": "C30S"},
            {"unique_id": "u-b", "family": "F1", "type_name": "C30S"},
        ],
        "types": [{"family": "F1", "name": "C30S", "roles": _roles()}],
    }
    fields["before"]["elements"].append(_element("u-b", 102, "F1", 21, "Told"))
    fields["before"]["types"] = [_old_type((101, 102))]
    fields["after"]["elements"].append(_element("u-b", 102, "F1", 30, "C30S"))
    fields["after"]["types"] = [
        _old_type(()),
        _type_row(30, "F1", "C30S", {"section_b": _qty(306), "section_h": _qty(294)}, (101, 102)),
    ]
    assert _run(fields) == {
        "status": "FAIL",
        "issues": [
            {"unique_id": "u-a", "code": "VALUE_MISMATCH"},
            {"unique_id": "u-b", "code": "VALUE_MISMATCH"},
        ],
        "before_revision": 1,
        "after_revision": 2,
    }


@pytest.mark.parametrize(
    "role",
    [
        pytest.param(None, id="missing"),
        pytest.param("not read", id="string"),
        pytest.param(400, id="int"),
        pytest.param({"value": 30.0, "unit": "MPa"}, id="pressure"),
    ],
)
def test_unread_role_kinds(role: Any) -> None:
    """B4: a missing, non-quantity or non-length role reads `NOT_READ`, never compared."""
    fields = _fields()
    params = dict(fields["after"]["types"][1]["parameters"])
    if role is None:
        del params["section_b"]
    else:
        params["section_b"] = role
    fields["after"]["types"][1]["parameters"] = params
    assert _run(fields) == {
        "status": "FAIL",
        "issues": [{"unique_id": "u-a", "code": "NOT_READ"}],
        "before_revision": 1,
        "after_revision": 2,
    }


def test_missing_type_row_unreads_all_roles() -> None:
    """B4: without a row for the planned type in `after.types`, every planned role is unread."""
    fields = _fields()
    fields["after"]["types"] = [_old_type(())]
    assert _run(fields) == {
        "status": "FAIL",
        "issues": [{"unique_id": "u-a", "code": "NOT_READ"}],
        "before_revision": 1,
        "after_revision": 2,
    }


def test_mismatch_and_not_read_combine_per_assignee() -> None:
    """One role off and one unread give both codes for the assignee, ordered by code."""
    fields = _fields()
    fields["after"]["types"][1]["parameters"] = {"section_b": _qty(306)}
    assert _run(fields) == {
        "status": "FAIL",
        "issues": [
            {"unique_id": "u-a", "code": "NOT_READ"},
            {"unique_id": "u-a", "code": "VALUE_MISMATCH"},
        ],
        "before_revision": 1,
        "after_revision": 2,
    }


def test_issues_sort_by_unique_id_then_code() -> None:
    """Issues sort by (`unique_id`, `code`), not by plan order: u-b is planned first, u-aa is unplanned."""
    fields = _fields()
    fields["plan"]["expected"] = {
        "elements": [
            {"unique_id": "u-b", "family": "F1", "type_name": "C30S"},
            {"unique_id": "u-a", "family": "F1", "type_name": "C30S"},
        ],
        "types": [{"family": "F1", "name": "C30S", "roles": _roles()}],
    }
    fields["before"] = {
        "elements": [
            _element("u-a", 101, "F1", 21, "Told"),
            _element("u-aa", 100, "F1", 21, "Told"),
            _element("u-b", 102, "F1", 21, "Told"),
        ],
        "types": [_old_type((100, 101, 102))],
    }
    fields["after"] = {
        "elements": [
            _element("u-a", 101, "F2", 23, "C30S"),
            _element("u-aa", 100, "F1", 22, "C50"),
            _element("u-b", 102, "F2", 23, "C30S"),
        ],
        "types": [
            _old_type(()),
            _type_row(23, "F2", "C30S", {"section_b": _qty(400), "section_h": _qty(400)}, (101, 102)),
            _type_row(30, "F1", "C30S", {"section_b": _qty(300), "section_h": _qty(300)}),
        ],
    }
    assert _run(fields) == {
        "status": "FAIL",
        "issues": [
            {"unique_id": "u-a", "code": "TYPE_MISMATCH"},
            {"unique_id": "u-aa", "code": "UNEXPECTED_TYPE_CHANGE"},
            {"unique_id": "u-b", "code": "TYPE_MISMATCH"},
        ],
        "before_revision": 1,
        "after_revision": 2,
    }


def test_unexpected_change_scope() -> None:
    """B3 covers only unplanned elements present in both reads: same, up, down, added, removed, planned."""
    fields = _fields()
    fields["plan"]["expected"] = {"elements": [{"unique_id": "u-a", "type_id": "30"}], "types": []}
    fields["before"] = {
        "elements": [
            _element("u-a", 101, "F1", 21, "Told"),
            _element("u-down", 104, "F1", 22, "C50"),
            _element("u-remove", 105, "F1", 21, "Told"),
            _element("u-same", 106, "F1", 21, "Told"),
            _element("u-up", 107, "F1", 21, "Told"),
        ],
        "types": [_old_type((101, 105, 106, 107)), _type_row(22, "F1", "C50", {"section_b": _qty(500)}, (104,))],
    }
    fields["after"] = {
        "elements": [
            _element("u-a", 101, "F1", 30, "C30S"),
            _element("u-add", 108, "F1", 21, "Told"),
            _element("u-down", 104, "F1", 21, "Told"),
            _element("u-same", 106, "F1", 21, "Told"),
            _element("u-up", 107, "F1", 22, "C50"),
        ],
        "types": [
            _old_type((106, 108)),
            _type_row(22, "F1", "C50", {"section_b": _qty(500)}, (107,)),
            _type_row(30, "F1", "C30S", {"section_b": _qty(300), "section_h": _qty(300)}, (101,)),
        ],
    }
    assert _run(fields) == {
        "status": "FAIL",
        "issues": [
            {"unique_id": "u-down", "code": "UNEXPECTED_TYPE_CHANGE"},
            {"unique_id": "u-up", "code": "UNEXPECTED_TYPE_CHANGE"},
        ],
        "before_revision": 1,
        "after_revision": 2,
    }


@pytest.mark.parametrize(
    ("before_rev", "after_rev"),
    [(2, 2), (2, 1)],
    ids=["equal", "reversed"],
)
def test_pass_needs_a_later_after_revision(before_rev: int, after_rev: int) -> None:
    """Without issues, `status` is still `FAIL` unless `after` is at a later revision than `before`."""
    body = _run(_fields(), _meta_without(before_rev=before_rev, after_rev=after_rev))
    assert body == {
        "status": "FAIL",
        "issues": [],
        "before_revision": before_rev,
        "after_revision": after_rev,
    }


def test_trace_records_inputs_issues_and_status() -> None:
    """The trace pins every input, step and output name, value, unit, reference, formula, source and use."""
    fields = _fields()
    fields["plan"]["expected"]["elements"].append({"unique_id": "u-c", "type_id": "22"})
    fields["sections"]["frame_sections"].append(
        {"name": "C50", "material": "C30", "shape": {"type": "rectangular", "b_mm": 500, "h_mm": 500}}
    )
    fields["before"]["elements"].append(_element("u-c", 103, "F1", 21, "Told"))
    fields["after"]["elements"].append(_element("u-c", 103, "F2", 31, "C50"))
    fields["after"]["types"].append(
        _type_row(31, "F2", "C50", {"section_b": _qty(500), "section_h": _qty(500)}, (103,))
    )
    trace = TraceBuilder()
    body = _run(fields, _meta_without(), trace)
    assert body == {
        "status": "FAIL",
        "issues": [{"unique_id": "u-c", "code": "TYPE_MISMATCH"}],
        "before_revision": 1,
        "after_revision": 2,
    }
    built = trace.build(REGISTRY["harness.revit_column_readback"], "ab" * 32)
    assert [(i.name, i.value, i.unit, i.ref) for i in built.inputs] == [
        ("before_revision", 1, None, REFS["before"]),
        ("after_revision", 2, None, REFS["after"]),
        ("planned_elements", 2, None, REFS["plan"]),
        ("frame_sections", 2, None, REFS["sections"]),
        ("compare_length_mm", 5.0, "mm", f"{REFS['basis']}#/fields/compare.length_mm"),
    ]
    assert [(s.name, s.value, s.unit, s.formula, s.source, list(s.uses)) for s in built.steps] == [
        (
            "issues",
            1,
            None,
            "planned element and role issues plus unplanned type changes",
            "spec 0013 §4.4.6 B1 to B4",
            ["before_revision", "after_revision", "planned_elements", "frame_sections", "compare_length_mm"],
        ),
        (
            "status",
            "FAIL",
            None,
            "PASS if there are no issues and after_revision exceeds before_revision",
            "spec 0013 §4.4.6",
            ["issues", "before_revision", "after_revision"],
        ),
    ]
    assert built.outputs == ["status", "issues", "before_revision", "after_revision"]
    assert built.constants == []


def test_registration_and_input_schema() -> None:
    """The registry entry and every input field's reference rule pin the decorator and `_ref` arguments."""
    definition = REGISTRY["harness.revit_column_readback"]
    assert (
        definition.id,
        definition.version,
        definition.output_kind,
        definition.title,
        definition.method_source,
        definition.verification,
    ) == (
        "harness.revit_column_readback",
        1,
        "harness.revit_column_readback/1",
        "Revit column read-back against the update plan",
        "eng-harness spec 0013 §4.4.6 (B1 to B4)",
        "draft",
    )
    assert definition.input_type is RevitReadbackInput
    fields = RevitReadbackInput.model_json_schema()["properties"]
    assert {name: field["x-eng"] for name, field in fields.items()} == {
        name: {
            "unit": None,
            "ref_capable": True,
            "engineering_quantity": True,
            "stale_ok": name == "before",
            "bounds_source": None,
            "ref_kinds": [kind],
        }
        for name, kind in KINDS.items()
    }


def test_basis_fields() -> None:
    assert BASIS_FIELDS == ("compare.length_mm",)
