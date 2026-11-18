"""Steps 6 to 10 of the edit cycle against the synthetic CSI fake (plan 0007 T8; spec 0007 AC10, AC11, AC17).

The change sets and the model are synthetic. Expected model values are derived by hand in each test from the items.
"""

import copy
import json
from collections.abc import Callable
from typing import Any, cast

from pydantic import JsonValue

from eng_harness.engine import RunStatus
from eng_harness.ports import ApprovalRequest, InputRequest

from .conftest import ITEM_AREA, ITEM_LOAD, ITEM_SECTION, LOADS, Stand

THREE: dict[str, JsonValue] = {"change_set": {"items": [ITEM_SECTION, ITEM_LOAD, ITEM_AREA]}}
AREA_LOADS = "Area Load Assignments - Uniform"
SECTIONS = "Area Assignments - Section Properties"
EPHEMERAL = ("model_path", "units", "locked")


def _responder(
    *, rejected: tuple[str, ...] = (), decision: str = "approve", option: str = "continue"
) -> Callable[[Stand, Any], Any]:
    def respond(stand: Stand, shown: Any) -> Any:
        if isinstance(shown, ApprovalRequest):
            return stand.approve(shown, rejected=rejected, decision=decision)
        assert isinstance(shown, InputRequest)
        return stand.give(shown, THREE) if shown.kind == "block" else stand.choose(shown, option)

    return respond


def _seeded(stand: Stand) -> dict[str, Any]:
    """The model the control file seeds, with the fake's defaults: what the fake holds before the first edit."""
    seed: dict[str, Any] = json.loads(stand.control.read_text())["seed"]
    model: dict[str, Any] = {c: [] for c in (
        "stories", "grids", "points", "frames", "areas", "materials", "frame_sections", "area_sections",
        "load_patterns", "load_cases", "load_combos")}  # fmt: skip
    model.update(seed)
    model.setdefault("tables", {})
    return copy.deepcopy(model)


def _row(model: dict[str, Any], table: str, key: str, name: str) -> dict[str, Any]:
    (row,) = [r for r in model["tables"][table] if r[key] == name]
    found: dict[str, Any] = row
    return found


def _written(stand: Stand) -> list[str]:
    return [
        c["tool"] for c in stand.calls() if c["tool"].startswith(("csi_assign", "csi_set", "csi_define", "csi_add"))
    ]


def test_model_holds_exactly_the_changes(stand: Stand) -> None:
    """AC10: read-back PASS, the report from the step 3 read to the step 9 read holds exactly the expected effects,
    and the fake's final model is the baseline plus the three items (by hand: F1 section C40, A1 section SL20, the
    F1 DEAD load 20 kN/m, which the fake stores unchanged in its resting units kN and m)."""
    expected = _seeded(stand)
    outcome = stand.play(stand.flow(), _responder())
    assert outcome.status is RunStatus.COMPLETED, outcome
    expected["frames"][0]["section"] = "C40"
    expected["areas"][0]["section"] = "SL20"
    _row(expected, LOADS, "Frame", "F1")["Value"] = 20.0
    expected["tables"][SECTIONS] = [{"UniqueName": "A1", "Section": "SL20"}]
    final = stand.model()
    for key in EPHEMERAL:
        final.pop(key, None)
        expected.pop(key, None)
    assert final == expected
    (readback,) = stand.results("harness.readback_check")
    assert readback["status"] == "PASS"
    assert {row["result"] for row in readback["items"]} == {"match"}
    assert readback["unexpected"] == []
    (effects,) = stand.results("harness.expected_effects")
    keys = {(e["section"], tuple(e["key"])) for e in effects["effects"]}
    assert {(c["section"], tuple(c["key"])) for c in readback["diff"]["changes"]} == keys


def test_rejected_items_not_written(stand: Stand) -> None:
    """AC11: a rejected item is not written and is not an expected effect, so the read-back still passes."""
    outcome = stand.play(stand.flow(), _responder(rejected=("a2",)))
    assert outcome.status is RunStatus.COMPLETED, outcome
    written = _written(stand)
    assert "csi_set_frame_load_distributed" not in written
    assert written.count("csi_assign_frame_section") == written.count("csi_assign_area_section") == 1
    assert _row(stand.model(), LOADS, "Frame", "F1")["Value"] == _row(_seeded(stand), LOADS, "Frame", "F1")["Value"]
    (effects,) = stand.results("harness.expected_effects")
    assert {e["item_id"].partition("/")[0] for e in effects["effects"]} == {"a1", "a3"}
    assert stand.results("harness.readback_check")[0]["status"] == "PASS"


def test_rejected_set_writes_nothing(stand: Stand) -> None:
    """AC11: a rejection of the whole set runs no write at all and ends the cycle as `rejected`."""
    outcome = stand.play(stand.flow(), _responder(decision="reject"))
    assert outcome.status is RunStatus.COMPLETED, outcome
    assert outcome.output is not None
    assert [c.route for c in cast(Any, outcome.output).cycles] == ["rejected"]
    assert _written(stand) == []
    assert "csi_save_model" not in [c["tool"] for c in stand.calls()]
    assert stand.results("harness.expected_effects") == []


def test_readback_failure_routes(stand: Stand) -> None:
    """AC17: a read-back `FAIL` (the fake changes an area load that no item touches, so it is `unexpected`) opens D-2,
    `restore_previous` reopens this cycle's snapshot (the `saved_file` of its step 7) and the cycle starts again at
    step 3; analysis does not run."""
    changed: list[bool] = []

    def hook(ports: Any) -> None:
        call = ports.tool_port.call

        async def after(tool: str, *args: Any, **kwargs: Any) -> Any:
            result = await call(tool, *args, **kwargs)
            if tool == "csi_set_frame_load_distributed" and not changed:
                changed.append(True)
                stand.hand_edit(lambda m: _row(m, AREA_LOADS, "UniqueName", "A1").update(Value=99.0))
            return result

        ports.tool_port.call = after

    outcome = stand.play(stand.flow(), _responder(option="restore_previous"), cycles_hook=hook)
    assert outcome.status is RunStatus.COMPLETED, outcome
    decisions = [r for r in stand.inputs.presented if r.kind == "engine.decision"]
    assert decisions
    first, *_ = stand.results("harness.readback_check")
    assert first["status"] == "FAIL"
    assert first["unexpected"]  # the area load that the fake changed and no effect explains
    saved = [s for s in stand.steps("tool") if s.name == "csi_save_model" and (s.args or {}).get("as_new_revision")]
    revisions = [e.payload for e in stand.events() if getattr(e.payload, "role", None) == "revision"]
    assert saved
    assert revisions
    restored = [s for s in stand.steps("tool") if s.name == "csi_open_revision"]
    assert len(restored) == 1
    assert (restored[0].args or {})["revision"].startswith("original.rev")
    assert "csi_run_analysis" not in [c["tool"] for c in stand.calls()]
