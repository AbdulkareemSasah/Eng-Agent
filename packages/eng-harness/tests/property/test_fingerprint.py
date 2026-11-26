"""Fingerprint properties (plan 0003 T7, plan 0002 T11b; spec 0003 AC19, AC20; spec 0002 AC27, section 4.6.4).

The calc fingerprint tests come first; the CSI adapter's fingerprint over the host reads follows.
"""

import copy
from typing import Any

from hypothesis import assume, given, settings
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
                    "ref": "res_00000000000000000000000001",
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


HOST_KINDS = (
    "model.stories/1",
    "model.grid_system/1",
    "model.frame_placements/1",
    "model.area_placements/1",
    "model.load_set/1",
    "model.joint_restraints/1",
)
_label = st.text("ABCDEFGHJ0123456789", min_size=1, max_size=4)  # upper case: the added names below are lower case


@st.composite
def _host_row(draw: st.DrawFn) -> dict[str, Any]:
    """A synthetic host row: a name, a value, a coordinate list (order matters) and a list of named parts."""
    return {
        "name": draw(_label),
        "value": draw(_coord),
        "point": [draw(_coord) for _ in range(3)],
        "items": [{"name": n, "factor": draw(_coord)} for n in draw(st.lists(_label, max_size=3, unique=True))],
    }


@st.composite
def host_reads(draw: st.DrawFn) -> tuple[dict[str, Any], dict[str, int]]:
    """The six host sections (each a list of rows) and the object counts of one synthetic read (no project value)."""
    rows = st.lists(_host_row(), min_size=1, max_size=4, unique_by=lambda row: row["name"])
    sections = {kind: {"rows": draw(rows)} for kind in HOST_KINDS}
    return sections, draw(st.dictionaries(_label, st.integers(0, 2000), min_size=1, max_size=4))


def _mixed(data: st.DataObject, value: Any) -> Any:
    """Every object's key order and every list of objects reordered; lists of numbers keep their order."""
    if isinstance(value, dict):
        return {k: _mixed(data, v) for k, v in data.draw(st.permutations(list(value.items())))}
    if isinstance(value, list):
        items = [_mixed(data, item) for item in value]
        if items and all(isinstance(item, dict) for item in items):
            return list(data.draw(st.permutations(items)))
        return items
    return value


HOST_EDITS = ("value", "name", "coordinate", "swap", "add_row", "drop_row", "add_item", "count", "empty")


@settings(derandomize=True, max_examples=100, deadline=None)
@given(host_reads(), st.sampled_from(HOST_EDITS), st.data())
def test_order_independent_and_edit_sensitive(
    read: tuple[dict[str, Any], dict[str, int]], edit: str, data: st.DataObject
) -> None:
    """The host fingerprint ignores the order of rows and keys and changes with any one edit of a row or a count."""
    from eng_harness.adapters.csi._state import fingerprint

    sections, counts = read
    base = fingerprint(sections, counts)
    assert len(base) == 64
    assert fingerprint(_mixed(data, sections), _mixed(data, counts)) == base

    changed, more = copy.deepcopy(sections), dict(counts)
    kind = data.draw(st.sampled_from(HOST_KINDS))
    rows = changed[kind]["rows"]
    row = rows[data.draw(st.integers(0, len(rows) - 1))]
    if edit == "value":
        row["value"] = data.draw(_coord.filter(lambda v: v != row["value"]))
    elif edit == "name":
        row["name"] += "x"
    elif edit == "coordinate":
        row["point"][data.draw(st.integers(0, 2))] += 1.0
    elif edit == "swap":
        first, second = data.draw(st.sampled_from([(0, 1), (0, 2), (1, 2)]))
        assume(row["point"][first] != row["point"][second])
        row["point"][first], row["point"][second] = row["point"][second], row["point"][first]
    elif edit == "add_row":
        rows.append({"name": "new", "value": 0.0, "point": [0.0, 0.0, 0.0], "items": []})
    elif edit == "drop_row":
        rows.remove(row)
    elif edit == "add_item":
        row["items"].append({"name": "extra", "factor": 1.0})
    elif edit == "count":
        more[data.draw(st.sampled_from(sorted(more)))] += 1
    else:
        changed[kind] = {"rows": []}
    assert fingerprint(changed, more) != base


SAFE_HOST_KINDS = (
    "model.grid_system/1",
    "harness.model_points/1",
    "model.frame_placements/1",
    "model.area_placements/1",
    "model.sections/1",
    "model.materials/1",
    "model.load_set/1",
    "harness.joint_loads/1",
    "harness.safe_soil_supports/1",
)
SAFE_EDITS = ("value", "name", "coordinate", "add_row", "drop_row", "count", "empty")


