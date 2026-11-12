"""CSI model fingerprint stability (plan 0002 T11; spec 0002 AC27, section 4.6.4)."""

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from eng_harness.adapters.csi._state import fingerprint_host, sort_lists

_SECTIONS = (
    "model.stories/1",
    "model.grid_system/1",
    "model.frame_placements/1",
    "model.area_placements/1",
    "model.load_set/1",
    "model.joint_restraints/1",
)


def _sample(name: str) -> dict[str, object]:
    if name == "model.stories/1":
        return {"base_elevation": 0.0, "stories": [{"name": "S1", "elevation": 0.0, "height": 3.0}]}
    if name == "model.grid_system/1":
        return {"systems": [{"name": "G1", "x_lines": [{"id": "1", "ordinate": 0.0}]}]}
    if name == "model.frame_placements/1":
        return {"frames": [{"id": "F1", "point1": [0, 0, 0], "point2": [0, 0, 3]}]}
    if name == "model.area_placements/1":
        return {"areas": [{"id": "A1", "points": [[0, 0, 0], [1, 0, 0], [0, 1, 0]]}]}
    if name == "model.load_set/1":
        return {"patterns": [{"name": "DEAD"}], "combinations": [], "frame_loads": [], "area_loads": []}
    return {"joints": [{"joint": "P1", "ux": True, "uy": True, "uz": True, "rx": False, "ry": False, "rz": False}]}


def _base() -> tuple[dict[str, dict[str, object]], dict[str, int]]:
    return ({key: sort_lists(_sample(key)) for key in _SECTIONS}, {"points": 2, "frames": 1})


@settings(derandomize=True, max_examples=80)
@given(st.data())
def test_order_independent_and_edit_sensitive(data: st.DataObject) -> None:
    """The fingerprint ignores list order and changes when any section's content changes."""
    base, counts = _base()
    first = fingerprint_host(base, counts)
    assert len(first) == 64
    shuffled: dict[str, dict[str, object]] = {}
    for key, body in base.items():
        changed = dict(body)
        for field, rows in changed.items():
            if isinstance(rows, list) and len(rows) > 1:
                changed[field] = data.draw(st.permutations(rows))
        shuffled[key] = changed
    assume(fingerprint_host(shuffled, counts) == first)
    edited = {
        **base,
        "model.frame_placements/1": sort_lists({"frames": [{"id": "F2", "point1": [1, 0, 0], "point2": [1, 0, 3]}]}),
    }
    assert fingerprint_host(edited, counts) != first
    assert fingerprint_host(base, {"points": 3, "frames": 1}) != first
