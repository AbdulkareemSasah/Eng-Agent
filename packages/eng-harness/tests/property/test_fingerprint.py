"""Fingerprint properties (plan 0003 T7; spec 0003 AC19, AC20): order independence and change sensitivity."""

import copy
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from eng_harness.calc import InputMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.model_fingerprint import FingerprintBody, FingerprintInput

KINDS = {
    "frames": "model.frame_placements/1",
    "materials": "model.materials/1",
    "loads": "model.load_set/1",
    "restraints": "model.joint_restraints/1",
}
_coord = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False).map(lambda v: v + 0.0)
_names = st.lists(st.text("ABCDEFGHJ0123456789é", min_size=1, max_size=4), min_size=1, max_size=5, unique=True)


def _frame(name: str, z: float) -> dict[str, Any]:
    return {
        "id": name,
        "kind": "beam",
        "section": "S1",
        "i": {"x_mm": 0.0, "y_mm": 0.0, "z_mm": z},
        "j": {"x_mm": 1.0, "y_mm": 0.0, "z_mm": z},
        "rotation_deg": 0.0,
    }


@st.composite
def read_sets(draw: st.DrawFn) -> dict[str, Any]:
    """A synthetic read set of frames, materials, loads and restraints (no project value)."""
    names = draw(_names)
    return {
        "frames": {"frames": [_frame(n, draw(_coord)) for n in names]},
        "materials": {
            "materials": [
                {"name": n, "type": "other", "E_MPa": 1.0, "nu_ratio": 0.0, "gamma_kN_m3": 0.0} for n in draw(_names)
            ]
        },
        "loads": {
            "patterns": [{"name": "P", "type": "dead", "self_weight_ratio": 0.0}],
            "combinations": [
                {
                    "name": "C",
                    "type": "linear_add",
                    "items": [
                        {"case": {"case": "P", "case_type": "load_pattern"}, "scale_ratio": s}
                        for s in draw(st.lists(_coord, min_size=1, max_size=4))
                    ],
                }
            ],
            "frame_loads": [
                {"frame": n, "pattern": "P", "direction": "gravity", "w_kN_m": draw(_coord)} for n in names
            ],
            "area_loads": [],
        },
        "restraints": {
            "joints": [
                {"joint": n, "ux": True, "uy": draw(st.booleans()), "uz": True, "rx": False, "ry": False, "rz": False}
                for n in draw(_names)
            ]
        },
    }


def _fingerprint(fields: dict[str, Any]) -> str:
    meta = InputMeta.model_validate(
        {
            "refs": {
                name: {
                    "result_id": "res_00000000000000000000000001",
                    "kind": KINDS[name],
                    "complete": True,
                    "model_id": "mdl_00000000000000000000000000",
                    "model_revision": 1,
                    "parents": [],
                    "producer_tool": "csi",
                }
                for name in fields
            }
        }
    )
    body = REGISTRY["harness.model_fingerprint"](FingerprintInput.model_validate(fields), meta, TraceBuilder())
    assert isinstance(body, FingerprintBody)
    return body.fingerprint


def _shuffled(data: st.DataObject, rows: list[Any]) -> list[Any]:
    return list(data.draw(st.permutations(rows)))


@settings(derandomize=True, max_examples=60, deadline=None)
@given(read_sets(), st.data())
def test_order_independent(fields: dict[str, Any], data: st.DataObject) -> None:
    mixed = copy.deepcopy(fields)
    mixed["frames"]["frames"] = _shuffled(data, mixed["frames"]["frames"])
    mixed["materials"]["materials"] = _shuffled(data, mixed["materials"]["materials"])
    mixed["restraints"]["joints"] = _shuffled(data, mixed["restraints"]["joints"])
    loads = mixed["loads"]
    loads["frame_loads"] = _shuffled(data, loads["frame_loads"])
    loads["combinations"][0]["items"] = _shuffled(data, loads["combinations"][0]["items"])
    order = data.draw(st.permutations(list(mixed)))
    assert _fingerprint({k: mixed[k] for k in order}) == _fingerprint(fields)


MUTATIONS = ("coordinate", "section", "restraint", "load", "add", "remove", "drop")


@settings(derandomize=True, max_examples=80, deadline=None)
@given(read_sets(), st.sampled_from(MUTATIONS), st.data())
def test_any_change_changes_fingerprint(fields: dict[str, Any], mutation: str, data: st.DataObject) -> None:
    changed = copy.deepcopy(fields)
    frames = changed["frames"]["frames"]
    if mutation == "coordinate":
        point = frames[data.draw(st.integers(0, len(frames) - 1))]["i"]
        point["z_mm"] = data.draw(_coord.filter(lambda v: v != point["z_mm"]))
    elif mutation == "section":
        frames[0]["section"] = "S2"
    elif mutation == "restraint":
        joint = changed["restraints"]["joints"][0]
        joint["uy"] = not joint["uy"]
    elif mutation == "load":
        row = changed["loads"]["frame_loads"][0]
        row["w_kN_m"] = data.draw(_coord.filter(lambda v: v != row["w_kN_m"]))
    elif mutation == "add":
        frames.append(_frame("new", 0.0))
    elif mutation == "remove":
        changed["restraints"]["joints"].pop()
    else:
        del changed[data.draw(st.sampled_from(sorted(changed)))]
    assert _fingerprint(changed) != _fingerprint(fields)
