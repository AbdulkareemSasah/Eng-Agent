"""Behaviours of the synthetic Sasaah Revit fake server (spec 0011 section 4.13), run as a real process."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

SERVER = Path(__file__).resolve().parent / "server.py"
SCHEMAS = SERVER.parent / "schemas.json"


class Rpc:
    """Newline-delimited JSON-RPC over the fake's stdio, driven from a private event loop."""

    def __init__(self, control: Path, *, args: tuple[str, ...] = (), read_timeout: float = 30.0) -> None:
        self.loop = asyncio.new_event_loop()
        self.read_timeout = read_timeout
        env = {**os.environ, "SASAAH_REVIT_FAKE_CONTROL": str(control)}
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
        self.proc.stdin.write((json.dumps(message) + "\n").encode())
        self.loop.run_until_complete(self.proc.stdin.drain())

    def readline(self) -> str:
        assert self.proc.stdout is not None
        return self.loop.run_until_complete(asyncio.wait_for(self.proc.stdout.readline(), self.read_timeout)).decode()

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

    def call(self, tool: str, /, **arguments: Any) -> tuple[bool, Any]:
        result = self.request("tools/call", {"name": tool, "arguments": arguments})
        blocks = result["content"]
        assert len(blocks) == 1
        assert blocks[0]["type"] == "text"
        text = blocks[0]["text"]
        error = bool(result.get("isError"))
        if error:
            return error, text
        return error, json.loads(text)

    def close(self) -> None:
        assert self.proc.stdin is not None
        if not self.proc.stdin.is_closing():
            self.proc.stdin.close()
        try:
            self.wait()
        except TimeoutError:
            self.proc.kill()
            self.wait()
        self.loop.close()


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


def test_tool_list_equals_schemas(rpc: Rpc) -> None:
    schemas = json.loads(SCHEMAS.read_text(encoding="utf-8"))
    listed = rpc.request("tools/list", {})["tools"]
    assert {t["name"]: t["inputSchema"] for t in listed} == {t["name"]: t["input_schema"] for t in schemas["tools"]}


def test_seed_reads_levels_grids_elements_and_raw_feet_parameters(rpc: Rpc) -> None:
    levels = rpc.call("revit_list_levels")[1]
    assert levels["levels"][0]["name"] == "Level 1"
    assert levels["levels"][0]["elevation_mm"] == 0.0
    grids = rpc.call("revit_list_grids")[1]
    assert grids["grids"][0]["name"] == "A"
    columns = rpc.call("revit_list_elements", category="OST_StructuralColumns")[1]
    assert columns["items"][0]["unique_id"] == "col-3001"
    params = rpc.call("revit_get_element_parameters", elementIds=[3001])[1]
    row = params["items"][0]["parameters"][0]
    assert row["value"] == 1.0
    assert row["specId"] == "autodesk.spec.aec:length-2.0.0"
    assert row["builtInParameter"] == "STRUCTURAL_SECTION_COMMON_WIDTH"
    status = rpc.call("revit_connection_status")[1]
    assert status["ping_status"] == "ok"
    assert status["catalog_version"]
    assert rpc.call("revit_get_current_target")[1]["pipe_name"]


def test_open_model_and_writes_apply(rpc: Rpc) -> None:
    error, opened = rpc.call("revit_open_model", path=r"C:\models\copy.rvt")
    assert not error
    assert opened["opened"] is True
    assert opened["is_workshared"] is False
    assert rpc.call("revit_get_model_metadata")[1]["path"] == r"C:\models\copy.rvt"
    error, duplicated = rpc.call("revit_duplicate_family_type", source_type_id="2001", new_type_name="C400x400")
    assert not error
    assert duplicated["name"] == "C400x400"
    assert not rpc.call(
        "revit_set_element_parameter_values",
        elementIds=[3001],
        parameterName="b",
        value="1.5",
        valueType="double",
    )[0]
    params = rpc.call("revit_get_element_parameters", elementIds=[3001])[1]
    assert params["items"][0]["parameters"][0]["value"] == "1.5"
    assert not rpc.call("revit_change_element_type", elementIds=[3001], typeId=duplicated["type_id"])[0]
    details = rpc.call("revit_get_element_details", elementIds=[3001])[1]
    assert details["items"][0]["type_id"] == duplicated["type_id"]


def test_dialog_declined_and_commit_unchecked(rpc: Rpc, control: Path) -> None:
    _fault(control, "dialog_declined", tool="revit_set_element_parameter_values")
    error, text = rpc.call(
        "revit_set_element_parameter_values",
        elementIds=[3001],
        parameterName="b",
        value="9",
        valueType="double",
    )
    assert error
    assert "forbidden_destructive" in text
    assert "declined by the user" in text
    assert rpc.call("revit_get_element_parameters", elementIds=[3001])[1]["items"][0]["parameters"][0]["value"] == 1.0

    _fault(control, "commit_unchecked", tool="revit_set_element_parameter_values")
    error, body = rpc.call(
        "revit_set_element_parameter_values",
        elementIds=[3001],
        parameterName="b",
        value="9",
        valueType="double",
    )
    assert not error
    assert body["ok"] is True
    assert rpc.call("revit_get_element_parameters", elementIds=[3001])[1]["items"][0]["parameters"][0]["value"] == 1.0