@st.composite
def safe_host_reads(draw: st.DrawFn) -> tuple[dict[str, Any], dict[str, int]]:
    """SAFE host sections (spec 0008 section 4.4) and object counts for one synthetic read."""
    rows = st.lists(_host_row(), min_size=1, max_size=4, unique_by=lambda row: row["name"])
    sections = {kind: {"rows": draw(rows)} for kind in SAFE_HOST_KINDS}
    return sections, draw(st.dictionaries(_label, st.integers(0, 2000), min_size=1, max_size=4))


@settings(derandomize=True, max_examples=100, deadline=None)
@given(safe_host_reads(), st.sampled_from(SAFE_EDITS), st.data())
def test_safe_order_independent_and_edit_sensitive(
    read: tuple[dict[str, Any], dict[str, int]], edit: str, data: st.DataObject
) -> None:
    """AC9: the SAFE fingerprint ignores row and key order and changes with each section 4.4 edit kind."""
    from eng_harness.adapters.csi.products._safe_state import fingerprint

    sections, counts = read
    base = fingerprint(sections, counts)
    assert len(base) == 64
    assert fingerprint(_mixed(data, sections), _mixed(data, counts)) == base

    changed, more = copy.deepcopy(sections), dict(counts)
    kind = data.draw(st.sampled_from(SAFE_HOST_KINDS))
    rows = changed[kind]["rows"]
    row = rows[data.draw(st.integers(0, len(rows) - 1))]
    if edit == "value":
        row["value"] = data.draw(_coord.filter(lambda v: v != row["value"]))
    elif edit == "name":
        row["name"] += "x"
    elif edit == "coordinate":
        row["point"][data.draw(st.integers(0, 2))] += 1.0
    elif edit == "add_row":
        rows.append({"name": "new", "value": 0.0, "point": [0.0, 0.0, 0.0], "items": []})
    elif edit == "drop_row":
        rows.remove(row)
    elif edit == "count":
        more[data.draw(st.sampled_from(sorted(more)))] += 1
    else:
        changed[kind] = {"rows": []}
    assert fingerprint(changed, more) != base


SAP2000_HOST_KINDS = (
    "model.frame_placements/1",
    "model.area_placements/1",
    "harness.model_points/1",
    "model.sections/1",
    "model.materials/1",
    "model.load_set/1",
)
SAP2000_EDITS = ("value", "name", "coordinate", "add_row", "drop_row", "count", "empty")


@st.composite
def sap2000_host_reads(draw: st.DrawFn) -> tuple[dict[str, Any], dict[str, int]]:
    """SAP2000 host sections (spec 0012 section 4.3) and object counts for one synthetic read."""
    rows = st.lists(_host_row(), min_size=1, max_size=4, unique_by=lambda row: row["name"])
    sections = {kind: {"rows": draw(rows)} for kind in SAP2000_HOST_KINDS}
    return sections, draw(st.dictionaries(_label, st.integers(0, 2000), min_size=1, max_size=4))


@settings(derandomize=True, max_examples=100, deadline=None)
@given(sap2000_host_reads(), st.sampled_from(SAP2000_EDITS), st.data())
def test_sap2000_order_independent_and_edit_sensitive(
    read: tuple[dict[str, Any], dict[str, int]], edit: str, data: st.DataObject
) -> None:
    """AC7: the SAP2000 fingerprint ignores row and key order and changes with each section 4.3 edit kind."""
    from eng_harness.adapters.csi.products._sap2000_state import fingerprint

    sections, counts = read
    base = fingerprint(sections, counts)
    assert len(base) == 64
    assert fingerprint(_mixed(data, sections), _mixed(data, counts)) == base

    changed, more = copy.deepcopy(sections), dict(counts)
    kind = data.draw(st.sampled_from(SAP2000_HOST_KINDS))
    rows = changed[kind]["rows"]
    row = rows[data.draw(st.integers(0, len(rows) - 1))]
    if edit == "value":
        row["value"] = data.draw(_coord.filter(lambda v: v != row["value"]))
    elif edit == "name":
        row["name"] += "x"
    elif edit == "coordinate":
        row["point"][data.draw(st.integers(0, 2))] += 1.0
    elif edit == "add_row":
        rows.append({"name": "new", "value": 0.0, "point": [0.0, 0.0, 0.0], "items": []})
    elif edit == "drop_row":
        rows.remove(row)
    elif edit == "count":
        more[data.draw(st.sampled_from(sorted(more)))] += 1
    else:
        changed[kind] = {"rows": []}
    assert fingerprint(changed, more) != base
