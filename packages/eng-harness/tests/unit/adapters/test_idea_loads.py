"""IDEA load map, load plan and structure-preserving builder (plan 0014 T7; spec 0014 AC7 to AC9, section 4.7).

The shipped map stays unconfirmed (IG-2). Tests that need a confirmed map load the synthetic fixture whose header
says "synthetic test values, not engineering". Expected host force units are N and N.m (spec 0014 section 4.6);
canonical stored values are kN and kN.m via eng_contract.units.convert.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, cast

import pytest
from eng_contract.envelope import HostInfo, Provenance
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.store import ResultStore
from pydantic import JsonValue

from eng_harness.errors import NotImplementedGap

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "idea"
_SYNTHETIC_MAP = _FIXTURES / "load_map_synthetic.toml"
_MODEL = "mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV"
_SHA = "ab" * 32

# Spec 0014 section 4.7: IDEA components and the CSI fields they take (forces.member_end/1).
_COMPONENTS = ("n", "qy", "qz", "mx", "my", "mz")
_CSI_FIELDS = ("P_kN", "V2_kN", "V3_kN", "T_kNm", "M2_kNm", "M3_kNm")


def _provenance(revision: int | None = 1) -> Provenance:
    host = (
        None if revision is None else HostInfo(program="ETABS", version="22", model_id=_MODEL, model_revision=revision)
    )
    return Provenance(
        tool="harness",
        tool_version="1",
        host=host,
        inputs={},
        started_at="2026-01-01T00:00:00.000Z",
        duration_ms=0,
    )


def _put_member_end(store: ResultStore, row: dict[str, Any], *, revision: int = 1) -> str:
    payload = cast(dict[str, JsonValue], {"sign_convention": "host_local/1", "rows": [row]})
    return store.put("forces.member_end/1", payload, _provenance(revision)).result_id


def _row(
    *,
    member: str = "B1",
    end: str = "i",
    p: float = 10.0,
    v2: float = 1.0,
    v3: float = -2.0,
    t: float = 0.5,
    m2: float = 3.0,
    m3: float = -4.0,
) -> dict[str, Any]:
    return {
        "member": member,
        "case": {"case": "DEAD", "case_type": "load_case"},
        "end": end,
        "station_mm": 0.0,
        "P_kN": p,
        "V2_kN": v2,
        "V3_kN": v3,
        "T_kNm": t,
        "M2_kNm": m2,
        "M3_kNm": m3,
    }


def _host_loading() -> list[dict[str, Any]]:
    """One effect with one mapped segment and one untouched segment (host shape, N / N.m)."""
    return [
        {
            "id": 1,
            "name": "LE1",
            "checkEquilibrium": True,
            "percentageLoad": False,
            "forcesOnSegments": [
                {
                    "beamSegmentId": 1,
                    "position": 0.0,
                    "n": 1000.0,
                    "qy": 0.0,
                    "qz": 0.0,
                    "mx": 0.0,
                    "my": 0.0,
                    "mz": 0.0,
                },
                {
                    "beamSegmentId": 2,
                    "position": 1.0,
                    "n": 500.0,
                    "qy": 10.0,
                    "qz": 20.0,
                    "mx": 30.0,
                    "my": 40.0,
                    "mz": 50.0,
                },
            ],
            "forcesPercentageOnSegments": [],
        }
    ]


def _plan(
    store: ResultStore,
    *,
    member: str = "B1",
    end: str = "i",
    beam_segment_id: int = 1,
    position_host: float = 0.0,
    row_override: dict[str, Any] | None = None,
    revision: int = 1,
    member_map: dict[str, list[dict[str, Any]]] | None = None,
) -> Any:
    from eng_harness.adapters.idea import _loads as loads

    row = row_override or _row(member=member, end=end)
    rid = _put_member_end(store, row, revision=revision)
    entries = [
        {
            "beam_segment_id": beam_segment_id,
            "position_host": position_host,
            "row": {"$ref": f"{rid}#/rows/0"},
        }
    ]
    mapping = member_map
    if mapping is None:
        mapping = {member: [{"beam_segment_id": beam_segment_id, "position_host": position_host}]}
    return loads.LoadPlan.model_validate(
        {
            "path": "/run/model.ideaCon",
            "connection": "CON1",
            "member_map": mapping,
            "effects": [{"name": "LE1", "entries": entries}],
        }
    )


def test_unconfirmed_map_gap() -> None:
    """AC7: the shipped load map is unconfirmed; a load step raises NotImplementedGap IG-2 before any call."""
    from eng_harness.adapters.idea import _loads as loads

    with pytest.raises(NotImplementedGap) as caught:
        loads.require_confirmed_map(loads.load_shipped_map())
    assert "IG-2" in caught.value.evidence


def test_synthetic_map_proceeds() -> None:
    """AC7: a synthetic confirmed map from the test fixtures lets the step proceed past the gap check."""
    from eng_harness.adapters.idea import _loads as loads

    confirmed = loads.load_map_file(_SYNTHETIC_MAP)
    assert confirmed.status == "confirmed"
    loads.require_confirmed_map(confirmed)
    for component, field in zip(_COMPONENTS, _CSI_FIELDS, strict=True):
        entry = confirmed.components[component]
        assert entry.csi_field == field
        assert entry.sign_i in (-1, 1)
        assert entry.sign_j in (-1, 1)


def test_refs_resolved_converted(store: ResultStore) -> None:
    """AC8: $ref rows resolve; forces convert exactly kN→N and kN.m→N.m; provenance records refs, not values."""
    from eng_harness.adapters.idea import _loads as loads

    plan = _plan(store, end="i")
    built, provenance = loads.build_loading(
        current=_host_loading(),
        plan=plan,
        load_map=loads.load_map_file(_SYNTHETIC_MAP),
        source=store,
        current_revision=lambda _: 1,
    )
    seg = next(
        s for effect in built for s in effect["forcesOnSegments"] if s["beamSegmentId"] == 1 and s["position"] == 0.0
    )
    # 10 kN → 10000 N; 1 kN → 1000 N; -2 kN → -2000 N; 0.5 kN.m → 500 N.m; etc. (contract §4.7 exact factors)
    assert seg["n"] == 10000.0
    assert seg["qy"] == 1000.0
    assert seg["qz"] == -2000.0
    assert seg["mx"] == 500.0
    assert seg["my"] == 3000.0
    assert seg["mz"] == -4000.0
    assert provenance
    for value in provenance.values():
        text = str(value)
        assert "10.0" not in text
        assert "10000" not in text
        assert "ref" in text.lower() or "$ref" in text or "res_" in text


def test_literal_force_refused(store: ResultStore) -> None:
    """AC8: a literal force on a load-plan entry is refused (require_refs / engineering_quantity)."""
    from eng_harness.adapters.idea import _loads as loads

    with pytest.raises(ContractError) as caught:
        loads.build_loading_from_raw(
            current=_host_loading(),
            plan={
                "path": "/run/model.ideaCon",
                "connection": "CON1",
                "member_map": {"B1": [{"beam_segment_id": 1, "position_host": 0.0}]},
                "effects": [
                    {
                        "name": "LE1",
                        "entries": [
                            {
                                "beam_segment_id": 1,
                                "position_host": 0.0,
                                "row": {
                                    "member": "B1",
                                    "case": {"case": "DEAD", "case_type": "load_case"},
                                    "end": "i",
                                    "station_mm": 0.0,
                                    "P_kN": 10.0,
                                    "V2_kN": 0.0,
                                    "V3_kN": 0.0,
                                    "T_kNm": 0.0,
                                    "M2_kNm": 0.0,
                                    "M3_kNm": 0.0,
                                },
                            }
                        ],
                    }
                ],
            },
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
        )
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT


def test_stale_ref_refused(store: ResultStore) -> None:
    """AC8: a reference older than the current model revision is REF_STALE."""
    from eng_harness.adapters.idea import _loads as loads

    plan = _plan(store, revision=1)
    with pytest.raises(ContractError) as caught:
        loads.build_loading(
            current=_host_loading(),
            plan=plan,
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 2,
        )
    assert (caught.value.detail.code, caught.value.detail.field) == (ErrorCode.REF_STALE, "row")


def test_wrong_kind_refused(store: ResultStore) -> None:
    """AC8: a reference to another kind is REF_KIND_MISMATCH."""
    from eng_harness.adapters.idea import _loads as loads

    other = store.put(
        "forces.joint_reactions/1",
        cast(
            dict[str, JsonValue],
            {
                "axes": "global",
                "rows": [
                    {
                        "joint": "J1",
                        "case": {"case": "DEAD", "case_type": "load_case"},
                        "FX_kN": 1.0,
                        "FY_kN": 0.0,
                        "FZ_kN": 0.0,
                        "MX_kNm": 0.0,
                        "MY_kNm": 0.0,
                        "MZ_kNm": 0.0,
                    }
                ],
            },
        ),
        _provenance(1),
    ).result_id
    plan = loads.LoadPlan.model_validate(
        {
            "path": "/run/model.ideaCon",
            "connection": "CON1",
            "member_map": {"B1": [{"beam_segment_id": 1, "position_host": 0.0}]},
            "effects": [
                {
                    "name": "LE1",
                    "entries": [
                        {
                            "beam_segment_id": 1,
                            "position_host": 0.0,
                            "row": {"$ref": f"{other}#/rows/0"},
                        }
                    ],
                }
            ],
        }
    )
    with pytest.raises(ContractError) as caught:
        loads.build_loading(
            current=_host_loading(),
            plan=plan,
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
        )
    assert caught.value.detail.code is ErrorCode.REF_KIND_MISMATCH


def test_only_force_fields_change(store: ResultStore) -> None:
    """AC9: only the six force fields of mapped segments differ from the read loading."""
    from eng_harness.adapters.idea import _loads as loads

    current = _host_loading()
    before = copy.deepcopy(current)
    built, _ = loads.build_loading(
        current=current,
        plan=_plan(store),
        load_map=loads.load_map_file(_SYNTHETIC_MAP),
        source=store,
        current_revision=lambda _: 1,
    )
    assert built[0]["name"] == before[0]["name"]
    assert built[0]["checkEquilibrium"] == before[0]["checkEquilibrium"]
    assert built[0]["id"] == before[0]["id"]
    untouched = next(s for s in built[0]["forcesOnSegments"] if s["beamSegmentId"] == 2)
    original = next(s for s in before[0]["forcesOnSegments"] if s["beamSegmentId"] == 2)
    assert untouched == original
    mapped = next(s for s in built[0]["forcesOnSegments"] if s["beamSegmentId"] == 1)
    original_mapped = next(s for s in before[0]["forcesOnSegments"] if s["beamSegmentId"] == 1)
    assert mapped["beamSegmentId"] == original_mapped["beamSegmentId"]
    assert mapped["position"] == original_mapped["position"]
    assert mapped["n"] != original_mapped["n"]


def test_unmapped_segment_refused(store: ResultStore) -> None:
    """AC9: a member-end row whose member is not in the plan's member map is INVALID_ARGUMENT."""
    from eng_harness.adapters.idea import _loads as loads

    plan = _plan(
        store,
        member="B1",
        member_map={"OTHER": [{"beam_segment_id": 1, "position_host": 0.0}]},
    )
    with pytest.raises(ContractError) as caught:
        loads.build_loading(
            current=_host_loading(),
            plan=plan,
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
        )
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field in {"member", "member_map", "row"}


