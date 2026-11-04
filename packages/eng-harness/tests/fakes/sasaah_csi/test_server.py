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
    data["faults"].append({"fault": fault, **extra})
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
