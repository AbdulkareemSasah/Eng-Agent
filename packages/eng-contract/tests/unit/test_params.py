"""Input-parameter metadata and the validation pipeline (plan T9; spec 3.6 and 5; AC39 to AC43).

Expected values come from the criteria of spec 3.6, the metadata table and the step order of spec section 5, and the
error table of spec section 6, not from the implementation. The physical bounds below are the example of 04 section 7
(`b_mm` from 150 to 3000) and synthetic values for the other fields.
"""

from collections.abc import Callable
from typing import Any, Literal

import pytest
from pydantic import Field, create_model, model_validator

from eng_contract.envelope import LiteralInput, RefInput
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import (
    ContractDefinitionError,
    InputPolicy,
    ParamModel,
    ValidatedInput,
    eng_param,
    validate_input,
)
from eng_contract.quantity import Quantity
from eng_contract.records import ResultRecord

RID = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"
MISSING = "res_01ARZ3NDEKTSV4RRFFQ69G5FAW"
MID = "mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV"
TS = "2026-01-02T03:04:05.678Z"
WHY = "Widths below 150 mm or above 3000 mm are not physically meaningful here"
SECTIONS = "model.sections/1"


class Beam(ParamModel):
    """A synthetic tool input model covering every kind of parameter metadata."""

    b_mm: float = eng_param(
        unit="mm",
        ge=150,
        le=3000,
        bounds_source=WHY,
        ref_capable=True,
        ref_kinds=frozenset({SECTIONS}),
        engineering_quantity=True,
    )
    h_mm: Quantity = eng_param(unit="mm", ge=100, le=5000, bounds_source=WHY, ref_capable=True)
    dur_s: float = eng_param(unit="s", gt=0, lt=200, bounds_source=WHY, ref_capable=True, stale_ok=True)
    cover_mm: float = eng_param(15.0, unit="mm", ge=0, bounds_source=WHY)
    material: Literal["concrete", "steel"] = "concrete"
    n_bars: int = 2
    layers: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _steel_has_no_bars(self) -> Beam:
        if self.material == "steel" and self.n_bars > 0:
            raise ValueError("steel members take no bars")
        return self


PAYLOAD: dict[str, Any] = {
    "b_mm": 300,
    "wide_mm": 5000,
    "h": {"value": 500, "unit": "mm"},
    "h_kPa": {"value": 25, "unit": "kPa"},
    "dur_s": 30,
    "name": "text",
}


def record(*, rid: str = RID, kind: str = SECTIONS, host_revision: int | None = None) -> ResultRecord:
    producer: dict[str, Any] = {
        "tool": "harness",
        "tool_version": "1",
        "inputs": {},
        "started_at": TS,
        "duration_ms": 0,
    }
    if host_revision is not None:
        producer["host"] = {"program": "ETABS", "version": "1", "model_id": MID, "model_revision": host_revision}
    return ResultRecord.model_validate(
        {
            "contract": "eng-contract/1",
            "result_id": rid,
            "kind": kind,
            "created_at": TS,
            "units": "canonical/1",
            "complete": True,
            "producer": producer,
            "parents": [],
            "payload_sha256": "b" * 64,
            "payload": PAYLOAD,
            "payload_file": None,
        }
    )


class MemorySource:
    """In-memory `RecordSource`: a missing id raises `REF_NOT_FOUND`, as the store does."""

    def __init__(self, *records: ResultRecord) -> None:
        self.records = {r.result_id: r for r in records}

    def get(self, result_id: str) -> ResultRecord:
        if result_id not in self.records:
            raise ContractError(ErrorCode.REF_NOT_FOUND, f"no result {result_id}")
        return self.records[result_id]

    def payload(self, result_id: str) -> dict[str, Any]:
        return dict(self.records[result_id].payload or {})


def untracked(_: str) -> int | None:
    return None


def ref(pointer: str = "", result_id: str = RID) -> dict[str, str]:
    return {"$ref": f"{result_id}#{pointer}"}


GOOD: dict[str, Any] = {"b_mm": 450, "h_mm": {"value": 600, "unit": "mm"}, "dur_s": 25}


def run(
    raw: dict[str, Any],
    *,
    policy: InputPolicy | None = None,
    source: MemorySource | None = None,
    revision: Callable[[str], int | None] = untracked,
) -> ValidatedInput[Beam]:
    return validate_input(
        Beam,
        raw,
        source=source or MemorySource(record()),
        current_revision=revision,
        policy=policy or InputPolicy(),
    )


def fails(raw: dict[str, Any], **kwargs: Any) -> ContractError:
    with pytest.raises(ContractError) as info:
        run(raw, **kwargs)
    return info.value


