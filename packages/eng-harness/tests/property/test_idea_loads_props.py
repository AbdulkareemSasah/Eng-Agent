"""Property: IDEA loading builder preserves structure (plan 0014 T7; spec 0014 AC9)."""

from __future__ import annotations

import copy
import tempfile
import uuid
from pathlib import Path
from typing import Any, cast

from eng_contract.envelope import HostInfo, Provenance
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import JsonValue

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "idea"
_SYNTHETIC_MAP = _FIXTURES / "load_map_synthetic.toml"
_START = 1_767_225_600_000
_MODEL = "mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV"

_finite = st.floats(min_value=-1e5, max_value=1e5, allow_nan=False, allow_infinity=False)
_force_keys = ("n", "qy", "qz", "mx", "my", "mz")


def _store() -> ResultStore:
    from eng_harness._kinds import HARNESS_KINDS

    root = Path(tempfile.mkdtemp(prefix=f"idea-loads-props-{uuid.uuid4().hex}-"))
    workspace = Workspace(root=root, classification=LocationClass.LOCAL)
    clock = FixedClock(_START, 1)
    return ResultStore(workspace, HARNESS_KINDS, SeededIdSource(b"idea-loads-props", clock), clock)


def _put_row(store: ResultStore, values: dict[str, float]) -> str:
    payload = cast(
        dict[str, JsonValue],
        {
            "sign_convention": "host_local/1",
            "rows": [
                {
                    "member": "B1",
                    "case": {"case": "DEAD", "case_type": "load_case"},
                    "end": "i",
                    "station_mm": 0.0,
                    "P_kN": values["n"],
                    "V2_kN": values["qy"],
                    "V3_kN": values["qz"],
                    "T_kNm": values["mx"],
                    "M2_kNm": values["my"],
                    "M3_kNm": values["mz"],
                }
            ],
        },
    )
    prov = Provenance(
        tool="harness",
        tool_version="1",
        host=HostInfo(program="ETABS", version="22", model_id=_MODEL, model_revision=1),
        inputs={},
        started_at="2026-01-01T00:00:00.000Z",
        duration_ms=0,
    )
    return store.put("forces.member_end/1", payload, prov).result_id


@settings(derandomize=True, max_examples=80, deadline=None)
@given(
    n=_finite,
    qy=_finite,
    qz=_finite,
    mx=_finite,
    my=_finite,
    mz=_finite,
    other_n=_finite,
)
def test_structure_preserved(n: float, qy: float, qz: float, mx: float, my: float, mz: float, other_n: float) -> None:
    """AC9: non-force fields and unmapped segments are byte-equal to the read loading after the build."""
    from eng_harness.adapters.idea import _loads as loads

    store = _store()
    rid = _put_row(store, {"n": n, "qy": qy, "qz": qz, "mx": mx, "my": my, "mz": mz})
    current: list[dict[str, Any]] = [
        {
            "id": 7,
            "name": "LE1",
            "checkEquilibrium": True,
            "percentageLoad": False,
            "extra_host_field": "keep-me",
            "forcesOnSegments": [
                {
                    "beamSegmentId": 1,
                    "position": 0.0,
                    "n": 1.0,
                    "qy": 2.0,
                    "qz": 3.0,
                    "mx": 4.0,
                    "my": 5.0,
                    "mz": 6.0,
                    "host_meta": "segment-meta",
                },
                {
                    "beamSegmentId": 2,
                    "position": 0.5,
                    "n": other_n,
                    "qy": 0.0,
                    "qz": 0.0,
                    "mx": 0.0,
                    "my": 0.0,
                    "mz": 0.0,
                },
            ],
            "forcesPercentageOnSegments": [],
        }
    ]
    before = copy.deepcopy(current)
    plan = loads.LoadPlan.model_validate(
        {
            "path": "/run/m.ideaCon",
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
        }
    )
    built, _ = loads.build_loading(
        current=current,
        plan=plan,
        load_map=loads.load_map_file(_SYNTHETIC_MAP),
        source=store,
        current_revision=lambda _: 1,
    )
    assert built[0]["id"] == before[0]["id"]
    assert built[0]["name"] == before[0]["name"]
    assert built[0]["checkEquilibrium"] == before[0]["checkEquilibrium"]
    assert built[0]["extra_host_field"] == before[0]["extra_host_field"]
    assert built[0]["forcesOnSegments"][1] == before[0]["forcesOnSegments"][1]
    mapped = built[0]["forcesOnSegments"][0]
    original = before[0]["forcesOnSegments"][0]
    assert mapped["beamSegmentId"] == original["beamSegmentId"]
    assert mapped["position"] == original["position"]
    assert mapped["host_meta"] == original["host_meta"]
    for key in _force_keys:
        assert key in mapped