def test_percentage_forces_gap(store: ResultStore) -> None:
    """AC9: an effect with a non-empty forcesPercentageOnSegments raises NotImplementedGap IG-8."""
    from eng_harness.adapters.idea import _loads as loads

    current = _host_loading()
    current[0]["forcesPercentageOnSegments"] = [
        {"beamSegmentId": 1, "position": 0.0, "n": 10.0, "qy": 0.0, "qz": 0.0, "mx": 0.0, "my": 0.0, "mz": 0.0}
    ]
    with pytest.raises(NotImplementedGap) as caught:
        loads.build_loading(
            current=current,
            plan=_plan(store),
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
        )
    assert "IG-8" in caught.value.evidence


def test_unknown_segment_refused(store: ResultStore) -> None:
    """AC9: a plan entry naming a segment that does not exist is INVALID_ARGUMENT before the write."""
    from eng_harness.adapters.idea import _loads as loads

    plan = _plan(store, beam_segment_id=99, position_host=0.0)
    with pytest.raises(ContractError) as caught:
        loads.build_loading(
            current=_host_loading(),
            plan=plan,
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
        )
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field in {
        "beam_segment_id",
        "position_host",
        "entries",
        "segment",
    }


def test_component_csi_fields_match_spec() -> None:
    """AC8 / §4.7: COMPONENT_CSI_FIELDS lists the six IDEA components and their forces.member_end/1 fields."""
    from eng_harness.adapters.idea import _loads as loads

    assert dict(loads.COMPONENT_CSI_FIELDS) == {
        "n": "P_kN",
        "qy": "V2_kN",
        "qz": "V3_kN",
        "mx": "T_kNm",
        "my": "M2_kNm",
        "mz": "M3_kNm",
    }
    assert loads.FORCE_KEYS == ("n", "qy", "qz", "mx", "my", "mz")


def test_shipped_map_signs_unset_and_status_unconfirmed() -> None:
    """AC7: shipped map status is unconfirmed and every sign_i/sign_j is unset (None)."""
    from eng_harness.adapters.idea import _loads as loads

    shipped = loads.load_shipped_map()
    assert shipped.status == "unconfirmed"
    assert shipped.sign_convention == "host_local/1"
    assert shipped.source == "idea/_load_map.toml"
    expected = dict(zip(_COMPONENTS, _CSI_FIELDS, strict=True))
    for name in _COMPONENTS:
        entry = shipped.components[name]
        assert entry.sign_i is None
        assert entry.sign_j is None
        assert entry.csi_field == expected[name]


def test_confirmed_map_with_unset_sign_raises_ig2() -> None:
    """AC7: status confirmed but a sign still unset raises NotImplementedGap IG-2."""
    from eng_harness.adapters.idea import _loads as loads

    components = {
        name: loads.LoadMapComponent(csi_field=field, sign_i=1, sign_j=None if name == "mz" else 1)
        for name, field in zip(_COMPONENTS, _CSI_FIELDS, strict=True)
    }
    load_map = loads.LoadMap(
        status="confirmed",
        sign_convention="host_local/1",
        components=components,
        source="synthetic-unset-sign",
    )
    with pytest.raises(NotImplementedGap) as caught:
        loads.require_confirmed_map(load_map)
    assert "IG-2" in caught.value.evidence


