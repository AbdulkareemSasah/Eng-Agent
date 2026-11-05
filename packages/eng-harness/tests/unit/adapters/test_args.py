"""Arguments from neutral kinds and references (plan 0002 T8; spec 0002 section 4.5.2, AC18).

Expected values come from the spec text and from independent definitions, not from the code: 1 in = 25.4 mm exactly,
1 ft = 0.3048 m exactly, so 1 ft2 = 0.09290304 m2 and 10000 mm2 = 0.01 m2. The target and `confirm` keys
are those of the Sasaah CSI tool catalog (`TargetProp` and the `confirm` property).
"""

from collections.abc import Callable
from typing import Any

import pytest
from eng_contract.envelope import HostInfo, LiteralInput, Provenance, RefInput
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import ParamModel, eng_param
from eng_contract.quantity import Quantity
from eng_contract.store import ResultStore
from eng_contract.units import UnitError, UnitGapError

from eng_harness.adapters import (
    HostTarget,
    ToolDescriptor,
    convert_quantities,
    host_arguments,
    validate_call,
)

MODEL = "mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV"
WHY = "Synthetic bounds for the test model, not a code value"
FT2_IN_M2 = 0.09290304  # 0.3048 m squared, exact
TARGET = HostTarget(product="ETABS", pid=4242)


class WallArgs(ParamModel):
    """A synthetic canonical argument model: two engineering quantities, a plain field, a ratio and a quantity."""

    name: str
    thickness_mm: float = eng_param(
        unit="mm", ge=1, le=5000, bounds_source=WHY, ref_capable=True, engineering_quantity=True
    )
    area_mm2: float = eng_param(1.0, unit="mm2", ref_capable=True, engineering_quantity=True)
    scale_ratio: float = eng_param(1.0, unit="1", ref_capable=True)
    cover: Quantity | None = eng_param(None, unit="mm", ref_capable=True)
    twist_deg: float | None = eng_param(None, unit="deg")


def _provenance(revision: int | None) -> Provenance:
    host = (
        None if revision is None else HostInfo(program="ETABS", version="22", model_id=MODEL, model_revision=revision)
    )
    return Provenance(
        tool="harness", tool_version="1", host=host, inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0
    )


def _put(store: ResultStore, value: dict[str, Any], revision: int | None = None) -> str:
    return store.put("harness.run_input/1", {"value": value}, _provenance(revision)).result_id


def _no_revision(_: str) -> int | None:
    return None


def _call(store: ResultStore, raw: dict[str, Any], revision: Callable[[str], int | None] = _no_revision) -> Any:
    return validate_call(WallArgs, raw, source=store, current_revision=revision)


def _descriptor(**over: Any) -> ToolDescriptor:
    fields: dict[str, Any] = {
        "name": "csi_define_wall_section",
        "kind": "write",
        "timeout_class": "call",
        "effect": "write",
        "action": "plain",
        "args_model": "WallArgs",
        "units": "token",
        "confirm": "never",
        "readback": "wall_section",
        "products": ["ETABS"],
    }
    return ToolDescriptor.model_validate(fields | over)


def test_refs_resolved_converted_recorded(store: ResultStore) -> None:
    rid = _put(store, {"thickness_mm": 250.0, "area_mm2": 10000.0})
    thickness, load = f"{rid}#/value/thickness_mm", f"{rid}#/value/area_mm2"
    validated = _call(store, {"name": "W1", "thickness_mm": {"$ref": thickness}, "area_mm2": {"$ref": load}})

    # resolved through the contract: the model holds the stored values in canonical units
    assert (validated.model.thickness_mm, validated.model.area_mm2) == (250.0, 10000.0)
    # provenance records the references and the literal, never the referenced values
    assert validated.inputs == {
        "name": LiteralInput(literal="W1"),
        "thickness_mm": RefInput(ref=thickness),
        "area_mm2": RefInput(ref=load),
    }
    assert "250" not in repr(validated.inputs["thickness_mm"]) + repr(validated.inputs["area_mm2"])

    # converted to the units the token passes: 250 mm is 0.25 m and 10000 mm2 is 0.01 m2 (both exact)
    assert convert_quantities(validated.model, "kN_mm_C") == {
        "thickness_mm": 250.0,
        "area_mm2": 10000.0,
        "scale_ratio": 1.0,
    }
    in_metres = convert_quantities(validated.model, "kN_m_C")
    assert (in_metres["thickness_mm"], in_metres["area_mm2"]) == (0.25, 0.01)
    in_feet = convert_quantities(validated.model, "kip_ft_F")
    assert in_feet["area_mm2"] == pytest.approx(0.01 / FT2_IN_M2, rel=1e-9)
    assert in_feet["thickness_mm"] == pytest.approx(250.0 / 304.8, rel=1e-12)


