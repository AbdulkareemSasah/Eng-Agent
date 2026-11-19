"""Behaviors and faults of the synthetic Sasaah IDEA fake server (spec 0014 section 4.12), run as a real process."""

import asyncio
import contextlib
import json
import os
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

SERVER = Path(__file__).resolve().parent / "server.py"


class Rpc:
    """Newline-delimited JSON-RPC over the fake's stdio, driven from a private event loop."""

    def __init__(
        self,
        control: Path,
        args: tuple[str, ...] = ("--disable-script", "--call-timeout-sec", "30"),
        *,
        read_timeout: float = 30.0,
    ) -> None:
        self.loop = asyncio.new_event_loop()
        self.read_timeout = read_timeout
        env = {**os.environ, "SASAAH_IDEA_FAKE_CONTROL": str(control)}
        self.proc = self.loop.run_until_complete(
            asyncio.create_subprocess_exec(
                sys.executable,
                str(SERVER),
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                env=env,
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
        self.proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        self.loop.run_until_complete(self.proc.stdin.drain())

    def readline(self) -> str:
        assert self.proc.stdout is not None
        return self.loop.run_until_complete(asyncio.wait_for(self.proc.stdout.readline(), self.read_timeout)).decode(
            "utf-8"
        )

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
        if self.proc.returncode is None:
            self.proc.kill()
            with contextlib.suppress(TimeoutError):
                self.wait()
        if not self.loop.is_closed():
            self.loop.close()


def make_ideacon(path: Path, *, connections: list[dict[str, Any]] | None = None) -> Path:
    """Write a synthetic ``.ideaCon``-like JSON file for tests."""
    payload = {
        "connections": connections
        if connections is not None
        else [
            {
                "id": 1,
                "name": "CON1",
                "loads": [
                    {
                        "id": 1,
                        "name": "LE1",
                        "checkEquilibrium": True,
                        "percentageLoad": False,
                        "forcesOnSegments": [
                            {
                                "beamSegmentId": 1,
                                "position": 0.0,
                                "n": 10000.0,
                                "qy": 0.0,
                                "qz": -5000.0,
                                "mx": 0.0,
                                "my": 2000.0,
                                "mz": 0.0,
                            }
                        ],
                        "forcesPercentageOnSegments": [],
                    }
                ],
            }
        ]
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def control(tmp_path: Path) -> Path:
    path = tmp_path / "control.json"
    path.write_text(json.dumps({"faults": [], "seed": {}}), encoding="utf-8")
    return path


@pytest.fixture
def rpc(control: Path) -> Iterator[Rpc]:
    client = Rpc(control)
    yield client
    client.close()


def _fault(control: Path, fault: str, **extra: Any) -> None:
    data = json.loads(control.read_text(encoding="utf-8"))
    data.setdefault("faults", []).append({"fault": fault, **extra})
    control.write_text(json.dumps(data), encoding="utf-8")


def test_tool_list_hides_run_script_when_disabled(rpc: Rpc) -> None:
    schemas = json.loads((SERVER.parent / "schemas.json").read_text(encoding="utf-8"))
    expected = {t["name"]: t["input_schema"] for t in schemas["tools"] if t["name"] != "idea_run_script"}
    listed = rpc.request("tools/list", {})["tools"]
    assert {t["name"]: t["inputSchema"] for t in listed} == expected
    error, body = rpc.call("idea_run_script", source="x", args={})
    assert error
    assert body["code"] == "script_disabled"


def test_tool_list_exposes_run_script_without_disable_flag(control: Path) -> None:
    schemas = json.loads((SERVER.parent / "schemas.json").read_text(encoding="utf-8"))
    expected = {t["name"]: t["input_schema"] for t in schemas["tools"]}
    client = Rpc(control, args=("--call-timeout-sec", "30"))
    try:
        listed = client.request("tools/list", {})["tools"]
        assert {t["name"]: t["inputSchema"] for t in listed} == expected
        assert client.call("idea_status")[1]["script_enabled"] is True
        assert client.call("idea_run_script", source="class C {}")[1] == {"executed": True}
    finally:
        client.close()


def test_read_only_flag_hides_destructive_and_code_tools(control: Path) -> None:
    client = Rpc(control, args=("--disable-script", "--read-only", "--call-timeout-sec", "30"))
    try:
        names = {t["name"] for t in client.request("tools/list", {})["tools"]}
        assert "idea_calculate" not in names
        assert "idea_native_set_loads" not in names
        assert "idea_run_script" not in names
        assert client.call("idea_status")[1]["read_only"] is True
        error, body = client.call("idea_calculate", confirm=True)
        assert (error, body["code"]) == (True, "no_project")
    finally:
        client.close()


def test_status_defaults_and_faults(rpc: Rpc, control: Path) -> None:
    error, body = rpc.call("idea_status")
    assert not error
    assert body["read_only"] is False
    assert body["script_enabled"] is False
    assert body["service"] == {"reachable": True, "service_version": "24.1.0"}
    assert body["installed"] == [{"version": "24.1", "has_rest_api": True, "hidden_calculator": True}]

    _fault(control, "script_enabled", listed=True)
    assert any(t["name"] == "idea_run_script" for t in rpc.request("tools/list", {})["tools"])
    assert rpc.call("idea_status")[1]["script_enabled"] is True

    _fault(control, "read_only_listed_wrong")
    assert rpc.call("idea_status")[1]["read_only"] is True

    _fault(control, "service_stopped", tool="idea_status")
    assert rpc.call("idea_status")[1]["service"] == {"reachable": False, "service_version": None}


def test_rest_cycle_open_list_calculate_results_close(rpc: Rpc, tmp_path: Path) -> None:
    assert rpc.call("idea_list_connections")[1]["code"] == "no_project"
    assert rpc.call("idea_calculate", confirm=True)[1]["code"] == "no_project"
    assert rpc.call("idea_get_check_results")[1]["code"] == "no_project"

    model = make_ideacon(tmp_path / "joint.ideaCon")
    error, opened = rpc.call("idea_open_project", path=str(model))
    assert not error
    assert opened["backend"] == "rest"
    assert opened["live_project"] is True
    assert opened["service_reachable"] is True
    assert opened["connections"] == [{"id": 1, "name": "CON1", "calculated": False}]

    pre = rpc.call("idea_get_check_results")[1]
    assert pre["connections"][0]["calculated"] is False

    assert rpc.call("idea_calculate")[1]["code"] == "confirmation_required"
    assert rpc.call("idea_calculate", connection_ids=[999], confirm=True)[1]["code"] == "connection_not_found"

    error, calc = rpc.call("idea_calculate", connection_ids=[1], confirm=True)
    assert not error
    assert calc["offline_stub"] is False
    assert calc["backend"] == "rest"
    assert calc["connections"][0]["calculated"] is True
    assert calc["connections"][0]["passed"] is True
    assert [c["name"] for c in calc["connections"][0]["checks"]] == ["Plates", "Bolts"]
    assert all(c["check_value"] > 0 for c in calc["connections"][0]["checks"])

    listed = rpc.call("idea_list_connections", limit=1)[1]
    assert listed["connections"] == [{"id": 1, "name": "CON1", "calculated": True}]
    assert rpc.call("idea_get_check_results", connection_id=1)[1]["connections"] == calc["connections"]

    assert rpc.call("idea_close_project")[1] == {"closed": True}
    assert rpc.call("idea_list_connections")[1]["code"] == "no_project"


def test_service_stopped_and_live_create_fallback_return_stub(rpc: Rpc, control: Path, tmp_path: Path) -> None:
    model = make_ideacon(tmp_path / "joint.ideaCon")
    assert not rpc.call("idea_open_project", path=str(model))[0]

    _fault(control, "service_stopped", tool="idea_calculate")
    error, stub = rpc.call("idea_calculate", connection_ids=[1], confirm=True)
    assert not error
    assert stub["offline_stub"] is True
    assert stub["backend"] == "file"
    assert "notice" in stub
    checks = stub["connections"][0]["checks"]
    assert [c["check_value"] for c in checks] == [35.0, 42.0, 51.0, 47.0, 10.0]
    assert all(c["unity_check_message"] == "Offline stub." for c in checks)

    _fault(control, "live_create_fallback", tool="idea_open_project")
    error, opened = rpc.call("idea_open_project", path=str(model))
    assert not error
    assert opened["backend"] == "file"
    assert opened["live_project"] is False
    assert rpc.call("idea_calculate", confirm=True)[1]["offline_stub"] is True
    assert rpc.call("idea_get_check_results")[1]["offline_stub"] is True


def test_native_get_set_calculate_and_zero_effects(rpc: Rpc, control: Path, tmp_path: Path) -> None:
    src = make_ideacon(tmp_path / "in.ideaCon")
    before_bytes = src.read_bytes()
    out = tmp_path / "out.ideaCon"

    error, loaded = rpc.call("idea_native_get_loads", path=str(src), connection_id="CON1")
    assert not error
    assert loaded["connection"] == "CON1"
    assert len(loaded["loads"]) == 1

    assert rpc.call("idea_native_set_loads", path=str(src), loads=loaded["loads"], out_path=str(out))[1]["code"] == (
        "confirmation_required"
    )
    assert not out.exists()

    zero_effect = {
        "id": 2,
        "name": "LE_ZERO",
        "checkEquilibrium": True,
        "percentageLoad": False,
        "forcesOnSegments": [
            {"beamSegmentId": 1, "position": 0.0, "n": 0.0, "qy": 0.0, "qz": 0.0, "mx": 0.0, "my": 0.0, "mz": 0.0}
        ],
        "forcesPercentageOnSegments": [],
    }
    err_zero, zero_body = rpc.call(
        "idea_native_set_loads", path=str(src), loads=[zero_effect], out_path=str(out), confirm=True
    )
    assert (err_zero, zero_body["code"]) == (True, "idea_error")
    assert not out.exists()

    new_loads = [*loaded["loads"], zero_effect]
    new_loads[0]["forcesOnSegments"][0]["n"] = 25000.0
    error, saved = rpc.call("idea_native_set_loads", path=str(src), loads=new_loads, out_path=str(out), confirm=True)
    assert not error
    assert saved["effects_written"] == 1
    assert saved["dropped_zero"] == ["LE_ZERO"]
    assert src.read_bytes() == before_bytes
    assert out.is_file()

    reread = rpc.call("idea_native_get_loads", path=str(out), connection_id="1")[1]
    assert reread["loads"][0]["forcesOnSegments"][0]["n"] == 25000.0

    _fault(control, "all_zero_loads")
    out2 = tmp_path / "out2.ideaCon"
    assert (
        rpc.call("idea_native_set_loads", path=str(out), loads=reread["loads"], out_path=str(out2), confirm=True)[1][
            "code"
        ]
        == "idea_error"
    )
    assert not out2.exists()

    assert rpc.call("idea_native_calculate", path=str(out), save=True)[1]["code"] == "confirmation_required"
    error, native_calc = rpc.call("idea_native_calculate", path=str(out), connection_id="CON1", save=False)
    assert not error
    assert native_calc["route"] == "native"
    assert native_calc["backend"] is None
    assert native_calc["offline_stub"] is False
    assert native_calc["connections"][0]["calculated"] is True


def test_faults_license_timeouts_and_reply_anomalies(rpc: Rpc, control: Path, tmp_path: Path) -> None:
    model = make_ideacon(tmp_path / "joint.ideaCon")
    assert not rpc.call("idea_open_project", path=str(model))[0]

    _fault(control, "license_refused", tool="idea_calculate")
    err, body = rpc.call("idea_calculate", confirm=True)
    assert (err, body["code"]) == (True, "service_unavailable")
    assert "license seat" in body["message"]

    _fault(control, "license_hang", tool="idea_native_calculate", seconds=0.15)
    t0 = time.monotonic()
    assert not rpc.call("idea_native_calculate", path=str(model))[0]
    assert time.monotonic() - t0 >= 0.12

    _fault(control, "timeout_calculate", tool="idea_calculate")
    assert rpc.call("idea_calculate", confirm=True)[1]["code"] == "timeout"

    _fault(control, "timeout_calculate", tool="idea_native_calculate")
    assert rpc.call("idea_native_calculate", path=str(model))[1]["code"] == "timeout"

    _fault(control, "unexpected_shape", tool="idea_native_calculate")
    assert rpc.call("idea_native_calculate", path=str(model))[1] == {"unexpected": True, "payload": "malformed"}

    _fault(control, "errors_in_reply", tool="idea_native_calculate")
    err_reply = rpc.call("idea_native_calculate", path=str(model))[1]["connections"][0]
    assert err_reply["calculated"] is True
    assert err_reply["passed"] is False
    assert err_reply["errors"]

    _fault(control, "zero_utilization_true", tool="idea_native_calculate")
    zero_util = rpc.call("idea_native_calculate", path=str(model))[1]["connections"][0]["checks"][0]
    assert zero_util["check_value"] == 0.0
    assert zero_util["check_status"] is True

    _fault(control, "passed_disagrees", tool="idea_native_calculate")
    disagrees = rpc.call("idea_native_calculate", path=str(model))[1]["connections"][0]
    assert disagrees["passed"] is True
    assert any(c["check_status"] is False for c in disagrees["checks"])

    _fault(control, "zero_connections_calculated", tool="idea_native_calculate")
    uncalc = rpc.call("idea_native_calculate", path=str(model))[1]["connections"][0]
    assert uncalc["calculated"] is False
    assert uncalc["checks"] == []


@pytest.mark.parametrize(
    ("applied", "mismatch"),
    [
        (False, False),
        (True, False),
        (True, True),
    ],
)
def test_timeout_set_loads_loses_reply(control: Path, tmp_path: Path, applied: bool, mismatch: bool) -> None:
    """Spec 0014 §4.12: timeout_set_loads withholds the reply; the file may or may not be written."""
    client = Rpc(control)
    try:
        model = make_ideacon(tmp_path / "joint.ideaCon")
        assert not client.call("idea_open_project", path=str(model))[0]
        loads = client.call("idea_native_get_loads", path=str(model))[1]["loads"]
        original_n = loads[0]["forcesOnSegments"][0]["n"]
        out = tmp_path / f"out_{applied}_{mismatch}.ideaCon"
        # Fault sleep longer than the short client bound so the reply is lost past it.
        _fault(control, "timeout_set_loads", applied=applied, mismatch=mismatch, seconds=5.0)
        client.read_timeout = 0.25
        with pytest.raises(TimeoutError):
            client.call(
                "idea_native_set_loads",
                path=str(model),
                loads=loads,
                out_path=str(out),
                confirm=True,
            )
        assert out.is_file() is applied
        if applied:
            reread = json.loads(out.read_text(encoding="utf-8"))
            written_n = reread["connections"][0]["loads"][0]["forcesOnSegments"][0]["n"]
            if mismatch:
                assert written_n != original_n
            else:
                assert written_n == original_n
        else:
            assert not out.exists()
    finally:
        client.close()


def test_crash_during_call_and_unknown_tool(rpc: Rpc, control: Path) -> None:
    assert rpc.call("no_such_tool")[1]["code"] == "idea_error"
    _fault(control, "crash_during_call")
    rpc.send({"jsonrpc": "2.0", "id": 99, "method": "tools/call", "params": {"name": "idea_status", "arguments": {}}})
    assert rpc.readline() == ""
    assert rpc.wait() != 0