def test_wrong_sign_convention_refused(store: ResultStore) -> None:
    """AC8: a confirmed map whose sign_convention is not host_local/1 is INVALID_ARGUMENT."""
    from eng_harness.adapters.idea import _loads as loads

    base = loads.load_map_file(_SYNTHETIC_MAP)
    bad = loads.LoadMap(
        status=base.status,
        sign_convention="other/1",
        components=base.components,
        source=base.source,
    )
    with pytest.raises(ContractError) as caught:
        loads.build_loading(
            current=_host_loading(),
            plan=_plan(store),
            load_map=bad,
            source=store,
            current_revision=lambda _: 1,
        )
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "sign_convention"


def test_duplicate_effect_name_refused(store: ResultStore) -> None:
    """AC8: two plan effects with the same name are INVALID_ARGUMENT."""
    from eng_harness.adapters.idea import _loads as loads

    rid = _put_member_end(store, _row())
    plan = loads.LoadPlan.model_validate(
        {
            "path": "/run/model.ideaCon",
            "connection": "CON1",
            "member_map": {"B1": [{"beam_segment_id": 1, "position_host": 0.0}]},
            "effects": [
                {
                    "name": "LE1",
                    "entries": [{"beam_segment_id": 1, "position_host": 0.0, "row": {"$ref": f"{rid}#/rows/0"}}],
                },
                {
                    "name": "LE1",
                    "entries": [{"beam_segment_id": 1, "position_host": 0.0, "row": {"$ref": f"{rid}#/rows/0"}}],
                },
            ],
        }
    )
    with pytest.raises(ContractError) as caught:
        loads.build_loading(
            current=_host_loading(),
            plan=plan,
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
        )
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "name"
    assert "LE1" in caught.value.detail.message


def test_missing_host_effect_refused(store: ResultStore) -> None:
    """AC9: a plan effect name absent from the host loading is INVALID_ARGUMENT."""
    from eng_harness.adapters.idea import _loads as loads

    plan = _plan(store)
    with pytest.raises(ContractError) as caught:
        loads.build_loading(
            current=[{"id": 1, "name": "OTHER", "forcesOnSegments": [], "forcesPercentageOnSegments": []}],
            plan=plan,
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
        )
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "name"
    assert "LE1" in caught.value.detail.message


def test_missing_forces_on_segments_refused(store: ResultStore) -> None:
    """AC9: a host effect without forcesOnSegments is INVALID_ARGUMENT."""
    from eng_harness.adapters.idea import _loads as loads

    with pytest.raises(ContractError) as caught:
        loads.build_loading(
            current=[{"id": 1, "name": "LE1", "forcesPercentageOnSegments": []}],
            plan=_plan(store),
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
        )
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "forcesOnSegments"


def test_segment_not_mapped_for_member_refused(store: ResultStore) -> None:
    """AC9: a plan entry whose segment is not listed for the row member is INVALID_ARGUMENT."""
    from eng_harness.adapters.idea import _loads as loads

    plan = _plan(
        store,
        beam_segment_id=1,
        position_host=0.0,
        member_map={"B1": [{"beam_segment_id": 1, "position_host": 0.5}]},
    )
    with pytest.raises(ContractError) as caught:
        loads.build_loading(
            current=_host_loading(),
            plan=plan,
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
        )
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "member_map"


def test_end_j_applies_sign_j(store: ResultStore) -> None:
    """AC8: end j uses sign_j; a synthetic map with sign_j=-1 flips every converted component."""
    from eng_contract.units import convert

    from eng_harness.adapters.idea import _loads as loads

    components = {
        name: loads.LoadMapComponent(csi_field=field, sign_i=1, sign_j=-1)
        for name, field in zip(_COMPONENTS, _CSI_FIELDS, strict=True)
    }
    load_map = loads.LoadMap(
        status="confirmed",
        sign_convention="host_local/1",
        components=components,
        source="synthetic-sign-j",
    )
    plan = _plan(store, end="j", row_override=_row(end="j", p=10.0, v2=1.0, v3=-2.0, t=0.5, m2=3.0, m3=-4.0))
    built, _ = loads.build_loading(
        current=_host_loading(),
        plan=plan,
        load_map=load_map,
        source=store,
        current_revision=lambda _: 1,
    )
    seg = next(s for s in built[0]["forcesOnSegments"] if s["beamSegmentId"] == 1)
    assert seg["n"] == -1.0 * convert(10.0, "kN", "N")
    assert seg["qy"] == -1.0 * convert(1.0, "kN", "N")
    assert seg["qz"] == -1.0 * convert(-2.0, "kN", "N")
    assert seg["mx"] == -1.0 * convert(0.5, "kN.m", "N.m")
    assert seg["my"] == -1.0 * convert(3.0, "kN.m", "N.m")
    assert seg["mz"] == -1.0 * convert(-4.0, "kN.m", "N.m")


