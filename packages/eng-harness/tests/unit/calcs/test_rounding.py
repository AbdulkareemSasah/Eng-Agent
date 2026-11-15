"""Calc 5, section size rounding (plan 0003 T11; spec 0003 4.10, AC39 to AC41): rule, bounds, basis and trace."""

import json
from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import InputPolicy, validate_input
from eng_contract.records import ResultRecord

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.calc import CalcInput, InputMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.errors import NotImplementedGap
from eng_harness.kinds.calcs import SectionSize

CALC_ID = "harness.section_round"
INCREMENT = "modeling.section_increment_mm"
RULE = "modeling.section_rounding"
SRC = "engineer:synthetic@2026-01-01T00:00:00.000Z"
GOLDEN_DIR = Path(__file__).resolve().parents[2] / "data" / "golden" / "calcs"


def _field(value: Any, unit: str | None = None, *, confirmed: bool = True) -> dict[str, Any]:
    return {"value": value, "unit": unit, "source": SRC, "confirmed": confirmed, "citation": None}


def _basis(**fields: dict[str, Any] | None) -> dict[str, Any]:
    given = {INCREMENT: _field(50, "mm"), RULE: _field("up")}
    named = {INCREMENT: fields.pop("increment", given[INCREMENT]), RULE: fields.pop("rule", given[RULE])}
    return {"template": None, "fields": {k: v for k, v in (named | fields).items() if v is not None}}


def _ref(n: int, kind: str) -> dict[str, Any]:
    return {
        "result_id": f"res_{n:026d}",
        "kind": kind,
        "complete": True,
        "model_id": None,
        "model_revision": None,
        "parents": [],
        "producer_tool": "harness",
    }


REFS = {"required": _ref(1, "basis.engineer_input/1"), "basis": _ref(9, "basis.design_basis/1")}


def _input_type() -> type[CalcInput]:
    input_type = REGISTRY[CALC_ID].input_type
    assert isinstance(input_type, type)
    assert issubclass(input_type, CalcInput)
    return input_type


def _run(
    required: float = 437.5,
    basis: dict[str, Any] | None = None,
    refs: dict[str, Any] | None = None,
    trace: TraceBuilder | None = None,
) -> dict[str, Any]:
    raw = {"required": {"value": required, "unit": "mm"}, "basis": _basis() if basis is None else basis}
    inp = _input_type().model_validate(raw)
    meta = InputMeta.model_validate({"refs": REFS if refs is None else refs})
    return REGISTRY[CALC_ID](inp, meta, trace or TraceBuilder()).model_dump(mode="json")


class _NoStore:
    """A record source that holds nothing: literal inputs never reach it."""

    def get(self, result_id: str) -> ResultRecord:
        raise AssertionError(result_id)

    def payload(self, result_id: str) -> dict[str, Any]:
        raise AssertionError(result_id)


def _validate(required: float) -> Any:
    raw = {"required": {"value": required, "unit": "mm"}, "basis": _basis()}
    return validate_input(
        _input_type(), raw, source=_NoStore(), current_revision=lambda _: None, policy=InputPolicy()
    ).model


def _refusal(basis: dict[str, Any]) -> ContractError:
    with pytest.raises(ContractError) as caught:
        _run(basis=basis)
    return caught.value


def test_edge_cases() -> None:
    """AC40: a rule other than `up` is gap CG-2, a required size not > 0 is OUT_OF_RANGE, no compare field is read."""
    for rule in ("down", "nearest", "UP"):
        with pytest.raises(NotImplementedGap) as gap:
            _run(basis=_basis(rule=_field(rule)))
        assert gap.value.evidence == ("CG-2",)
        assert str(gap.value) == f"the section rounding rule {rule!r} is not implemented (gap CG-2)"
    for required in (0.0, -0.0, -50.0):
        with pytest.raises(ContractError) as caught:
            _validate(required)
        detail = caught.value.detail
        assert (detail.code, detail.field, detail.received) == (ErrorCode.OUT_OF_RANGE, "required", required)
        assert detail.expected == {"exclusive_min": 0, "unit": "mm"}
    assert _validate(0.5).required.value == 0.5  # positive, however small: accepted and never clamped
    trace = TraceBuilder()
    assert _run(0.5, trace=trace)["size"] == {"value": 50.0, "unit": "mm"}  # basis without any compare.* field
    names = [i.name for i in trace.build(REGISTRY[CALC_ID], "ab" * 32).inputs]
    assert names == ["modeling_section_rounding", "modeling_section_increment_mm", "required"]


@pytest.mark.parametrize(
    ("required", "increment", "multiple", "size"),
    [
        (0.5, 0.5, 1, 0.5),
        (0.75, 0.5, 2, 1.0),
        (1.0, 0.25, 4, 1.0),
        (1.0, 0.75, 2, 1.5),
        (450.0, 50, 9, 450.0),
        (450.0000000000001, 50, 10, 500.0),
        (0.1, 0.1, 1, 0.1),
        (0.3, 0.1, 3, 0.30000000000000004),  # 3 x Fraction(0.1) lies halfway between two floats: ties to even
        (0.30000000000000004, 0.1, 4, 0.4),  # above 3 x Fraction(0.1): the next multiple
    ],
)
def test_round_up(required: float, increment: float, multiple: int, size: float) -> None:
    """N1, N2: the smallest multiple not below the required size, on exact fractions of the stored values."""
    out = _run(required, _basis(increment=_field(increment, "mm")))
    assert (out["multiple"], out["size"], out["status"]) == (multiple, {"value": size, "unit": "mm"}, "PASS")
    assert out["required"] == {"value": required, "unit": "mm"}
    assert out["increment"] == {"value": float(increment), "unit": "mm"}


