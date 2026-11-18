"""Behaviors of the synthetic Sasaah CSI fake server (spec 0002 section 4.8.3), run as a real process."""

import asyncio
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

SERVER = Path(__file__).resolve().parent / "server.py"


class Rpc:
    """Newline-delimited JSON-RPC over the fake's stdio, driven from a private event loop."""

    def __init__(self, control: Path) -> None:
        self.loop = asyncio.new_event_loop()
        env = {**os.environ, "SASAAH_CSI_FAKE_CONTROL": str(control)}
        self.proc = self.loop.run_until_complete(
            asyncio.create_subprocess_exec(
                sys.executable, str(SERVER), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, env=env
            )
        )
        self._id = 0
        self.request(
            "initialize",
            {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
        )
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def send(self, message: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write((json.dumps(message) + "\n").encode())
        self.loop.run_until_complete(self.proc.stdin.drain())

    def readline(self) -> str:
        assert self.proc.stdout is not None
        return self.loop.run_until_complete(asyncio.wait_for(self.proc.stdout.readline(), 30)).decode()

    def wait(self) -> int:
        return self.loop.run_until_complete(asyncio.wait_for(self.proc.wait(), 10))

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._id += 1
        self.send({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params})
        line = self.readline()
        assert line, "the fake closed its output"
        reply = json.loads(line)
        assert reply["id"] == self._id
        result = reply["result"]
        assert isinstance(result, dict)
        return result

    def call(self, tool: str, /, **arguments: Any) -> tuple[bool, dict[str, Any]]:
        result = self.request("tools/call", {"name": tool, "arguments": arguments})
        blocks = result["content"]
        assert len(blocks) == 1
        assert blocks[0]["type"] == "text"
        body = json.loads(blocks[0]["text"])
        return bool(result.get("isError")), body

    def close(self) -> None:
        assert self.proc.stdin is not None
        if not self.proc.stdin.is_closing():
            self.proc.stdin.close()
        self.wait()
        self.loop.close()


@pytest.fixture
def control(tmp_path: Path) -> Path:
    path = tmp_path / "control.json"
    path.write_text(json.dumps({"faults": [], "seed": {}}))
    return path


@pytest.fixture
def rpc(control: Path) -> Iterator[Rpc]:
    client = Rpc(control)
    yield client
    client.close()


def _fault(control: Path, fault: str, **extra: Any) -> None:
    data = json.loads(control.read_text())
    data.setdefault("faults", []).append({"fault": fault, **extra})
    control.write_text(json.dumps(data))


def _launch(rpc: Rpc) -> None:
    error, body = rpc.call("csi_launch", product="ETABS")
    assert not error
    assert body["launched"] is True


def test_tool_list_equals_schemas(rpc: Rpc) -> None:
    schemas = json.loads((SERVER.parent / "schemas.json").read_text())
    listed = rpc.request("tools/list", {})["tools"]
    assert {t["name"]: t["inputSchema"] for t in listed} == {t["name"]: t["input_schema"] for t in schemas["tools"]}


def test_no_target_error_shape(rpc: Rpc) -> None:
    error, body = rpc.call("csi_model_info")
    assert error
    assert body["code"] == "no_target"
    assert set(body) >= {"code", "message", "data"}


def test_confirmation_required(rpc: Rpc) -> None:
    _launch(rpc)
    error, body = rpc.call("csi_run_analysis")
    assert error
    assert body["code"] == "confirmation_required"


def test_units_set_and_restored_per_call(rpc: Rpc) -> None:
    _launch(rpc)
    error, body = rpc.call("csi_list_points", units="kN_mm_C")
    assert not error
    assert body["units"] == "kN_mm_C"
    assert rpc.call("csi_model_info")[1]["units"] == "kN_m_C"


def test_units_left_changed_fault(rpc: Rpc, control: Path) -> None:
    _launch(rpc)
    _fault(control, "units_left_changed")
    rpc.call("csi_list_points", units="kN_mm_C")
    assert rpc.call("csi_model_info")[1]["units"] == "kN_mm_C"


def test_model_locked_after_analysis_until_unlocked(rpc: Rpc) -> None:
    _launch(rpc)
    assert rpc.call("csi_model_info")[1]["locked"] is False
    assert not rpc.call("csi_run_analysis", confirm=True)[0]
    assert rpc.call("csi_model_info")[1]["locked"] is True
    error, body = rpc.call("csi_add_point", x=0, y=0, z=0, name="P1")
    assert error
    assert body["code"] == "model_locked"
    assert not rpc.call("csi_unlock_model", confirm=True)[0]
    assert not rpc.call("csi_add_point", x=0, y=0, z=0, name="P1")[0]


def test_writes_are_visible_to_reads(rpc: Rpc) -> None:
    _launch(rpc)
    assert not rpc.call("csi_add_point", x=1, y=2, z=3, name="P1")[0]
    body = rpc.call("csi_list_points")[1]
    assert [item["name"] for item in body["items"]] == ["P1"]
    assert body["truncated"] is False


def test_truncated_at_limit(rpc: Rpc) -> None:
    _launch(rpc)
    for index in range(3):
        rpc.call("csi_add_point", x=index, y=0, z=0, name=f"P{index}")
    body = rpc.call("csi_list_points", limit=2)[1]
    assert len(body["items"]) == 2
    assert body["truncated"] is True


def test_attach_is_not_launched_and_refuses_exit(rpc: Rpc) -> None:
    error, body = rpc.call("csi_attach", product="ETABS", pid=4242)
    assert not error
    assert body["launched"] is False
    error, body = rpc.call("csi_exit", confirm=True)
    assert error
    assert body["code"] == "not_launched_by_server"


def test_exit_acts_on_current_target(rpc: Rpc) -> None:
    _launch(rpc)
    status = rpc.call("csi_status")[1]
    error, body = rpc.call("csi_exit", confirm=True)
    assert not error
    assert body["pid"] == status["current_target"]["pid"]
    assert rpc.call("csi_status")[1]["current_target"] is None


def test_timeout_before_apply_invalidates_session(rpc: Rpc, control: Path) -> None:
    _launch(rpc)
    _fault(control, "timeout_before_apply", tool="csi_add_point")
    error, body = rpc.call("csi_add_point", x=0, y=0, z=0, name="P1")
    assert error
    assert body["code"] == "timeout"
    assert rpc.call("csi_list_points")[1]["items"] == []
    status = rpc.call("csi_status")[1]
    assert status["current_target"]["launched"] is False
    assert rpc.call("csi_exit", confirm=True)[1]["code"] == "not_launched_by_server"


def test_timeout_after_apply_applies(rpc: Rpc, control: Path) -> None:
    _launch(rpc)
    _fault(control, "timeout_after_apply", tool="csi_add_point")
    assert rpc.call("csi_add_point", x=0, y=0, z=0, name="P1")[1]["code"] == "timeout"
    assert [i["name"] for i in rpc.call("csi_list_points")[1]["items"]] == ["P1"]


def test_com_worker_recycled_fault(rpc: Rpc, control: Path) -> None:
    _launch(rpc)
    _fault(control, "com_worker_recycled")
    error, body = rpc.call("csi_add_point", x=0, y=0, z=0, name="P1")
    assert error
    assert body["code"] == "com_worker_recycled"
    assert rpc.call("csi_list_points")[1]["items"] == []


def test_crash_during_call(rpc: Rpc, control: Path) -> None:
    _launch(rpc)
    _fault(control, "crash_during_call")
    rpc.send(
        {"jsonrpc": "2.0", "id": 99, "method": "tools/call", "params": {"name": "csi_model_info", "arguments": {}}}
    )
    assert rpc.readline() == ""
    assert rpc.wait() != 0


def test_row_limit_truncates_table_read(control: Path) -> None:
    rows = [{"n": 1}, {"n": 2}, {"n": 3}]
    control.write_text(json.dumps({"faults": [], "seed": {"tables": {"Joint Reactions": rows}}}))
    client = Rpc(control)
    try:
        _launch(client)
        body = client.call("csi_db_table_read", table="Joint Reactions", row_limit=2)[1]
        assert len(body["rows"]) == 2
        assert body["truncated"] is True
    finally:
        client.close()


def test_timeout_fires_on_a_read(rpc: Rpc, control: Path) -> None:
    """AC21: a timeout on any call, a read included, invalidates the launched session."""
    _launch(rpc)
    _fault(control, "timeout_before_apply", tool="csi_list_points")
    error, body = rpc.call("csi_list_points")
    assert error
    assert body["code"] == "timeout"
    assert rpc.call("csi_status")[1]["current_target"]["launched"] is False


def test_timeout_after_apply_on_design_run(rpc: Rpc, control: Path) -> None:
    """A design run that times out is still applied (reconciliation tests of section 4.5.7)."""
    _launch(rpc)
    _fault(control, "timeout_after_apply", tool="csi_design_run")
    error, body = rpc.call("csi_design_run", confirm=True)
    assert error
    assert body["code"] == "timeout"


def test_model_locked_on_destructive_tool(rpc: Rpc) -> None:
    """S-12 report section 7: Destructive tools other than the four exceptions raise model_locked."""
    _launch(rpc)
    assert not rpc.call("csi_run_analysis", confirm=True)[0]
    error, body = rpc.call("csi_new_blank_model", confirm=True)
    assert error
    assert body["code"] == "model_locked"
    assert not rpc.call("csi_save_model", confirm=True)[0]
    assert not rpc.call("csi_design_run", confirm=True)[0]


def test_model_locked_on_design_prefs_set(rpc: Rpc) -> None:
    _launch(rpc)
    assert not rpc.call("csi_run_analysis", confirm=True)[0]
    assert rpc.call("csi_design_prefs_set")[1]["code"] == "model_locked"


def test_analysis_flags_are_shared_between_servers(control: Path) -> None:
    """The host is one program: an analysis run through one server shows in the status and lock the other reads."""
    seed = {"load_cases": [{"name": "DEAD"}, {"name": "LIVE"}]}
    control.write_text(json.dumps({"faults": [], "seed": seed}))
    first, second = Rpc(control), Rpc(control)
    try:
        _launch(first)
        assert not second.call("csi_attach", product="ETABS", pid=4242)[0]
        status = second.call("csi_analysis_status")[1]
        assert status == {"cases": [{"case": "DEAD", "status_code": 1}, {"case": "LIVE", "status_code": 1}]}
        error, body = first.call("csi_run_analysis", confirm=True)
        assert (error, body) == (False, {"started": True})
        status = second.call("csi_analysis_status")[1]
        assert [c["status_code"] for c in status["cases"]] == [4, 4]  # raw codes: the fake does not decode them
        assert second.call("csi_model_info")[1]["locked"] is True
    finally:
        first.close()
        second.close()


def test_design_needs_its_run_and_results_are_seeded(control: Path) -> None:
    """Design rows exist only after a design run of their kind; the results tools answer the seed."""
    rows = [{"frame": "B1", "ratio": 0.75}, {"frame": "B2", "ratio": 0.5}]
    seed = {"design_results": {"steel": rows}, "results": {"csi_results_story_drifts": [{"story": "S1"}]}}
    control.write_text(json.dumps({"faults": [], "seed": seed}))
    client = Rpc(control)
    try:
        _launch(client)
        error, body = client.call("csi_design_results", kind="steel")
        assert error
        assert body["code"] == "csi_error"
        assert not client.call("csi_design_run", kind="steel", confirm=True)[0]
        assert client.call("csi_design_results", kind="steel")[1]["items"] == rows
        assert client.call("csi_design_results", kind="steel", name="B2")[1]["items"] == rows[1:]
        page = client.call("csi_design_results", kind="steel", limit=1)[1]
        assert (page["items"], page["truncated"]) == (rows[:1], True)
        assert client.call("csi_design_results", kind="concrete")[0]  # only steel was run
        for kind in ("aluminum", "coldformed"):
            error, body = client.call("csi_design_run", kind=kind, confirm=True)
            assert (error, body["code"]) == (True, "unsupported_by_version")
        drifts = client.call("csi_results_story_drifts", units="kN_m_C")[1]
        assert (drifts["items"], drifts["units"]) == ([{"story": "S1"}], "kN_m_C")
        assert client.call("csi_results_frame_forces", units="kN_m_C")[1]["items"] == []  # nothing seeded
    finally:
        client.close()


def test_safe_mode_seed_loads_results_and_faults(control: Path) -> None:
    control.write_text(
        json.dumps(
            {
                "product": "SAFE",
                "seed": {
                    "points": [{"name": "P1"}],
                    "areas": [{"name": "A1"}],
                    "area_sections": [{"name": "S1"}],
                    "materials": [{"name": "C1"}],
                    "load_patterns": [{"name": "D"}],
                    "load_combos": [{"name": "U"}],
                    "tables": {
                        "Area Assignments - Area Springs": [{"UniqueName": "A1", "SpringProp": "K"}],
                        "Spring Property Definitions - Area Springs": [{"Name": "K"}],
                        "Joint Loads Assignments - Force": [
                            {"UniqueName": "P1", "LoadPattern": "D", "XDim": 2, "YDim": 3}
                        ],
                        "Soil Pressures": [
                            {"UniqueName": "A1", "Group": "F1", "Pressure": -10},
                            {"UniqueName": "A2", "Group": "F2", "Pressure": -20},
                        ],
                    },
                    "results": {"csi_results_base_reactions": [{"case": "D"}, {"case": "U"}]},
                    "result_limits": {"csi_results_base_reactions": 1, "Soil Pressures": 1},
                },
            }
        )
    )
    client = Rpc(control)
    try:
        assert client.call("csi_launch")[1]["product"] == "SAFE"
        assert client.call("csi_new_model", confirm=True)[1]["code"] == "unsupported_by_version"
        for kind in ("points", "areas", "area_sections", "materials", "load_patterns", "load_combos"):
            assert client.call("csi_list_" + kind)[1]["count"] == 1
        assert (
            client.call("csi_db_table_read", table="Area Assignments - Area Springs")[1]["rows"][0]["SpringProp"] == "K"
        )
        assert (
            "Name"
            in client.call("csi_db_table_fields", table="Spring Property Definitions - Area Springs")[1]["fields"]
        )
        error, _ = client.call("csi_set_point_load", name="P1", load_pattern="D", force=[1, 2, 3], moment=[4, 5, 6])
        assert not error
        rows = client.call("csi_db_table_read", table="Joint Loads Assignments - Force")[1]["rows"]
        assert rows == [
            {
                "UniqueName": "P1",
                "LoadPattern": "D",
                "XDim": 2,
                "YDim": 3,
                "FX": 1,
                "FY": 2,
                "FZ": 3,
                "MX": 4,
                "MY": 5,
                "MZ": 6,
            }
        ]
        result = client.call("csi_results_base_reactions")[1]
        assert result["count"] == 1
        assert result["truncated"] is True
        pressures = client.call("csi_db_table_read", table="Soil Pressures")[1]
        assert len(pressures["rows"]) == 1
        assert pressures["truncated"] is True
        grouped = client.call("csi_db_table_read", table="Soil Pressures", group="F2")[1]
        assert grouped["rows"] == [{"UniqueName": "A2", "Group": "F2", "Pressure": -20}]
        assert grouped["truncated"] is False
        _fault(control, "present_units_mm", tool="csi_model_info")
        assert client.call("csi_model_info")[1]["units"] == "kN_mm_C"
        assert client.call("csi_list_points", units="kN_m_C")[1]["units"] == "kN_m_C"
        assert client.call("csi_model_info")[1]["units"] == "kN_mm_C"
        assert not client.call(
            "csi_set_point_load", name="P1", load_pattern="D", force=[1, 2, 3], moment=[4, 5, 6], units="kN_m_C"
        )[0]
        row = client.call("csi_db_table_read", table="Joint Loads Assignments - Force")[1]["rows"][0]
        assert row["MX"] == 4000
        assert row["FX"] == 1
    finally:
        client.close()


def test_safe_point_load_missing_and_zero(control: Path) -> None:
    control.write_text(json.dumps({"product": "SAFE", "seed": {"points": [{"name": "P1"}]}}))
    client = Rpc(control)
    try:
        client.call("csi_launch")
        args = {"load_pattern": "D", "force": [1, 0, 0], "moment": [0, 0, 0]}
        assert client.call("csi_set_point_load", name="missing", **args)[1]["code"] == "not_found"
        assert not client.call("csi_set_point_load", name="P1", **args)[0]
        args["force"] = [0, 0, 0]
        assert not client.call("csi_set_point_load", name="P1", **args)[0]
        assert client.call("csi_db_table_read", table="Joint Loads Assignments - Force")[1]["rows"] == []
    finally:
        client.close()