def test_bad_end_value_refused(store: ResultStore, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC8: a member-end row whose end is not i or j is INVALID_ARGUMENT."""
    from types import SimpleNamespace

    from eng_harness.adapters.idea import _loads as loads

    plan = _plan(store)
    bad_row = _row(end="i")
    bad_row["end"] = "k"

    def _fake_resolve(ref: object, rule: object, source: object, current_revision: object) -> object:
        text = getattr(ref, "ref", None) or str(ref)
        return SimpleNamespace(ref=text, value=bad_row)

    monkeypatch.setattr("eng_harness.adapters.idea._loads.resolve_ref", _fake_resolve)
    with pytest.raises(ContractError) as caught:
        loads.build_loading(
            current=_host_loading(),
            plan=plan,
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
        )
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "row"
    assert "end" in caught.value.detail.message


def test_missing_numeric_csi_field_refused(store: ResultStore, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC8: a row missing a CSI force field is INVALID_ARGUMENT."""
    from types import SimpleNamespace

    from eng_harness.adapters.idea import _loads as loads

    plan = _plan(store)
    bad_row = _row()
    del bad_row["P_kN"]

    def _fake_resolve(ref: object, rule: object, source: object, current_revision: object) -> object:
        text = getattr(ref, "ref", None) or str(ref)
        return SimpleNamespace(ref=text, value=bad_row)

    monkeypatch.setattr("eng_harness.adapters.idea._loads.resolve_ref", _fake_resolve)
    with pytest.raises(ContractError) as caught:
        loads.build_loading(
            current=_host_loading(),
            plan=plan,
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
        )
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "row"
    assert "P_kN" in caught.value.detail.message


def test_literal_force_field_on_entry_refused(store: ResultStore) -> None:
    """AC8: literal P_kN (and siblings) on a load entry are refused even when row is a ref."""
    from eng_harness.adapters.idea import _loads as loads

    rid = _put_member_end(store, _row())
    with pytest.raises(ContractError) as caught:
        loads.build_loading_from_raw(
            current=_host_loading(),
            plan={
                "path": "/run/model.ideaCon",
                "connection": "CON1",
                "member_map": {"B1": [{"beam_segment_id": 1, "position_host": 0.0}]},
                "effects": [
                    {
                        "name": "LE1",
                        "entries": [
                            {
                                "beam_segment_id": 1,
                                "position_host": 0.0,
                                "row": {"$ref": f"{rid}#/rows/0"},
                                "P_kN": 10.0,
                            }
                        ],
                    }
                ],
            },
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
        )
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert "literal force" in caught.value.detail.message


def test_non_mapping_row_refused(store: ResultStore) -> None:
    """AC8: a non-mapping row value is refused as an engineering quantity."""
    from eng_harness.adapters.idea import _loads as loads

    with pytest.raises(ContractError) as caught:
        loads.build_loading_from_raw(
            current=_host_loading(),
            plan={
                "path": "/run/model.ideaCon",
                "connection": "CON1",
                "member_map": {"B1": [{"beam_segment_id": 1, "position_host": 0.0}]},
                "effects": [
                    {
                        "name": "LE1",
                        "entries": [
                            {
                                "beam_segment_id": 1,
                                "position_host": 0.0,
                                "row": 10.0,
                            }
                        ],
                    }
                ],
            },
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
        )
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "row"


def test_optional_sign_rejects_zero_and_other() -> None:
    """AC7: load-map signs accept only +1, -1 or unset; 0 and 2 raise ValueError."""
    from eng_harness.adapters.idea import _loads as loads

    assert loads._optional_sign(None) is None
    assert loads._optional_sign(1) == 1
    assert loads._optional_sign(-1) == -1
    with pytest.raises(ValueError, match="load-map sign must be \\+1, -1 or unset") as zero:
        loads._optional_sign(0)
    assert str(zero.value) == "load-map sign must be +1, -1 or unset"
    with pytest.raises(ValueError, match="load-map sign must be \\+1, -1 or unset") as two:
        loads._optional_sign(2)
    assert str(two.value) == "load-map sign must be +1, -1 or unset"


def test_parse_map_rejects_wrong_csi_field(tmp_path: Path) -> None:
    """§4.7: a map whose csi_field drifts from the listed forces.member_end/1 name is refused."""
    from eng_harness.adapters.idea import _loads as loads

    path = tmp_path / "bad_map.toml"
    path.write_text(
        "\n".join(
            [
                'status = "confirmed"',
                'sign_convention = "host_local/1"',
                "[components.n]",
                'csi_field = "WRONG_kN"',
                "sign_i = 1",
                "sign_j = 1",
                *[
                    line
                    for name, field in zip(_COMPONENTS[1:], _CSI_FIELDS[1:], strict=True)
                    for line in (f"[components.{name}]", f'csi_field = "{field}"', "sign_i = 1", "sign_j = 1")
                ],
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="csi_field must be P_kN"):
        loads.load_map_file(path)


def test_load_map_status_issue_fields() -> None:
    """§4.10: LOADS_UNCONFIRMED_MAP carries INFO severity, exact code/message and the connection subject."""
    from eng_contract.issues import Severity
    from eng_contract.verdicts import SubjectKind

    from eng_harness.adapters.idea import _checks as checks
    from eng_harness.adapters.idea import _loads as loads

    shipped = loads.load_shipped_map()
    issue = checks.load_map_status_issue(shipped, connection="CON1")
    assert issue is not None
    assert issue.code == "LOADS_UNCONFIRMED_MAP"
    assert issue.severity is Severity.INFO
    assert issue.message == ("load map status is unconfirmed (IG-2); verdicts stay draft until the owner confirms it")
    assert issue.subject.kind is SubjectKind.JOINT
    assert issue.subject.id == "CON1"
    assert issue.subject.station_mm is None
    assert issue.subject.case is None
    confirmed = loads.load_map_file(_SYNTHETIC_MAP)
    assert checks.load_map_status_issue(confirmed, connection="CON1") is None


def test_issues_from_set_loads_reply_zero_dropped() -> None:
    """AC10 / §4.10: LOAD_EFFECT_ZERO_DROPPED names each dropped effect; empty/non-list yields no issue."""
    from eng_contract.issues import Severity
    from eng_contract.verdicts import SubjectKind

    from eng_harness.adapters.idea import _checks as checks

    assert checks.issues_from_set_loads_reply({}, connection="CON1") == []
    assert checks.issues_from_set_loads_reply({"dropped_zero": []}, connection="CON1") == []
    assert checks.issues_from_set_loads_reply({"dropped_zero": None}, connection="CON1") == []
    assert checks.issues_from_set_loads_reply({"dropped_zero": "ZERO"}, connection="CON1") == []
    issues = checks.issues_from_set_loads_reply({"dropped_zero": ["ZERO", "", "KEEP"]}, connection="CON1")
    assert len(issues) == 1
    issue = issues[0]
    assert issue.code == "LOAD_EFFECT_ZERO_DROPPED"
    assert issue.severity is Severity.WARNING
    assert issue.message == "host dropped all-zero load effects before the write: ZERO, KEEP"
    assert issue.subject.kind is SubjectKind.JOINT
    assert issue.subject.id == "CON1"
    assert issue.subject.station_mm is None
    assert issue.subject.case is None


def _seg(beam: int, position: float, **forces: float) -> dict[str, Any]:
    row = {"beamSegmentId": beam, "position": position, "n": 0.0, "qy": 0.0, "qz": 0.0, "mx": 0.0, "my": 0.0, "mz": 0.0}
    row.update(forces)
    return row


def test_compare_loads_readback_unavailable() -> None:
    """AC10 / §4.10: READBACK_UNAVAILABLE when got is None or tolerance is missing or not positive."""
    from eng_contract.issues import Severity
    from eng_contract.verdicts import SubjectKind

    from eng_harness.adapters.idea import _checks as checks

    requested = [{"name": "LE1", "forcesOnSegments": [_seg(1, 0.0, n=1000.0)]}]
    for got, tol, message in (
        (None, 1e-9, "load read-back reply was not available"),
        (
            [{"name": "LE1", "forcesOnSegments": [_seg(1, 0.0, n=1000.0)]}],
            None,
            "no read-back tolerance (checks.readback_relative_tolerance_ratio)",
        ),
        (
            [{"name": "LE1", "forcesOnSegments": [_seg(1, 0.0, n=1000.0)]}],
            0.0,
            "no read-back tolerance (checks.readback_relative_tolerance_ratio)",
        ),
        (
            [{"name": "LE1", "forcesOnSegments": [_seg(1, 0.0, n=1000.0)]}],
            -0.1,
            "no read-back tolerance (checks.readback_relative_tolerance_ratio)",
        ),
    ):
        issues = checks.compare_loads_readback(
            requested=requested,
            got=got,
            tolerance_ratio=tol,
            connection="CON1",
        )
        assert len(issues) == 1
        assert issues[0].code == "READBACK_UNAVAILABLE"
        assert issues[0].severity is Severity.ERROR
        assert issues[0].message == message
        assert issues[0].subject.kind is SubjectKind.JOINT
        assert issues[0].subject.id == "CON1"


def test_compare_loads_readback_missing_effect_and_segment() -> None:
    """AC10: absent effect or segment on read-back is READBACK_MISMATCH with the exact message."""
    from eng_contract.issues import Severity

    from eng_harness.adapters.idea import _checks as checks

    requested = [{"name": "LE1", "forcesOnSegments": [_seg(1, 0.0, n=1000.0), _seg(2, 0.5, n=500.0)]}]
    missing_effect = checks.compare_loads_readback(
        requested=requested,
        got=[{"name": "OTHER", "forcesOnSegments": [_seg(1, 0.0, n=1000.0)]}],
        tolerance_ratio=1e-9,
        connection="CON1",
    )
    assert len(missing_effect) == 1
    assert missing_effect[0].code == "READBACK_MISMATCH"
    assert missing_effect[0].severity is Severity.ERROR
    assert missing_effect[0].message == "effect 'LE1' is absent on read-back"

    missing_seg = checks.compare_loads_readback(
        requested=requested,
        got=[{"name": "LE1", "forcesOnSegments": [_seg(1, 0.0, n=1000.0)]}],
        tolerance_ratio=1e-9,
        connection="CON1",
    )
    assert any(
        issue.code == "READBACK_MISMATCH" and issue.message == "segment (2, 0.5) of effect 'LE1' is absent on read-back"
        for issue in missing_seg
    )


def test_compare_loads_readback_tolerance_boundary_and_per_field() -> None:
    """AC10: exactly at tolerance is ok; just beyond mismatches; every FORCE_KEYS field is checked."""
    import math

    from eng_harness.adapters.idea import _checks as checks
    from eng_harness.adapters.idea._loads import FORCE_KEYS

    tol = 0.01
    wanted = 1000.0
    threshold = tol * abs(wanted)
    at_boundary = wanted + threshold
    beyond = math.nextafter(at_boundary, math.inf)
    base_seg = _seg(1, 0.0, n=wanted, qy=wanted, qz=wanted, mx=wanted, my=wanted, mz=wanted)
    requested = [{"name": "LE1", "forcesOnSegments": [dict(base_seg)]}]

    ok_got = [{"name": "LE1", "forcesOnSegments": [{**base_seg, "n": at_boundary}]}]
    assert checks.compare_loads_readback(requested=requested, got=ok_got, tolerance_ratio=tol, connection="CON1") == []

    bad_got = [{"name": "LE1", "forcesOnSegments": [{**base_seg, "n": beyond}]}]
    bad = checks.compare_loads_readback(requested=requested, got=bad_got, tolerance_ratio=tol, connection="CON1")
    assert len(bad) == 1
    assert bad[0].code == "READBACK_MISMATCH"
    assert "field n" in bad[0].message
    assert f"reads {beyond}" in bad[0].message
    assert f"requested {wanted}" in bad[0].message

    # wanted == 0 uses scale 1.0 (spec relative tolerance against unit scale when requested is zero)
    zero_req = [{"name": "LE1", "forcesOnSegments": [_seg(1, 0.0)]}]
    zero_ok = [{"name": "LE1", "forcesOnSegments": [_seg(1, 0.0, n=tol)]}]
    assert checks.compare_loads_readback(requested=zero_req, got=zero_ok, tolerance_ratio=tol, connection="CON1") == []
    zero_bad = [{"name": "LE1", "forcesOnSegments": [_seg(1, 0.0, n=math.nextafter(tol, math.inf))]}]
    zero_issues = checks.compare_loads_readback(
        requested=zero_req, got=zero_bad, tolerance_ratio=tol, connection="CON1"
    )
    assert any(issue.code == "READBACK_MISMATCH" and "field n" in issue.message for issue in zero_issues)

    # negative wanted uses abs(wanted) as scale
    neg = -500.0
    neg_thresh = tol * abs(neg)
    neg_req = [{"name": "LE1", "forcesOnSegments": [_seg(1, 0.0, n=neg)]}]
    neg_ok = [{"name": "LE1", "forcesOnSegments": [_seg(1, 0.0, n=neg + neg_thresh)]}]
    assert checks.compare_loads_readback(requested=neg_req, got=neg_ok, tolerance_ratio=tol, connection="CON1") == []
    neg_bad = [{"name": "LE1", "forcesOnSegments": [_seg(1, 0.0, n=math.nextafter(neg + neg_thresh, math.inf))]}]
    assert any(
        issue.code == "READBACK_MISMATCH" and "field n" in issue.message
        for issue in checks.compare_loads_readback(
            requested=neg_req, got=neg_bad, tolerance_ratio=tol, connection="CON1"
        )
    )

    # every FORCE_KEYS field reports its own mismatch
    for force in FORCE_KEYS:
        mutated = dict(base_seg)
        mutated[force] = beyond
        got = [{"name": "LE1", "forcesOnSegments": [mutated]}]
        issues = checks.compare_loads_readback(requested=requested, got=got, tolerance_ratio=tol, connection="CON1")
        assert len(issues) == 1
        assert issues[0].code == "READBACK_MISMATCH"
        assert f"field {force}" in issues[0].message


def test_require_confirmed_map_accepts_all_minus_one_signs() -> None:
    """AC7: every sign may be -1; require_confirmed_map accepts the (-1, 1) membership exactly."""
    from eng_harness.adapters.idea import _loads as loads

    components = {
        name: loads.LoadMapComponent(csi_field=field, sign_i=-1, sign_j=-1)
        for name, field in zip(_COMPONENTS, _CSI_FIELDS, strict=True)
    }
    load_map = loads.LoadMap(
        status="confirmed",
        sign_convention="host_local/1",
        components=components,
        source="synthetic-all-minus",
    )
    loads.require_confirmed_map(load_map)


def test_require_confirmed_map_unknown_component() -> None:
    """AC7: an unknown component name on a confirmed map is INVALID_ARGUMENT."""
    from eng_harness.adapters.idea import _loads as loads

    components = {
        name: loads.LoadMapComponent(csi_field=field, sign_i=1, sign_j=1)
        for name, field in zip(_COMPONENTS, _CSI_FIELDS, strict=True)
    }
    components["extra"] = loads.LoadMapComponent(csi_field="P_kN", sign_i=1, sign_j=1)
    load_map = loads.LoadMap(
        status="confirmed",
        sign_convention="host_local/1",
        components=components,
        source="synthetic-extra",
    )
    with pytest.raises(ContractError) as caught:
        loads.require_confirmed_map(load_map)
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "components"
    assert "extra" in caught.value.detail.message


def test_wrong_sign_convention_exact_message(store: ResultStore) -> None:
    """AC8: sign_convention refusal carries the exact message text."""
    from eng_harness.adapters.idea import _loads as loads

    base = loads.load_map_file(_SYNTHETIC_MAP)
    bad = loads.LoadMap(
        status=base.status,
        sign_convention="other/1",
        components=base.components,
        source=base.source,
    )
    with pytest.raises(ContractError) as caught:
        loads.build_loading(
            current=_host_loading(),
            plan=_plan(store),
            load_map=bad,
            source=store,
            current_revision=lambda _: 1,
        )
    assert caught.value.detail.message == "load map sign_convention must be host_local/1"


def test_build_loading_from_raw_success_and_invalid_plan(store: ResultStore) -> None:
    """AC8: a valid raw plan builds; an invalid shape becomes INVALID_ARGUMENT after refuse_literal."""
    from eng_harness.adapters.idea import _loads as loads

    rid = _put_member_end(store, _row())
    built, provenance = loads.build_loading_from_raw(
        current=_host_loading(),
        plan={
            "path": "/run/model.ideaCon",
            "connection": "CON1",
            "member_map": {"B1": [{"beam_segment_id": 1, "position_host": 0.0}]},
            "effects": [
                {
                    "name": "LE1",
                    "entries": [
                        {
                            "beam_segment_id": 1,
                            "position_host": 0.0,
                            "row": {"$ref": f"{rid}#/rows/0"},
                        }
                    ],
                }
            ],
        },
        load_map=loads.load_map_file(_SYNTHETIC_MAP),
        source=store,
        current_revision=lambda _: 1,
    )
    assert built[0]["forcesOnSegments"][0]["n"] == 10000.0
    assert provenance

    with pytest.raises(ContractError) as caught:
        loads.build_loading_from_raw(
            current=_host_loading(),
            plan={
                "path": "/run/model.ideaCon",
                "connection": "CON1",
                "member_map": {"B1": [{"beam_segment_id": 1, "position_host": 0.0}]},
                "effects": [],
            },
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
        )
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "row"
    assert caught.value.detail.message == "load plan is not valid"


def test_refuse_literal_skips_non_mapping_then_catches_literal(store: ResultStore) -> None:
    """AC8: non-mapping effects/entries are skipped (continue); a later literal still refuses."""
    from eng_harness.adapters.idea import _loads as loads

    with pytest.raises(ContractError) as caught:
        loads.build_loading_from_raw(
            current=_host_loading(),
            plan={
                "path": "/run/model.ideaCon",
                "connection": "CON1",
                "member_map": {"B1": [{"beam_segment_id": 1, "position_host": 0.0}]},
                "effects": [
                    "skip-me",
                    {
                        "name": "LE1",
                        "entries": [
                            "skip-entry",
                            {
                                "beam_segment_id": 1,
                                "position_host": 0.0,
                                "row": {
                                    "member": "B1",
                                    "case": {"case": "DEAD", "case_type": "load_case"},
                                    "end": "i",
                                    "station_mm": 0.0,
                                    "P_kN": 1.0,
                                    "V2_kN": 0.0,
                                    "V3_kN": 0.0,
                                    "T_kNm": 0.0,
                                    "M2_kNm": 0.0,
                                    "M3_kNm": 0.0,
                                },
                            },
                        ],
                    },
                ],
            },
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
        )
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "row"
    assert "reference" in caught.value.detail.message


def test_host_loads_missing_force_defaults_to_zero() -> None:
    """AC16: a segment omitting a force key converts the default 0.0 (not None / KeyError)."""
    from eng_harness.adapters.idea import _loads as loads

    canonical = loads.host_loads_to_canonical(
        connection="C",
        effects=[{"name": "LE1", "forcesOnSegments": [{"beamSegmentId": 1, "position": 0.0}]}],
        file_sha256="ab" * 32,
    )
    seg = canonical.effects[0].segments[0]
    assert seg.N_kN == 0.0
    assert seg.Qy_kN == 0.0
    assert seg.Qz_kN == 0.0
    assert seg.Mx_kNm == 0.0
    assert seg.My_kNm == 0.0
    assert seg.Mz_kNm == 0.0


def test_find_segment_skips_non_dict_and_bad_position() -> None:
    """AC9: _find_segment continues past non-dicts and non-numeric positions; exact match returns the dict."""
    from eng_harness.adapters.idea import _loads as loads

    segments: list[Any] = [
        "skip",
        {"beamSegmentId": 1, "position": "bad"},
        {"beamSegmentId": 1, "position": 0.0, "n": 7.0},
    ]
    found = loads._find_segment(segments, 1, 0.0)
    assert found["n"] == 7.0
    with pytest.raises(ContractError) as caught:
        loads._find_segment(segments, 9, 0.0)
    assert caught.value.detail.field == "beam_segment_id"
    assert caught.value.detail.message == "segment (9, 0.0) does not exist in the host loading"


def test_raise_host_unexpected_and_mapped() -> None:
    """AC10: _raise_host maps a typed error reply; an unparseable body is UNEXPECTED_REPLY HOST_ERROR."""
    from types import SimpleNamespace

    from eng_harness.adapters.idea import _loads as loads
    from eng_harness.servers import CallEffect

    with pytest.raises(ContractError) as plain:
        loads._raise_host({"not": "an error shape"}, tool="idea_native_get_loads", effect=CallEffect.READ, ids=None)
    assert plain.value.detail.code is ErrorCode.HOST_ERROR
    assert plain.value.detail.host_code == "UNEXPECTED_REPLY"
    assert plain.value.detail.host_method == "idea_native_get_loads"
    assert plain.value.detail.message == "idea_native_get_loads failed"

    class _Dump:
        def model_dump(self, *, by_alias: bool, mode: str) -> dict[str, Any]:
            assert by_alias is True
            assert mode == "json"
            return {
                "isError": True,
                "content": [
                    {
                        "type": "text",
                        "text": '{"code":"idea_error","message":"host said no","data":null}',
                    }
                ],
            }

    # A CallToolResult-shaped dump that parse_error_reply understands varies; assert kwargs reach the mapper path.
    with pytest.raises(ContractError) as mapped:
        loads._raise_host(
            SimpleNamespace(
                model_dump=lambda **kw: {
                    "isError": True,
                    "content": [{"type": "text", "text": '{"code":"idea_error","message":"host said no"}'}],
                }
            ),
            tool="idea_native_set_loads",
            effect=CallEffect.WRITE,
            ids=None,
        )
    assert mapped.value.detail.code is ErrorCode.HOST_ERROR
    assert mapped.value.detail.host_method == "idea_native_set_loads"


def test_set_loads_records_exact_calls_and_result(store: ResultStore, tmp_path: Path) -> None:
    """AC10: set_loads uses READ/WRITE effects, exact tool args, and returns dropped_zero / effects_written / issues."""
    import json
    from types import SimpleNamespace

    import anyio
    from mcp import types

    from eng_harness.adapters.idea import _loads as loads
    from eng_harness.servers import CallEffect

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    model = run_dir / "model.ideaCon"
    model.write_text("{}", encoding="utf-8")
    host_loads = _host_loading()
    calls: list[tuple[str, str, str, dict[str, Any], CallEffect]] = []

    def _ok(body: dict[str, Any]) -> types.CallToolResult:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(body))],
            is_error=False,
        )

    class _Sessions:
        async def call(
            self, server: str, role: str, tool: str, args: dict[str, Any], effect: CallEffect
        ) -> types.CallToolResult:
            calls.append((server, role, tool, dict(args), effect))
            if tool == "idea_native_get_loads":
                get_count = sum(1 for c in calls if c[2] == "idea_native_get_loads")
                if get_count == 1:
                    return _ok({"loads": host_loads})
                out = Path(str(args["path"]))
                data = json.loads(out.read_text(encoding="utf-8"))
                return _ok({"loads": data["loads"]})
            if tool == "idea_native_set_loads":
                out = Path(str(args["out_path"]))
                out.write_text(json.dumps({"loads": args["loads"]}), encoding="utf-8")
                return _ok({"dropped_zero": ["ZERO"], "effects_written": 1})
            raise AssertionError(f"unexpected tool {tool}")

    plan = _plan(store)
    # point the plan at the temp model inside run_dir
    plan = loads.LoadPlan.model_validate(
        {
            "path": str(model),
            "connection": "CON1",
            "member_map": {"B1": [{"beam_segment_id": 1, "position_host": 0.0}]},
            "effects": [
                {
                    "name": "LE1",
                    "entries": [
                        {
                            "beam_segment_id": 1,
                            "position_host": 0.0,
                            "row": {"$ref": plan.effects[0].entries[0].row.ref},
                        }
                    ],
                }
            ],
        }
    )

    async def body() -> loads.SetLoadsResult:
        return await loads.set_loads(
            sessions=_Sessions(),
            server="idea",
            role="main",
            plan=plan,
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
            run_dir=run_dir,
            readback_relative_tolerance_ratio=1e-9,
            approved=True,
            ids=SimpleNamespace(),
        )

    result = anyio.run(body)
    assert result.dropped_zero == ("ZERO",)
    assert result.effects_written == 1
    assert result.out_path.exists()
    assert result.readback_issues == ()
    assert len(calls) == 3
    get1, write, get2 = calls
    assert get1[0] == "idea"
    assert get1[1] == "main"
    assert get1[2] == "idea_native_get_loads"
    assert get1[3]["connection_id"] == "CON1"
    assert Path(get1[3]["path"]).resolve() == model.resolve()
    assert get1[4] is CallEffect.READ
    assert write[2] == "idea_native_set_loads"
    assert write[4] is CallEffect.WRITE
    assert write[3]["connection_id"] == "CON1"
    assert write[3]["confirm"] is True
    assert "out_path" in write[3]
    assert write[3]["path"] == get1[3]["path"]
    assert isinstance(write[3]["loads"], list)
    assert get2[2] == "idea_native_get_loads"
    assert get2[4] is CallEffect.READ
    assert get2[3]["connection_id"] == "CON1"
    assert Path(get2[3]["path"]).resolve() == result.out_path.resolve()