@pytest.mark.parametrize(
    ("basis", "message"),
    [
        (_basis(rule=None), f"basis field {RULE} is missing (no default)"),
        (_basis(rule=_field("up", confirmed=False)), f"basis field {RULE} is not confirmed"),
        (_basis(rule=_field("up", "mm")), f"basis field {RULE} must have no unit, not mm"),
        (_basis(rule=_field(1)), f"basis field {RULE} must be the name of a rule"),
        (_basis(increment=None), f"basis field {INCREMENT} is missing (no default)"),
        (_basis(increment=_field(50, "mm", confirmed=False)), f"basis field {INCREMENT} is not confirmed"),
        (_basis(increment=_field("50", "mm")), f"basis field {INCREMENT} must be a number"),
        (_basis(increment=_field(True, "mm")), f"basis field {INCREMENT} must be a number"),
    ],
)
def test_basis_refused(basis: dict[str, Any], message: str) -> None:
    """Spec 4.4: each basis field present, confirmed, of its type and unit; no default."""
    detail = _refusal(basis).detail
    path = message.split()[2]
    assert (detail.code, detail.message, detail.field) == (ErrorCode.INVALID_ARGUMENT, message, f"basis.fields.{path}")
    assert detail.hint == f"set and confirm {path} in the design basis"


@pytest.mark.parametrize("increment", [0, 0.0, -0.5, -50])
def test_increment_not_positive(increment: float) -> None:
    """Spec 4.4 bounds: `modeling.section_increment_mm` > 0, else OUT_OF_RANGE with the bound; never a default."""
    detail = _refusal(_basis(increment=_field(increment, "mm"))).detail
    assert (detail.code, detail.message) == (ErrorCode.OUT_OF_RANGE, f"basis field {INCREMENT} must be > 0")
    assert (detail.field, detail.received) == (f"basis.fields.{INCREMENT}", increment)
    assert detail.expected == {"exclusive_min": 0, "unit": "mm"}


def test_basis_must_be_a_record() -> None:
    """The basis pointers of the trace need the basis record: a literal basis is refused."""
    with pytest.raises(ContractError) as caught:
        _run(refs={"required": REFS["required"]})
    detail = caught.value.detail
    assert (detail.code, detail.message, detail.field) == (
        ErrorCode.INVALID_ARGUMENT,
        "the basis must be a record reference",
        "basis",
    )


def test_trace_and_schema() -> None:
    """Trace: required and increment as inputs, steps r / i, n and size (N1, N2); `required` is a mm reference > 0."""
    trace = TraceBuilder()
    _run(437.5, trace=trace)
    built = trace.build(REGISTRY[CALC_ID], "ab" * 32)
    inputs = {i.name: (i.value, i.unit, i.ref) for i in built.inputs}
    basis_id = REFS["basis"]["result_id"]
    assert inputs == {
        "modeling_section_rounding": ("up", None, f"{basis_id}#/fields/{RULE}"),
        "modeling_section_increment_mm": (50, "mm", f"{basis_id}#/fields/{INCREMENT}"),
        "required": (437.5, "mm", REFS["required"]["result_id"]),
    }
    steps = [(s.name, s.value, s.unit, s.source, list(s.uses)) for s in built.steps]
    assert steps == [
        ("ratio", 8.75, None, "§4.10 N1", ["required", "modeling_section_increment_mm"]),
        ("multiple", 9, None, "§4.10 N1", ["ratio"]),
        ("size", 450.0, "mm", "§4.10 N2", ["multiple", "modeling_section_increment_mm"]),
    ]
    assert list(built.outputs) == ["size"]
    literal = TraceBuilder()
    _run(437.5, refs={"basis": REFS["basis"]}, trace=literal)
    assert [i.ref for i in literal.build(REGISTRY[CALC_ID], "ab" * 32).inputs][2] is None
    prop = _input_type().model_json_schema()["properties"]["required"]
    assert prop["x-eng"]["unit"] == "mm"
    assert (prop["x-eng"]["ref_capable"], prop["x-eng"]["engineering_quantity"], prop["x-eng"]["stale_ok"]) == (
        True,
        True,
        False,
    )
    assert prop["x-eng"]["ref_kinds"] == []
    assert prop["anyOf"][0]["properties"]["value"]["exclusiveMinimum"] == 0


def test_golden_expectations_are_valid_payloads() -> None:
    """Each round golden's expected body, with calc metadata and a trace added, fits the calc's output kind."""
    output_type = HARNESS_KINDS[REGISTRY[CALC_ID].output_kind]
    assert output_type is SectionSize
    files = sorted(GOLDEN_DIR.glob("round-*.json"))
    assert len(files) == 3
    meta = {"id": CALC_ID, "version": 1, "content_sha256": "a" * 64, "status": "draft"}
    trace = {"calc_id": CALC_ID, "calc_version": "1", "content_sha256": "a" * 64, "steps": [], "outputs": []}
    for path in files:
        expected = json.loads(path.read_text(encoding="utf-8"))["expected"]
        output_type.model_validate(
            expected | {"calc": meta, "draft": True, "trace": trace | {"inputs": [], "constants": []}}
        )
