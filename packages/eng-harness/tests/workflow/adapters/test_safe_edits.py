"""SAFE pattern and combination edits (plan 0008 T6; spec 0008 AC20, section 4.4).

`superimposed_dead` maps to `SuperDead` on SAFE only; `roof_live` stays gap H-G3. Adapter imports sit inside the tests.
"""

from __future__ import annotations

from typing import Any

import pytest
from eng_contract.kinds.model import CombinationItem, CombinationType, PatternType
from pydantic import JsonValue

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._toolport import Binding
from eng_harness.errors import HarnessCode, NotImplementedGap


def _build(tool: str, model: Any, token: str | None = None) -> dict[str, JsonValue]:
    from eng_harness.adapters.csi import csi_allowlist
    from eng_harness.adapters.csi._tools import EDIT_BUILDERS

    binding = Binding(target=HostTarget(product="SAFE", pid=4242), units_system=token)
    return EDIT_BUILDERS[tool](model, csi_allowlist().for_product("SAFE").descriptor(tool), binding)


def _item(case: str, kind: str, scale: float) -> CombinationItem:
    return CombinationItem.model_validate({"case": {"case": case, "case_type": kind}, "scale_ratio": scale})


def test_patterns_and_combos() -> None:
    """AC20: 0002 §4.6.2 mapping holds on SAFE; superimposed_dead → SuperDead; roof_live is H-G3."""
    from eng_harness.adapters.csi import _edits as e
    from eng_harness.adapters.csi.products import _safe_loads as loads

    mapped = {"dead": "Dead", "live": "Live", "seismic": "Quake", "wind": "Wind", "snow": "Snow", "other": "Other"}
    for kind, name in mapped.items():
        pattern = e.AddLoadPatternArgs(model="m", name="P", type=PatternType(kind), self_weight_ratio=1.0)
        assert _build("csi_add_load_pattern", pattern) == {"name": "P", "type": name, "self_weight": 1.0}

    super_dead = e.AddLoadPatternArgs(
        model="m", name="SDL", type=PatternType.SUPERIMPOSED_DEAD, self_weight_ratio=0.0
    )
    assert _build("csi_add_load_pattern", super_dead) == {"name": "SDL", "type": "SuperDead", "self_weight": 0.0}
    assert loads.SAFE_PATTERN[PatternType.SUPERIMPOSED_DEAD] == "SuperDead"

    with pytest.raises(NotImplementedGap) as caught:
        _build(
            "csi_add_load_pattern",
            e.AddLoadPatternArgs(model="m", name="R", type=PatternType.ROOF_LIVE, self_weight_ratio=0.0),
        )
    assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
    assert caught.value.evidence == ("H-G3",)

    codes = {"linear_add": 0, "envelope": 1, "absolute_add": 2, "srss": 3}
    items = [_item("DEAD", "load_pattern", 1.4), _item("C1", "load_combination", 1.0)]
    for kind, code in codes.items():
        combo = e.AddLoadComboArgs(model="m", name="C2", type=CombinationType(kind), items=items)
        assert _build("csi_add_load_combo", combo) == {
            "name": "C2",
            "combo_type": code,
            "components": [
                {"name": "DEAD", "factor": 1.4, "kind": "case"},
                {"name": "C1", "factor": 1.0, "kind": "combo"},
            ],
        }
    assert _build("csi_delete_load_combo", e.DeleteLoadComboArgs(model="m", name="C2")) == {"name": "C2"}