def test_set_loads_get_error_raises_mapped_host(store: ResultStore, tmp_path: Path) -> None:
    """AC10: a failing idea_native_get_loads raises through _raise_host with READ and the tool name."""
    import json

    import anyio
    from mcp import types

    from eng_harness.adapters.idea import _loads as loads
    from eng_harness.servers import CallEffect

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    model = run_dir / "model.ideaCon"
    model.write_text("{}", encoding="utf-8")
    seen: list[tuple[str, CallEffect]] = []

    class _Sessions:
        async def call(
            self, server: str, role: str, tool: str, args: dict[str, Any], effect: CallEffect
        ) -> types.CallToolResult:
            seen.append((tool, effect))
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=json.dumps({"code": "idea_error", "message": "cannot read"}),
                    )
                ],
                is_error=True,
            )

    plan = loads.LoadPlan.model_validate(
        {
            "path": str(model),
            "connection": "CON1",
            "member_map": {"B1": [{"beam_segment_id": 1, "position_host": 0.0}]},
            "effects": [
                {
                    "name": "LE1",
                    "entries": [
                        {
                            "beam_segment_id": 1,
                            "position_host": 0.0,
                            "row": {"$ref": _put_member_end(store, _row()) + "#/rows/0"},
                        }
                    ],
                }
            ],
        }
    )

    async def body() -> None:
        await loads.set_loads(
            sessions=_Sessions(),
            server="idea",
            role="main",
            plan=plan,
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
            run_dir=run_dir,
            readback_relative_tolerance_ratio=1e-9,
            approved=True,
            ids=None,
        )

    with pytest.raises(ContractError) as caught:
        anyio.run(body)
    assert caught.value.detail.code is ErrorCode.HOST_ERROR
    assert caught.value.detail.host_method == "idea_native_get_loads"
    assert seen == [("idea_native_get_loads", CallEffect.READ)]


