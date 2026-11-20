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
