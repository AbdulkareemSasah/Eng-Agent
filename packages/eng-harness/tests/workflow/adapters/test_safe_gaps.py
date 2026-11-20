"""SAFE adapter gaps (plan 0008 T3, T7; spec 0008 AC8, AC24, AC25, section 4.8)."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio
import pytest

from eng_harness.adapters.csi import csi_allowlist
from eng_harness.errors import HarnessCode, NotImplementedGap
from eng_harness.servers import ServerManager, ServersConfig

ConfigFactory = Callable[..., ServersConfig]

# Step names wired in T7 (amendment B-418); SG-8 is raised from the load import (T6), not a STEP_GAPS entry.
_AC25_CASES = (
    ("SG-2", "define_slab_section"),
    ("SG-3", "define_area_spring"),
    ("SG-4", "resize_area"),
    ("SG-8", None),
    ("SG-9", "area_forces"),
)


def _calls(control: Path) -> list[dict[str, Any]]:
    data = json.loads(control.read_text())
    calls = data.get("calls", [])
    assert isinstance(calls, list)
    return calls


def test_new_model_gap(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC8: a new SAFE model step raises NotImplementedGap (SG-1), sends no call, and new-model tools are unserved."""
    from eng_harness.adapters.csi._gaps import new_model, refuse_step

    control.write_text(json.dumps({"faults": [], "seed": {}, "product": "SAFE"}))
    base = make_config()
    safe_section = base.servers["csi"].model_copy(update={"product": "SAFE", "host_key": "csi_safe"})
    config = ServersConfig(servers={"csi_safe": safe_section})
    safe_allowlist = csi_allowlist().for_product("SAFE")

    for excluded in ("csi_new_model", "csi_new_blank_model"):
        assert excluded not in safe_allowlist.tool_names
        with pytest.raises(KeyError, match=excluded):
            safe_allowlist.descriptor(excluded)

    async def body() -> None:
        async with ServerManager(
            config, tmp_path / "run", check={"csi_safe": safe_allowlist.build_expectation()}
        ) as manager:
            # Direct calls stay typed after new_model gained product= (plan 0012 T3 / B-247).
            with pytest.raises(NotImplementedGap) as from_new:
                new_model()
            with pytest.raises(NotImplementedGap) as from_step:
                refuse_step("new_model")
            for caught in (from_new, from_step):
                assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
                assert caught.value.evidence == ("SG-1",)
                assert "SG-1" in caught.value.message or "prepared" in caught.value.message
            assert manager.session_epoch("csi_safe") == 0

    anyio.run(body)
    assert _calls(control) == []


@pytest.mark.parametrize("gap_id", [f"SG-{n}" for n in range(1, 10)])
def test_safe_gap_registry_complete(gap_id: str) -> None:
    """Amendment B-418: _gaps.py holds SG-1 to SG-9 ids and messages; T7 wires SG-2 to SG-5 and SG-9."""
    from eng_harness.adapters.csi._gaps import SAFE_GAPS, STEP_GAPS, raise_gap

    assert SAFE_GAPS[gap_id]
    with pytest.raises(NotImplementedGap) as caught:
        raise_gap(gap_id)
    assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
    assert caught.value.evidence == (gap_id,)
    assert caught.value.message == SAFE_GAPS[gap_id]
    assert set(STEP_GAPS) == {
        "new_model",
        "define_slab_section",
        "define_area_spring",
        "resize_area",
        "slab_design",
        "design_results",
        "area_forces",
    }
    with pytest.raises(KeyError):
        raise_gap("SG-99")


def test_slab_design_gap(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC24: SAFE slab design run or design results raise NotImplementedGap SG-5; nothing is sent."""
    from eng_harness.adapters.csi._gaps import refuse_step, slab_design

    control.write_text(json.dumps({"faults": [], "seed": {}, "product": "SAFE"}))
    base = make_config()
    safe_section = base.servers["csi"].model_copy(update={"product": "SAFE", "host_key": "csi_safe"})
    config = ServersConfig(servers={"csi_safe": safe_section})
    safe_allowlist = csi_allowlist().for_product("SAFE")
    for excluded in ("csi_design_run", "csi_design_results"):
        assert excluded not in safe_allowlist.tool_names

    async def body() -> None:
        async with ServerManager(
            config, tmp_path / "run", check={"csi_safe": safe_allowlist.build_expectation()}
        ) as manager:
            for call in (slab_design, lambda: refuse_step("slab_design"), lambda: refuse_step("design_results")):
                with pytest.raises(NotImplementedGap) as caught:
                    call()
                assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
                assert caught.value.evidence == ("SG-5",)
            assert manager.session_epoch("csi_safe") == 0

    anyio.run(body)
    assert _calls(control) == []


@pytest.mark.parametrize(("gap_id", "step"), _AC25_CASES)
def test_gaps_not_implemented(
    gap_id: str, step: str | None, tmp_path: Path, make_config: ConfigFactory, control: Path
) -> None:
    """AC25: each remaining gap raises NotImplementedGap with its id and sends nothing."""
    from eng_harness.adapters.csi._gaps import raise_gap, refuse_step

    control.write_text(json.dumps({"faults": [], "seed": {}, "product": "SAFE"}))
    base = make_config()
    safe_section = base.servers["csi"].model_copy(update={"product": "SAFE", "host_key": "csi_safe"})
    config = ServersConfig(servers={"csi_safe": safe_section})
    safe_allowlist = csi_allowlist().for_product("SAFE")

    async def body() -> None:
        async with ServerManager(
            config, tmp_path / "run", check={"csi_safe": safe_allowlist.build_expectation()}
        ) as manager:
            if step is None:
                with pytest.raises(NotImplementedGap) as caught:
                    raise_gap(gap_id)
            else:
                with pytest.raises(NotImplementedGap) as caught:
                    refuse_step(step)
            assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
            assert caught.value.evidence == (gap_id,)
            assert manager.session_epoch("csi_safe") == 0

    anyio.run(body)
    assert _calls(control) == []