def test_set_loads_missing_loads_body(store: ResultStore, tmp_path: Path) -> None:
    """AC10: get_loads success without a loads list is HOST_ERROR UNEXPECTED_REPLY."""
    import json

    import anyio
    from mcp import types

    from eng_harness.adapters.idea import _loads as loads
    from eng_harness.servers import CallEffect

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    model = run_dir / "model.ideaCon"
    model.write_text("{}", encoding="utf-8")

    class _Sessions:
        async def call(
            self, server: str, role: str, tool: str, args: dict[str, Any], effect: CallEffect
        ) -> types.CallToolResult:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps({"ok": True}))],
                is_error=False,
            )

    plan = loads.LoadPlan.model_validate(
        {
            "path": str(model),
            "connection": "CON1",
            "member_map": {"B1": [{"beam_segment_id": 1, "position_host": 0.0}]},
            "effects": [
                {
                    "name": "LE1",
                    "entries": [
                        {
                            "beam_segment_id": 1,
                            "position_host": 0.0,
                            "row": {"$ref": _put_member_end(store, _row()) + "#/rows/0"},
                        }
                    ],
                }
            ],
        }
    )

    async def body() -> None:
        await loads.set_loads(
            sessions=_Sessions(),
            server="idea",
            role="main",
            plan=plan,
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
            run_dir=run_dir,
            readback_relative_tolerance_ratio=1e-9,
            approved=False,
            ids=None,
        )

    with pytest.raises(ContractError) as caught:
        anyio.run(body)
    assert caught.value.detail.code is ErrorCode.HOST_ERROR
    assert caught.value.detail.host_code == "UNEXPECTED_REPLY"
    assert caught.value.detail.message == "idea_native_get_loads returned no loads"