def define(name: str, annotation: type, **meta: Any) -> type[ParamModel]:
    """Define a one-field input model, as a tool author would (the field name decides the unit rules)."""
    definitions: dict[str, Any] = {name: (annotation, eng_param(**meta))}
    return create_model("Defined", __base__=ParamModel, **definitions)


# --- AC39 ------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "meta"),
    [
        pytest.param("b_mm", {"unit": "MPa"}, id="unit-not-the-suffix-unit"),
        pytest.param("b_mm", {}, id="suffixed-name-without-unit"),
        pytest.param("b_mm", {"unit": "furlong"}, id="unknown-unit"),
        pytest.param("b_mm", {"unit": "mm", "ge": 1.0}, id="bounds-without-source"),
        pytest.param("b_mm", {"unit": "mm", "le": 1.0, "bounds_source": "short"}, id="source-too-short"),
        pytest.param("b_mm", {"unit": "mm", "le": 1.0, "bounds_source": "x" * 501}, id="source-too-long"),
        pytest.param("b_mm", {"unit": "mm", "ge": 1.0, "gt": 1.0, "bounds_source": WHY}, id="two-lower-bounds"),
        pytest.param("b_mm", {"unit": "mm", "le": 1.0, "lt": 1.0, "bounds_source": WHY}, id="two-upper-bounds"),
        pytest.param("b_mm", {"unit": "mm", "ge": 5.0, "le": 1.0, "bounds_source": WHY}, id="empty-interval"),
        pytest.param("b_mm", {"unit": "mm", "gt": 5.0, "lt": 5.0, "bounds_source": WHY}, id="empty-open-interval"),
        pytest.param("b_mm", {"unit": "mm", "ge": 5.0, "lt": 5.0, "bounds_source": WHY}, id="empty-half-open-interval"),
        pytest.param("b_mm", {"unit": "mm", "engineering_quantity": True}, id="engineering-without-ref-capable"),
        pytest.param("b_mm", {"unit": "mm", "stale_ok": True}, id="stale-ok-without-ref-capable"),
        pytest.param("b_mm", {"unit": "mm", "ref_kinds": frozenset({SECTIONS})}, id="kinds-without-ref-capable"),
        pytest.param("b_mm", {"unit": "mm", "ref_capable": True, "ref_kinds": {"Bad Kind"}}, id="malformed-kind"),
        pytest.param("label", {"unit": "furlong"}, id="unknown-unit-on-unsuffixed-name"),
    ],
)
def test_definition_checks(name: str, meta: dict[str, Any]) -> None:
    with pytest.raises(ContractDefinitionError, match=name):
        define(name, float, **meta)


def test_definition_checks_accept_valid_and_boundary_definitions() -> None:
    define("b_mm", float, unit="mm", ge=1.0, le=1.0, bounds_source="x" * 8)
    define("b_mm", float, unit="mm", gt=0.0, lt=1.0, bounds_source="x" * 500)
    define("label", str)
    define("ratio_ratio", float, unit="1", ge=0.0, bounds_source=WHY)


def test_definition_check_covers_plain_fields_of_a_suffixed_name() -> None:
    with pytest.raises(ContractDefinitionError, match="b_mm"):
        create_model("Plain", __base__=ParamModel, b_mm=(float, ...))


def test_definition_error_is_not_a_contract_error() -> None:
    assert not issubclass(ContractDefinitionError, ContractError)


# --- AC40 ------------------------------------------------------------------------------------------------------------


def test_json_schema_metadata() -> None:
    schema = Beam.model_json_schema()
    props = schema["properties"]

    b = props["b_mm"]
    literal, reference = b["anyOf"]
    assert (literal["type"], literal["minimum"], literal["maximum"]) == ("number", 150, 3000)
    assert reference == {"$ref": "#/$defs/Ref"}
    assert schema["$defs"]["Ref"]["properties"]["$ref"]["type"] == "string"
    assert b["x-eng"] == {
        "unit": "mm",
        "ref_capable": True,
        "engineering_quantity": True,
        "stale_ok": False,
        "bounds_source": WHY,
        "ref_kinds": [SECTIONS],
    }

    fc = props["dur_s"]
    assert (fc["anyOf"][0]["exclusiveMinimum"], fc["anyOf"][0]["exclusiveMaximum"]) == (0, 200)
    assert fc["x-eng"]["stale_ok"] is True
    assert fc["x-eng"]["engineering_quantity"] is False

    cover = props["cover_mm"]  # not ref-capable: the bounds sit on the property itself, with the default
    assert "anyOf" not in cover
    assert (cover["minimum"], cover["default"]) == (0, 15.0)
    assert cover["x-eng"] == {
        "unit": "mm",
        "ref_capable": False,
        "engineering_quantity": False,
        "stale_ok": False,
        "bounds_source": WHY,
        "ref_kinds": [],
    }

    assert props["material"]["enum"] == ["concrete", "steel"]
    assert "x-eng" not in props["material"]
    assert schema["required"] == ["b_mm", "h_mm", "dur_s"]
    assert schema["additionalProperties"] is False


