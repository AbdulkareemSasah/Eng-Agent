"""SAFE adapter gaps (plan 0008 T3; spec 0008 AC8, section 4.8)."""

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
            # Lambdas keep the zero-arg call site typed after new_model gained product= (plan 0012 T3 / B-247).
            for refuse in (lambda: new_model(), lambda: refuse_step("new_model")):
                with pytest.raises(NotImplementedGap) as caught:
                    refuse()
                assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
                assert caught.value.evidence == ("SG-1",)
                assert "SG-1" in caught.value.message or "prepared" in caught.value.message
            assert manager.session_epoch("csi_safe") == 0

    anyio.run(body)
    assert _calls(control) == []


@pytest.mark.parametrize("gap_id", [f"SG-{n}" for n in range(1, 10)])
def test_safe_gap_registry_complete(gap_id: str) -> None:
    """Amendment B-418: _gaps.py holds SG-1 to SG-9 ids and messages, wiring only SG-1 to a step."""
    from eng_harness.adapters.csi._gaps import SAFE_GAPS, STEP_GAPS, raise_gap, refuse_step

    assert SAFE_GAPS[gap_id]
    with pytest.raises(NotImplementedGap) as caught:
        raise_gap(gap_id)
    assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
    assert caught.value.evidence == (gap_id,)
    assert caught.value.message == SAFE_GAPS[gap_id]
    assert set(STEP_GAPS) == {"new_model"}
    with pytest.raises(KeyError):
        refuse_step("slab_design")
    with pytest.raises(KeyError):
        raise_gap("SG-99")