def _set_loads_plan(store: ResultStore, model: Path) -> Any:
    from eng_harness.adapters.idea import _loads as loads

    return loads.LoadPlan.model_validate(
        {
            "path": str(model),
            "connection": "CON1",
            "member_map": {"B1": [{"beam_segment_id": 1, "position_host": 0.0}]},
            "effects": [
                {
                    "name": "LE1",
                    "entries": [
                        {
                            "beam_segment_id": 1,
                            "position_host": 0.0,
                            "row": {"$ref": _put_member_end(store, _row()) + "#/rows/0"},
                        }
                    ],
                }
            ],
        }
    )


def test_set_loads_write_error_and_missing_out_path(store: ResultStore, tmp_path: Path) -> None:
    """AC10: write failure maps through _raise_host (WRITE); missing out_path file is idea_error."""
    import json

    import anyio
    from mcp import types

    from eng_harness.adapters.idea import _loads as loads
    from eng_harness.servers import CallEffect

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    model = run_dir / "model.ideaCon"
    model.write_text("{}", encoding="utf-8")
    host_loads = _host_loading()

    class _WriteFail:
        async def call(
            self, server: str, role: str, tool: str, args: dict[str, Any], effect: CallEffect
        ) -> types.CallToolResult:
            if tool == "idea_native_get_loads":
                assert effect is CallEffect.READ
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=json.dumps({"loads": host_loads}))],
                    is_error=False,
                )
            assert tool == "idea_native_set_loads"
            assert effect is CallEffect.WRITE
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=json.dumps({"code": "idea_error", "message": "cannot write"}),
                    )
                ],
                is_error=True,
            )

    async def write_fail() -> None:
        await loads.set_loads(
            sessions=_WriteFail(),
            server="idea",
            role="main",
            plan=_set_loads_plan(store, model),
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
            run_dir=run_dir,
            readback_relative_tolerance_ratio=1e-9,
            approved=True,
            ids=None,
        )

    with pytest.raises(ContractError) as caught:
        anyio.run(write_fail)
    assert caught.value.detail.code is ErrorCode.HOST_ERROR
    assert caught.value.detail.host_method == "idea_native_set_loads"

    class _NoFile:
        async def call(
            self, server: str, role: str, tool: str, args: dict[str, Any], effect: CallEffect
        ) -> types.CallToolResult:
            if tool == "idea_native_get_loads":
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=json.dumps({"loads": host_loads}))],
                    is_error=False,
                )
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps({"effects_written": 1}))],
                is_error=False,
            )

    async def no_file() -> None:
        await loads.set_loads(
            sessions=_NoFile(),
            server="idea",
            role="main",
            plan=_set_loads_plan(store, model),
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
            run_dir=run_dir,
            readback_relative_tolerance_ratio=1e-9,
            approved=True,
            ids=None,
        )

    with pytest.raises(ContractError) as missing:
        anyio.run(no_file)
    assert missing.value.detail.code is ErrorCode.HOST_ERROR
    assert missing.value.detail.host_code == "idea_error"
    assert missing.value.detail.host_method == "idea_native_set_loads"
    assert missing.value.detail.message == "idea_native_set_loads did not write out_path"