def test_json_schema_without_ref_capable_fields_has_no_ref_definition() -> None:
    schema = define("cover_mm", float, unit="mm", ge=0.0, bounds_source=WHY).model_json_schema()
    assert "Ref" not in schema.get("$defs", {})


def test_ref_capable_field_keeps_its_title_and_default_outside_the_choice() -> None:
    model = define("b_mm", float, default=450.0, unit="mm", ref_capable=True)
    prop = model.model_json_schema()["properties"]["b_mm"]
    assert (prop["title"], prop["default"]) == ("B Mm", 450.0)
    assert "default" not in prop["anyOf"][0]


# --- AC41 ------------------------------------------------------------------------------------------------------------


def test_validation_order() -> None:
    # 1. shape beats everything
    err = fails({**GOOD, "b_mm": 1, "bogus": 1}).detail
    assert (err.code, err.received) == (ErrorCode.INVALID_ARGUMENT, "bogus")
    err = fails({"h_mm": GOOD["h_mm"], "dur_s": 25}).detail
    assert (err.code, err.field) == (ErrorCode.INVALID_ARGUMENT, "b_mm")
    err = fails({**GOOD, "b_mm": "wide"}).detail
    assert (err.code, err.field) == (ErrorCode.INVALID_ARGUMENT, "b_mm")
    err = fails({**GOOD, "b_mm": True}).detail
    assert (err.code, err.field) == (ErrorCode.INVALID_ARGUMENT, "b_mm")
    err = fails({**GOOD, "layers": [1, "x"]}).detail
    assert (err.code, err.field) == (ErrorCode.INVALID_ARGUMENT, "layers[1]")
    err = fails({**GOOD, "b_mm": 1, "dur_s": {"$ref": "nonsense"}}).detail  # malformed Ref beats out-of-range
    assert (err.code, err.field) == (ErrorCode.INVALID_ARGUMENT, "dur_s")
    err = fails({**GOOD, "dur_s": {"$ref": f"{RID}#/dur_s", "extra": 1}}).detail
    assert (err.code, err.field) == (ErrorCode.INVALID_ARGUMENT, "dur_s")

    # 3. a failing reference beats an out-of-range literal elsewhere (and a failing cross-field rule)
    err = fails({**GOOD, "b_mm": ref("/b_mm", MISSING), "dur_s": 999, "material": "steel"}).detail
    assert (err.code, err.field) == (ErrorCode.REF_NOT_FOUND, "b_mm")
    err = fails({**GOOD, "dur_s": ref("/nothing")}).detail
    assert (err.code, err.field) == (ErrorCode.REF_POINTER_INVALID, "dur_s")

    # 4. units beat bounds
    err = fails({**GOOD, "b_mm": 1, "h_mm": {"value": 600, "unit": "m"}}).detail
    assert (err.code, err.field, err.expected, err.received) == (
        ErrorCode.UNIT_MISMATCH,
        "h_mm",
        {"unit": "mm"},
        "m",
    )

    # 5. bounds beat cross-field rules
    err = fails({**GOOD, "b_mm": 3000.5, "material": "steel"}).detail
    assert (err.code, err.field) == (ErrorCode.OUT_OF_RANGE, "b_mm")

    # 6. only a cross-field rule fails
    err = fails({**GOOD, "material": "steel"}).detail
    assert (err.code, err.message) == (ErrorCode.INVALID_ARGUMENT, "Value error, steel members take no bars")


def test_out_of_range_detail_and_boundaries() -> None:
    err = fails({**GOOD, "b_mm": 149.5}).detail
    assert (err.code, err.field, err.expected, err.received) == (
        ErrorCode.OUT_OF_RANGE,
        "b_mm",
        {"min": 150, "max": 3000, "unit": "mm"},
        149.5,
    )
    assert fails({**GOOD, "b_mm": 3001}).detail.code is ErrorCode.OUT_OF_RANGE
    for edge in (150, 3000):  # inclusive bounds accept their edges
        assert run({**GOOD, "b_mm": edge}).model.b_mm == edge
    err = fails({**GOOD, "dur_s": 0}).detail  # exclusive bounds reject their edges
    assert (err.field, err.received) == ("dur_s", 0)
    assert err.expected == {"exclusive_min": 0, "exclusive_max": 200, "unit": "s"}
    assert fails({**GOOD, "dur_s": 200}).detail.field == "dur_s"
    err = fails({**GOOD, "h_mm": {"value": 99.9, "unit": "mm"}}).detail  # a Quantity is bounded by its value
    assert (err.code, err.field, err.received) == (ErrorCode.OUT_OF_RANGE, "h_mm", 99.9)


