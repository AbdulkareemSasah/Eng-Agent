"""SAP2000 adapter gaps (plan 0012 T3; spec 0012 AC6, AC17, section 4.5)."""

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

# Spec 0012 AC17: remaining gaps of §4.5 other than SP-1 (AC6) and the later-wired SP-3, SP-4, SP-6.
_REMAINING = ("SP-2", "SP-5", "SP-7", "SP-8")


def _calls(control: Path) -> list[dict[str, Any]]:
    data = json.loads(control.read_text())
    calls = data.get("calls", [])
    assert isinstance(calls, list)
    return calls


def test_new_model_gap(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC6: a new SAP2000 model step raises NotImplementedGap (SP-1), sends no call, and new-model tools are unserved."""
    from eng_harness.adapters.csi._gaps import new_model, refuse_step

    control.write_text(json.dumps({"faults": [], "seed": {}, "product": "SAP2000"}))
    base = make_config()
    section = base.servers["csi"].model_copy(update={"product": "SAP2000", "host_key": "csi_sap2000"})
    config = ServersConfig(servers={"csi_sap2000": section})
    allowlist = csi_allowlist().for_product("SAP2000")

    for excluded in ("csi_new_model", "csi_new_blank_model"):
        assert excluded not in allowlist.tool_names
        with pytest.raises(KeyError, match=excluded):
            allowlist.descriptor(excluded)

    async def body() -> None:
        async with ServerManager(
            config, tmp_path / "run", check={"csi_sap2000": allowlist.build_expectation()}
        ) as manager:
            for call in (lambda: new_model(product="SAP2000"), lambda: refuse_step("new_model", product="SAP2000")):
                with pytest.raises(NotImplementedGap) as caught:
                    call()
                assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
                assert caught.value.evidence == ("SP-1",)
                assert "SP-1" in caught.value.message or "prepared" in caught.value.message
            assert manager.session_epoch("csi_sap2000") == 0

    anyio.run(body)
    assert _calls(control) == []


@pytest.mark.parametrize("gap_id", list(_REMAINING))
def test_gaps_not_implemented(gap_id: str) -> None:
    """AC17: each remaining gap of §4.5 raises NotImplementedGap with its id and nothing is sent."""
    from eng_harness.adapters.csi._gaps import SAP2000_GAPS, raise_gap

    assert SAP2000_GAPS[gap_id]
    with pytest.raises(NotImplementedGap) as caught:
        raise_gap(gap_id)
    assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
    assert caught.value.evidence == (gap_id,)
    assert caught.value.message == SAP2000_GAPS[gap_id]