def test_set_loads_write_no_body_and_readback_error(store: ResultStore, tmp_path: Path) -> None:
    """AC10: set_loads with empty write body; read-back get failure maps WRITE/READ tools exactly."""
    import json

    import anyio
    from mcp import types

    from eng_harness.adapters.idea import _loads as loads
    from eng_harness.servers import CallEffect

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    model = run_dir / "model.ideaCon"
    model.write_text("{}", encoding="utf-8")
    host_loads = _host_loading()

    class _NoBody:
        async def call(
            self, server: str, role: str, tool: str, args: dict[str, Any], effect: CallEffect
        ) -> types.CallToolResult:
            if tool == "idea_native_get_loads":
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=json.dumps({"loads": host_loads}))],
                    is_error=False,
                )
            # empty content → reply_body None
            return types.CallToolResult(content=[], is_error=False)

    async def no_body() -> None:
        await loads.set_loads(
            sessions=_NoBody(),
            server="idea",
            role="main",
            plan=_set_loads_plan(store, model),
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
            run_dir=run_dir,
            readback_relative_tolerance_ratio=1e-9,
            approved=True,
            ids=None,
        )

    with pytest.raises(ContractError) as caught:
        anyio.run(no_body)
    assert caught.value.detail.message == "idea_native_set_loads returned no body"
    assert caught.value.detail.host_code == "UNEXPECTED_REPLY"

    class _ReadbackFail:
        async def call(
            self, server: str, role: str, tool: str, args: dict[str, Any], effect: CallEffect
        ) -> types.CallToolResult:
            if tool == "idea_native_get_loads" and effect is CallEffect.READ and "out_path" not in args:
                # first get (path is the model)
                if Path(str(args["path"])).resolve() == model.resolve():
                    return types.CallToolResult(
                        content=[types.TextContent(type="text", text=json.dumps({"loads": host_loads}))],
                        is_error=False,
                    )
                return types.CallToolResult(
                    content=[
                        types.TextContent(
                            type="text",
                            text=json.dumps({"code": "idea_error", "message": "cannot read back"}),
                        )
                    ],
                    is_error=True,
                )
            if tool == "idea_native_set_loads":
                Path(str(args["out_path"])).write_text(json.dumps({"loads": args["loads"]}), encoding="utf-8")
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=json.dumps({"effects_written": 1}))],
                    is_error=False,
                )
            raise AssertionError((tool, args, effect))

    async def readback_fail() -> None:
        await loads.set_loads(
            sessions=_ReadbackFail(),
            server="idea",
            role="main",
            plan=_set_loads_plan(store, model),
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
            run_dir=run_dir,
            readback_relative_tolerance_ratio=1e-9,
            approved=True,
            ids=None,
        )

    with pytest.raises(ContractError) as rb:
        anyio.run(readback_fail)
    assert rb.value.detail.host_method == "idea_native_get_loads"


def test_exact_messages_for_builder_refusals(store: ResultStore) -> None:
    """AC8/AC9: exact ContractError messages for duplicate names, missing effect, missing segments."""
    from eng_harness.adapters.idea import _loads as loads

    rid = _put_member_end(store, _row())
    dup = loads.LoadPlan.model_validate(
        {
            "path": "/run/model.ideaCon",
            "connection": "CON1",
            "member_map": {"B1": [{"beam_segment_id": 1, "position_host": 0.0}]},
            "effects": [
                {
                    "name": "LE1",
                    "entries": [{"beam_segment_id": 1, "position_host": 0.0, "row": {"$ref": f"{rid}#/rows/0"}}],
                },
                {
                    "name": "LE1",
                    "entries": [{"beam_segment_id": 1, "position_host": 0.0, "row": {"$ref": f"{rid}#/rows/0"}}],
                },
            ],
        }
    )
    with pytest.raises(ContractError) as caught:
        loads.build_loading(
            current=_host_loading(),
            plan=dup,
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
        )
    assert caught.value.detail.message == "effect name 'LE1' appears more than once"

    with pytest.raises(ContractError) as missing_effect:
        loads.build_loading(
            current=[{"id": 1, "name": "OTHER", "forcesOnSegments": [], "forcesPercentageOnSegments": []}],
            plan=_plan(store),
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
        )
    assert missing_effect.value.detail.message == "effect 'LE1' is not in the host loading"

    with pytest.raises(ContractError) as missing_segs:
        loads.build_loading(
            current=[{"id": 1, "name": "LE1", "forcesPercentageOnSegments": []}],
            plan=_plan(store),
            load_map=loads.load_map_file(_SYNTHETIC_MAP),
            source=store,
            current_revision=lambda _: 1,
        )
    assert missing_segs.value.detail.message == "effect 'LE1' has no forcesOnSegments"


def test_raise_host_passes_tool_effect_and_json_mode() -> None:
    """AC10: _raise_host dumps with by_alias/mode=json and keeps tool/effect on the mapped error."""
    import json

    from mcp import types

    from eng_harness.adapters.idea import _loads as loads
    from eng_harness.servers import CallEffect

    result = types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text=json.dumps({"code": "idea_error", "message": "boom", "data": None}),
            )
        ],
        is_error=True,
    )
    with pytest.raises(ContractError) as caught:
        loads._raise_host(result, tool="idea_native_set_loads", effect=CallEffect.WRITE, ids=None)
    assert caught.value.detail.code is ErrorCode.HOST_ERROR
    assert caught.value.detail.host_method == "idea_native_set_loads"
    assert caught.value.detail.retryable is False