def test_non_finite_numbers_are_rejected_as_invalid_arguments() -> None:
    for bad in (float("nan"), float("inf")):
        assert fails({**GOOD, "b_mm": bad}).detail.code is ErrorCode.INVALID_ARGUMENT


def test_valid_input_is_returned_unchanged_with_provenance_inputs() -> None:
    raw = {**GOOD, "b_mm": 450.123456, "layers": [3, 4]}
    result = run(raw)
    assert result.model.b_mm == 450.123456  # no rounding, clamping or conversion
    assert result.model.h_mm == Quantity(600, "mm")
    assert (result.model.cover_mm, result.model.material, result.model.layers) == (15.0, "concrete", [3, 4])
    assert result.inputs == {  # only what the caller gave; defaults are not inputs
        "b_mm": LiteralInput(literal=450.123456),
        "h_mm": LiteralInput(literal={"value": 600, "unit": "mm"}),
        "dur_s": LiteralInput(literal=25),
        "layers": LiteralInput(literal=[3, 4]),
    }


def test_references_are_resolved_into_the_model_and_recorded_as_refs() -> None:
    raw = {"b_mm": ref("/b_mm"), "h_mm": ref("/h"), "dur_s": ref("/dur_s")}
    result = run(raw)
    assert (result.model.b_mm, result.model.h_mm, result.model.dur_s) == (300, Quantity(500, "mm"), 30)
    assert result.inputs == {k: RefInput(ref=v["$ref"]) for k, v in raw.items()}  # the ref, never the value


# --- AC42 ------------------------------------------------------------------------------------------------------------


def test_require_refs_policy() -> None:
    strict = InputPolicy(require_refs=True)
    err = fails(GOOD, policy=strict).detail
    assert (err.code, err.field) == (ErrorCode.INVALID_ARGUMENT, "b_mm")
    assert err.hint is not None
    assert "b_mm" in err.hint

    # policy beats a failing reference found later (step 2 before step 3)
    err = fails({**GOOD, "dur_s": ref("/nothing")}, policy=strict).detail
    assert (err.code, err.field) == (ErrorCode.INVALID_ARGUMENT, "b_mm")

    # only engineering quantities are held to the policy; a reference passes
    ok = run({**GOOD, "b_mm": ref("/b_mm")}, policy=strict)
    assert ok.inputs["b_mm"] == RefInput(ref=f"{RID}#/b_mm")
    assert ok.inputs["dur_s"] == LiteralInput(literal=25)

    # without the policy the same literal is accepted and recorded as a literal
    assert run(GOOD).inputs["b_mm"] == LiteralInput(literal=450)
    assert InputPolicy().require_refs is False


# --- AC43 ------------------------------------------------------------------------------------------------------------


def test_refs_do_not_bypass_bounds() -> None:
    err = fails({**GOOD, "b_mm": ref("/wide_mm")}).detail
    assert (err.code, err.field, err.received) == (ErrorCode.OUT_OF_RANGE, "b_mm", 5000)
    assert err.expected == {"min": 150, "max": 3000, "unit": "mm"}


def test_reference_rules_come_from_the_parameter_metadata() -> None:
    err = fails({**GOOD, "b_mm": ref("/b_mm")}, source=MemorySource(record(kind="forces.member_end/1"))).detail
    assert (err.code, err.field, err.expected) == (ErrorCode.REF_KIND_MISMATCH, "b_mm", {"kinds": [SECTIONS]})
    err = fails({**GOOD, "h_mm": ref("/h_kPa")}).detail  # a quantity in kPa for a parameter in mm
    assert (err.code, err.field) == (ErrorCode.REF_UNIT_MISMATCH, "h_mm")
    err = fails({**GOOD, "h_mm": ref("/b_mm")}).detail  # a Quantity parameter needs a quantity object, not a number
    assert (err.code, err.field) == (ErrorCode.INVALID_ARGUMENT, "h_mm")
    err = fails({**GOOD, "b_mm": ref("/name")}).detail  # not a number
    assert (err.code, err.field) == (ErrorCode.INVALID_ARGUMENT, "b_mm")


def test_staleness_follows_the_stale_ok_flag() -> None:
    source = MemorySource(record(host_revision=4))

    def moved_on(_: str) -> int | None:
        return 5

    err = fails({**GOOD, "b_mm": ref("/b_mm")}, source=source, revision=moved_on).detail
    assert (err.code, err.field) == (ErrorCode.REF_STALE, "b_mm")
    ok = run({**GOOD, "dur_s": ref("/dur_s")}, source=source, revision=moved_on)  # a stale_ok parameter
    assert ok.model.dur_s == 30