def test_engineering_quantity_literal_is_refused_before_any_host_call(store: ResultStore) -> None:
    with pytest.raises(ContractError) as caught:
        _call(store, {"name": "W1", "thickness_mm": 250.0})
    assert (caught.value.detail.code, caught.value.detail.field) == (ErrorCode.INVALID_ARGUMENT, "thickness_mm")


def test_staleness_and_unknown_references_are_refused(store: ResultStore) -> None:
    rid = _put(store, {"thickness_mm": 250.0}, revision=3)
    raw = {"name": "W1", "thickness_mm": {"$ref": f"{rid}#/value/thickness_mm"}}
    with pytest.raises(ContractError) as caught:
        _call(store, raw, revision=lambda _: 4)
    assert caught.value.detail.code is ErrorCode.REF_STALE
    assert _call(store, raw, revision=lambda _: 3).model.thickness_mm == 250.0  # the same revision is not stale
    missing = {"name": "W1", "thickness_mm": {"$ref": "res_01ARZ3NDEKTSV4RRFFQ69G5FAW#/value/x"}}
    with pytest.raises(ContractError) as caught:
        _call(store, missing)
    assert caught.value.detail.code is ErrorCode.REF_NOT_FOUND


def test_quantity_optional_ratio_and_unfixed_units(store: ResultStore) -> None:
    rid = _put(store, {"thickness_mm": 300.0})
    thickness = {"$ref": f"{rid}#/value/thickness_mm"}
    model = _call(store, {"name": "W", "thickness_mm": thickness, "cover": {"value": 25, "unit": "mm"}}).model
    converted = convert_quantities(model, "kN_m_C")
    assert converted["cover"] == 0.025  # a Quantity field converts like a number
    assert "twist_deg" not in converted  # absent optional values are skipped
    assert converted["scale_ratio"] == 1.0  # a ratio is the same in every system
    angled = _call(store, {"name": "W", "thickness_mm": thickness, "twist_deg": 5.0}).model
    with pytest.raises(UnitError):  # a units token does not fix an angle: nothing is guessed
        convert_quantities(angled, "kN_m_C")


def test_unit_systems_are_checked() -> None:
    model = WallArgs.model_construct(name="W", thickness_mm=1.0)
    with pytest.raises(UnitGapError):  # Ton_* is contract gap G-1
        convert_quantities(model, "Ton_m_C")
    with pytest.raises(UnitError):
        convert_quantities(model, "not_a_system")


def test_host_arguments_target_units_and_confirm() -> None:
    args = {"name": "W1", "thickness": 250.0}
    sent = host_arguments(_descriptor(confirm="approved"), args, target=TARGET, units_system="kN_mm_C", approved=True)
    assert sent == {
        "name": "W1",
        "thickness": 250.0,
        "units": "kN_mm_C",
        "target": {"product": "ETABS", "pid": 4242},
        "confirm": True,
    }
    assert args == {"name": "W1", "thickness": 250.0}  # the caller's mapping is not changed

    # confirm: never for `never`; only under an approval for `approved`; also a launched instance for `owned`
    assert "confirm" not in host_arguments(_descriptor(), args, target=TARGET, units_system="kN_mm_C", approved=True)
    assert "confirm" not in host_arguments(_descriptor(confirm="approved"), args, target=TARGET, units_system="kN_mm_C")
    owned = _descriptor(confirm="owned")
    assert "confirm" not in host_arguments(owned, args, target=TARGET, units_system="kN_mm_C", approved=True)
    assert "confirm" not in host_arguments(owned, args, target=TARGET, units_system="kN_mm_C", owned=True)
    assert (
        host_arguments(owned, args, target=TARGET, units_system="kN_mm_C", approved=True, owned=True)["confirm"] is True
    )


def test_host_arguments_units_only_for_token_tools() -> None:
    plain = _descriptor(units="none", kind="read", effect="read", readback=None)
    assert "units" not in host_arguments(plain, {}, target=TARGET)
    declared = _descriptor(units="declared_ignored", kind="read", effect="read", readback=None)
    assert "units" not in host_arguments(declared, {}, target=TARGET, units_system="kN_m_C")
    with pytest.raises(ContractError) as caught:  # a token tool always passes its token
        host_arguments(_descriptor(), {}, target=TARGET)
    assert (caught.value.detail.code, caught.value.detail.field) == (ErrorCode.INVALID_ARGUMENT, "units")
    with pytest.raises(UnitGapError):
        host_arguments(_descriptor(), {}, target=TARGET, units_system="Ton_m_C")


@pytest.mark.parametrize("key", ["target", "confirm", "units"])
def test_builders_cannot_set_the_framework_keys(key: str) -> None:
    with pytest.raises(ContractError) as caught:
        host_arguments(_descriptor(), {key: "x"}, target=TARGET, units_system="kN_m_C")
    assert (caught.value.detail.code, caught.value.detail.field) == (ErrorCode.INVALID_ARGUMENT, key)


def test_target_must_name_an_instance() -> None:
    with pytest.raises(ValueError, match="pid"):
        HostTarget(product="ETABS", pid=0)