def test_timeout_texts_and_response_too_large(rpc: Rpc, control: Path) -> None:
    _fault(control, "timeout_not_started", tool="revit_duplicate_family_type")
    error, text = rpc.call("revit_duplicate_family_type", source_type_id="2001", new_type_name="X")
    assert error
    assert text.startswith("timeout ")
    assert "NOT executed" in text

    _fault(control, "timeout_executing", tool="revit_duplicate_family_type")
    error, text = rpc.call("revit_duplicate_family_type", source_type_id="2001", new_type_name="Y")
    assert error
    assert "already executing" in text

    _fault(control, "response_too_large", tool="revit_list_elements")
    error, text = rpc.call("revit_list_elements", category="OST_StructuralColumns")
    assert error
    assert text.startswith("RESPONSE_TOO_LARGE:")


def test_element_replaced_other_document_and_workshared(rpc: Rpc, control: Path) -> None:
    _fault(control, "element_replaced", tool="revit_change_element_type")
    error, body = rpc.call("revit_change_element_type", elementIds=[3001], typeId=2001)
    assert not error
    assert body["changed"][0]["old_element_id"] == 3001
    new_id = body["changed"][0]["element_id"]
    assert new_id != 3001
    assert rpc.call("revit_get_element_details", elementIds=[3001])[0]
    assert not rpc.call("revit_get_element_details", elementIds=[new_id])[0]

    _fault(control, "other_document_active", tool="revit_set_element_parameter_values")
    error, text = rpc.call(
        "revit_set_element_parameter_values",
        elementIds=[3002],
        parameterName="b",
        value="2",
        valueType="double",
    )
    assert error
    assert "Another document is active" in text

    _fault(control, "workshared_open", tool="revit_open_model")
    error, opened = rpc.call("revit_open_model", path=r"C:\models\central.rvt")
    assert not error
    assert opened["is_workshared"] is True


def test_toolset_faults_change_listed_tools(control: Path) -> None:
    _fault(control, "destructive_toolset_off")
    client = Rpc(control)
    try:
        names = {tool["name"] for tool in client.request("tools/list", {})["tools"]}
        assert "revit_set_element_parameter_values" not in names
        assert "revit_list_levels" in names
    finally:
        client.close()

    data = json.loads(control.read_text(encoding="utf-8"))
    data["faults"] = [{"fault": "code_toolset_on"}]
    control.write_text(json.dumps(data), encoding="utf-8")
    client = Rpc(control)
    try:
        names = {tool["name"] for tool in client.request("tools/list", {})["tools"]}
        assert "revit_compile_and_run" in names
        assert "revit_batch_execute" not in names
    finally:
        client.close()

    client = Rpc(control, args=("--read-only",))
    try:
        names = {tool["name"] for tool in client.request("tools/list", {})["tools"]}
        assert "revit_list_levels" in names
        assert "revit_open_model" not in names
        assert "revit_set_element_parameter_values" not in names
    finally:
        client.close()


def test_lost_reply_faults_withhold_response(control: Path) -> None:
    """Lost-reply faults withhold the reply (no error body) so the client timeout path runs."""
    client = Rpc(control)
    try:
        before = client.call("revit_get_element_parameters", elementIds=[3001])[1]["items"][0]["parameters"][0]["value"]
        _fault(control, "lost_pipe", tool="revit_list_levels", seconds=5.0)
        client.read_timeout = 0.25
        with pytest.raises(TimeoutError):
            client.call("revit_list_levels")
    finally:
        client.close()

    client = Rpc(control)
    try:
        _fault(
            control,
            "retry_token_consumed",
            tool="revit_set_element_parameter_values",
            seconds=5.0,
        )
        client.read_timeout = 0.25
        with pytest.raises(TimeoutError):
            client.call(
                "revit_set_element_parameter_values",
                elementIds=[3001],
                parameterName="b",
                value="7",
                valueType="double",
            )
    finally:
        client.close()

    client = Rpc(control)
    try:
        after = client.call("revit_get_element_parameters", elementIds=[3001])[1]["items"][0]["parameters"][0]["value"]
        assert after == "7"
        assert after != before
        error, text = client.call(
            "revit_set_element_parameter_values",
            elementIds=[3001],
            parameterName="b",
            value="7",
            valueType="double",
        )
        assert error
        assert "Invalid or already consumed confirmation token" in text
    finally:
        client.close()


def test_retry_duplicate_applies_twice(rpc: Rpc, control: Path) -> None:
    _fault(control, "retry_duplicate", tool="revit_set_element_parameter_values", applied_twice=True)
    error, body = rpc.call(
        "revit_set_element_parameter_values",
        elementIds=[3001],
        parameterName="b",
        value="3.25",
        valueType="double",
    )
    assert not error
    assert body["ok"] is True
    value = rpc.call("revit_get_element_parameters", elementIds=[3001])[1]["items"][0]["parameters"][0]["value"]
    assert value == "3.25"


def test_dialog_unanswered_withholds_reply(control: Path) -> None:
    client = Rpc(control)
    try:
        _fault(control, "dialog_unanswered", tool="revit_set_element_parameter_values", seconds=5.0)
        client.read_timeout = 0.25
        with pytest.raises(TimeoutError):
            client.call(
                "revit_set_element_parameter_values",
                elementIds=[3001],
                parameterName="b",
                value="8",
                valueType="double",
            )
        # Nothing applied: the dialog never answered, so the write never ran.
    finally:
        client.close()
    client = Rpc(control)
    try:
        value = client.call("revit_get_element_parameters", elementIds=[3001])[1]["items"][0]["parameters"][0]["value"]
        assert value == 1.0
    finally:
        client.close()


def test_error_shape_is_plain_string(rpc: Rpc) -> None:
    error, text = rpc.call("revit_get_element_details", elementIds=[999999])
    assert error
    assert isinstance(text, str)
    assert text.startswith("invalid_request ")
