"""Record mode: the sanitizer, the recording folder, its manifest and the transport wrapper (plan 0002 T17; AC33).

Spec 0002 section 4.8.1: every `tools/list` and `tools/call` request and reply is written as a fixture with paths
outside the run folder and user names replaced, `Project Information` reads dropped, and a manifest of SHA-256 hashes.
"""

import hashlib
import json
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp import types
from mcp.shared.message import SessionMessage
from pydantic import JsonValue

from eng_harness.servers import Recording, RecordMode, Sanitizer, verify_manifest
from eng_harness.servers._buildcheck import tool_list_fingerprint
from eng_harness.servers._transport import TransportStreams

HOME = "/home/jdoe"
SCHEMA: dict[str, Any] = {"type": "object", "properties": {"path": {"type": "string"}}}
TOOLS: list[dict[str, Any]] = [
    {"name": n, "inputSchema": SCHEMA} for n in ("csi_model_info", "csi_open_model", "csi_save_model", "other")
]


def _text(body: dict[str, Any], *, error: bool = False) -> dict[str, Any]:
    """A Sasaah tool result: one JSON text block."""
    return {"content": [{"type": "text", "text": json.dumps(body)}], **({"isError": True} if error else {})}


def _sanitizer(run: str = "/work/run-7") -> Sanitizer:
    return Sanitizer(run, user="jdoe", home=HOME)


def _recording(tmp_path: Path) -> tuple[Recording, Path, Path]:
    run, out = tmp_path / "run", tmp_path / "recordings" / "sasaah-csi-mcp-build1"
    run.mkdir()
    recording = Recording(
        out, run, adapter="sasaah-csi-mcp", build="0123456789ab+fedcba987654",
        tool_names=frozenset({"csi_model_info", "csi_open_model", "csi_save_model"}), user="jdoe", home=HOME,
    )  # fmt: skip
    return recording, run, out


def _session(recording: Recording, run: Path) -> None:
    """The exchanges of a short session, as the wrapper hands them over."""
    house = f"{HOME}/Clients/Acme Tower/Tower-A.EDB"
    recording.add("initialize", {"clientInfo": {"name": "harness"}}, result={"serverInfo": {"name": "sasaah"}})
    recording.add("tools/list", None, result={"tools": TOOLS})
    recording.add("tools/call", {"name": "csi_open_model", "arguments": {"path": house}}, result=_text({"ok": True}))
    recording.add(
        "tools/call", {"name": "csi_model_info", "arguments": {}},
        result=_text({"model_path": house, "message": "Model Tower-A was opened by jdoe"}),
    )  # fmt: skip
    recording.add(
        "tools/call", {"name": "csi_db_table_read", "arguments": {"table": "Project Information"}},
        result=_text({"rows": [{"Company": "Acme Structural"}]}),
    )  # fmt: skip
    recording.add(
        "tools/call", {"name": "csi_save_model", "arguments": {"path": f"{run}/work/Tower-A.EDB"}},
        result=_text(
            {"code": "model_locked", "message": "C:\\Users\\jdoe\\Acme\\Plan.dxf is locked", "data": {}}, error=True
        ),
    )  # fmt: skip


def _files(out: Path) -> list[Path]:
    return sorted(p for p in out.iterdir() if p.name != "manifest.json")


def _body(path: Path, field: str = "reply") -> Any:
    block = json.loads(path.read_text(encoding="utf-8"))[field]["content"][0]
    return json.loads(block["text"])


def test_sanitized_and_manifest(tmp_path: Path) -> None:
    """AC33: paths, names and the user are replaced, the project information read is dropped, the manifest verifies."""
    recording, run, out = _recording(tmp_path)
    _session(recording, run)
    assert recording.finish() == out / "manifest.json"
    names = [p.name for p in _files(out)]
    assert names == [
        "001-initialize.json", "002-tools-list.json", "003-csi_open_model.json", "004-csi_model_info.json",
        "005-csi_save_model.json",
    ]  # fmt: skip
    for path in _files(out):
        text = path.read_text(encoding="utf-8")
        for leak in ("jdoe", "Acme", "Tower", "Clients", "Plan", "Company", "Project Information", str(tmp_path)):
            assert leak not in text, (path.name, leak)
    opened = json.loads((out / names[2]).read_text(encoding="utf-8"))
    assert opened["request"] == {"name": "csi_open_model", "arguments": {"path": "<path>/<model-1>.EDB"}}
    assert (opened["seq"], opened["method"], opened["tool"]) == (3, "tools/call", "csi_open_model")
    assert _body(out / names[3]) == {
        "model_path": "<path>/<model-1>.EDB", "message": "Model <model-1> was opened by <user>",
    }  # fmt: skip
    saved = json.loads((out / names[4]).read_text(encoding="utf-8"))
    assert saved["request"]["arguments"] == {"path": "<run>/work/<model-1>.EDB"}
    assert saved["reply"]["isError"] is True
    assert _body(out / names[4]) == {"code": "model_locked", "message": "<path>/<file-2>.dxf is locked", "data": {}}

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) == {"adapter", "build", "harness_version", "tool_fingerprint", "files"}
    assert (manifest["adapter"], manifest["build"]) == ("sasaah-csi-mcp", "0123456789ab+fedcba987654")
    assert manifest["harness_version"]
    listed = {t["name"]: SCHEMA for t in TOOLS if t["name"] != "other"}  # the allowlisted tools only
    assert manifest["tool_fingerprint"] == tool_list_fingerprint(listed)
    assert manifest["files"] == {n: hashlib.sha256((out / n).read_bytes()).hexdigest() for n in names}
    assert verify_manifest(out) == []

    mapping = json.loads((run / "recording-names.json").read_text(encoding="utf-8"))  # kept in the run folder only
    assert mapping == {"Tower-A.EDB": "<model-1>.EDB", "Plan.dxf": "<file-2>.dxf"}


def test_manifest_problems(tmp_path: Path) -> None:
    """A changed, missing or unlisted file and a missing manifest are each told apart."""
    recording, run, out = _recording(tmp_path)
    _session(recording, run)
    recording.finish()
    (out / "002-tools-list.json").write_text("{}", encoding="utf-8")
    (out / "003-csi_open_model.json").unlink()
    (out / "009-extra.json").write_text("{}", encoding="utf-8")
    assert verify_manifest(out) == [
        "002-tools-list.json: SHA-256 differs",
        "003-csi_open_model.json: missing",
        "009-extra.json: not in the manifest",
    ]
    (out / "manifest.json").unlink()
    [problem] = verify_manifest(out)
    assert problem.startswith("manifest.json: ")
    (out / "manifest.json").write_text("[]", encoding="utf-8")
    assert verify_manifest(out) == ["manifest.json: no object with files"]


def test_manifest_without_tool_list(tmp_path: Path) -> None:
    """A session that never listed the tools has no fingerprint to compare."""
    recording, _run, out = _recording(tmp_path)
    recording.add("tools/call", {"name": "csi_model_info", "arguments": {}}, result=_text({"units": "kN_m_C"}))
    recording.finish()
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8"))["tool_fingerprint"] is None


def test_names_before_their_path_are_replaced(tmp_path: Path) -> None:
    """The pass over the whole session registers every file name first, so an earlier quote of it is replaced too."""
    recording, _run, out = _recording(tmp_path)
    recording.add("tools/call", {"name": "csi_model_info", "arguments": {}}, result=_text({"m": "Tower-A is open"}))
    recording.add("tools/call", {"name": "csi_open_model", "arguments": {"path": "/x/Tower-A.EDB"}}, result=_text({}))
    recording.finish()
    assert _body(out / "001-csi_model_info.json") == {"m": "<model-1> is open"}


def test_a_json_rpc_error_is_recorded(tmp_path: Path) -> None:
    recording, _run, out = _recording(tmp_path)
    recording.add(
        "tools/call", {"name": "csi_model_info", "arguments": {}}, error={"code": -32601, "message": "no jdoe"}
    )
    recording.finish()
    saved = json.loads((out / "001-csi_model_info.json").read_text(encoding="utf-8"))
    assert saved["error"] == {"code": -32601, "message": "no <user>"}
    assert "reply" not in saved


def test_plain_text_reply_and_other_methods(tmp_path: Path) -> None:
    """A reply that is not JSON is sanitized as text; a method other than a call is named by the method."""
    recording, _run, out = _recording(tmp_path)
    recording.add("ping", None, result={})
    block = {"type": "text", "text": "failed for jdoe"}
    recording.add("tools/call", {"name": "csi_model_info", "arguments": {}}, result={"content": [block]})
    recording.finish()
    assert (out / "001-ping.json").is_file()
    assert json.loads((out / "002-csi_model_info.json").read_text(encoding="utf-8"))["reply"] == {
        "content": [{"type": "text", "text": "failed for <user>"}]
    }


def test_user_and_home_default_to_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOGNAME", "env-user")
    monkeypatch.setenv("USER", "env-user")
    monkeypatch.setenv("HOME", "/home/env-user")
    run, out = tmp_path / "run", tmp_path / "out"
    run.mkdir()
    recording = Recording(out, run, adapter="a", build="b")
    recording.add("tools/call", {"name": "t", "arguments": {"p": "/home/env-user", "u": "env-user"}}, result={})
    recording.finish()
    saved = json.loads((out / "001-t.json").read_text(encoding="utf-8"))
    assert saved["request"]["arguments"] == {"p": "<home>", "u": "<user>"}


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("/work/run-7/models/Tower-A.EDB", "<run>/models/<model-1>.EDB"),
        ("/work/run-7/Tower-A.EDB.", "<run>/<model-1>.EDB."),
        ("/WORK/Run-7/a/b/c.dxf", "<run>/a/b/<file-1>.dxf"),
        ("/work/run-7", "<run>"),
        ("/home/jdoe", "<home>"),
        (HOME + "/", "<home>/"),
        (HOME + "/Clients/Acme Tower/Tower-A.EDB", "<path>/<model-1>.EDB"),
        ("C:\\Users\\jdoe\\Acme Tower\\Tower-A.edb", "<path>/<model-1>.edb"),
        ("D:/models/Tower-A.e2k", "<path>/<model-1>.e2k"),
        ("/srv/data/Tower-A.fdb", "<path>/<model-1>.fdb"),
        ("/srv/data/Tower-A.s2k", "<path>/<model-1>.s2k"),
        ("/srv/data/Tower-A.sdb", "<path>/<model-1>.sdb"),
        ("/srv/data/Tower-A.f2k", "<path>/<model-1>.f2k"),
        ("/srv/data/Tower-A.rvt", "<path>/<model-1>.rvt"),
        ("/srv/data/plan.dxf", "<path>/<file-1>.dxf"),
        ("/srv/data/folder", "<path>/<file-1>"),
        ("see /srv/data/Tower-A.EDB now", "see <path>/<model-1>.EDB now"),
        ("see (/srv/data/Tower-A.EDB)", "see (<path>/<model-1>.EDB)"),
        ("open Tower-A.EDB or plan.dxf", "open <model-1>.EDB or <file-2>.dxf"),
        ("open Tower-A.v2.EDB", "open <model-1>.EDB"),
        ("jdoe and JDOE and jdoes", "<user> and <user> and jdoes"),
        ("kN_m_C kN/m 1/2 a/b csi_run_analysis", "kN_m_C kN/m 1/2 a/b csi_run_analysis"),
        ("frames/1 relative/path.txt", "frames/1 relative/path.txt"),
    ],
)
def test_text(raw: str, clean: str) -> None:
    """Paths by the rules of 4.8.1; a file keeps its extension; ordinary text and units pass unchanged."""
    assert _sanitizer().text(raw) == clean


def test_names_are_numbered_by_first_appearance() -> None:
    sanitizer = _sanitizer()
    assert sanitizer.text("/a/Tower-A.EDB") == "<path>/<model-1>.EDB"
    assert sanitizer.text("/b/plan.dxf") == "<path>/<file-2>.dxf"
    assert sanitizer.text("/c/TOWER-a.e2k") == "<path>/<model-1>.e2k"  # the same base name, whatever its case
    assert sanitizer.text("/d/Other.EDB") == "<path>/<model-3>.EDB"
    assert sanitizer.names == {
        "Tower-A.EDB": "<model-1>.EDB", "plan.dxf": "<file-2>.dxf", "TOWER-a.e2k": "<model-1>.e2k",
        "Other.EDB": "<model-3>.EDB",
    }  # fmt: skip


def test_bare_base_names_follow_the_registered_names() -> None:
    sanitizer = _sanitizer()
    sanitizer.text("/a/Tower-A.EDB")
    assert (
        sanitizer.text("Model 'tower-a' is locked; Tower-Annex is not")
        == "Model '<model-1>' is locked; Tower-Annex is not"
    )
    assert sanitizer.text("<model-1> <run> <path>/<file-9>") == "<model-1> <run> <path>/<file-9>"


def test_values() -> None:
    """Strings are sanitized wherever they are, the keys, numbers, booleans and null are not."""
    sanitizer = _sanitizer()
    value: JsonValue = {
        "model_path": "/h/Tower-A.EDB", "count": 3, "ok": True, "none": None, "ratio": 0.5,
        "items": [{"user": "jdoe"}, "jdoe", 7], "jdoe": "x",
    }  # fmt: skip
    assert sanitizer.value(value) == {
        "model_path": "<path>/<model-1>.EDB", "count": 3, "ok": True, "none": None, "ratio": 0.5,
        "items": [{"user": "<user>"}, "<user>", 7], "jdoe": "x",
    }  # fmt: skip


def test_sanitizing_twice_changes_nothing() -> None:
    sanitizer = _sanitizer()
    once = sanitizer.value({"a": "/x/y/Tower-A.EDB", "b": "/work/run-7/p/q.dxf", "c": "jdoe /home/jdoe Tower-A"})
    assert sanitizer.value(once) == once
    assert _sanitizer().value(once) == once


Inner = Callable[[types.JSONRPCRequest], types.JSONRPCResponse | types.JSONRPCError]


class _Server(AbstractAsyncContextManager[TransportStreams]):
    """A transport whose far end answers each request with `answer`; notifications get no answer."""

    def __init__(self, answer: Inner) -> None:
        self._answer = answer
        self.received: list[types.JSONRPCMessage] = []
        self._context = self._open()

    async def __aenter__(self) -> TransportStreams:
        return await self._context.__aenter__()

    async def __aexit__(self, *exc: Any) -> None:
        await self._context.__aexit__(*exc)

    @asynccontextmanager
    async def _open(self) -> AsyncIterator[TransportStreams]:
        read_send, read_recv = anyio.create_memory_object_stream[SessionMessage | Exception](8)
        write_send, write_recv = anyio.create_memory_object_stream[SessionMessage](8)

        async def serve() -> None:
            async with read_send:
                async for message in write_recv:
                    self.received.append(message.message)
                    if isinstance(message.message, types.JSONRPCRequest):
                        await read_send.send(SessionMessage(self._answer(message.message)))

        async with anyio.create_task_group() as group:
            group.start_soon(serve)
            yield read_recv, write_send
            await write_send.aclose()
            group.cancel_scope.cancel()


def _request(number: int, method: str, params: dict[str, Any] | None = None) -> SessionMessage:
    return SessionMessage(types.JSONRPCRequest(jsonrpc="2.0", id=number, method=method, params=params))


async def _next(read: Any) -> types.JSONRPCMessage:
    item = await read.receive()
    assert isinstance(item, SessionMessage)
    return item.message


def test_record_mode_taps_the_transport(tmp_path: Path) -> None:
    """Every request and its reply pass unchanged and are recorded; notifications are not; leaving writes the files."""
    recording, _run, out = _recording(tmp_path)

    def answer(request: types.JSONRPCRequest) -> types.JSONRPCResponse | types.JSONRPCError:
        if request.method == "tools/call" and (request.params or {}).get("name") == "bad":
            error = types.ErrorData(code=-32602, message="unknown tool for jdoe")
            return types.JSONRPCError(jsonrpc="2.0", id=request.id, error=error)
        return types.JSONRPCResponse(jsonrpc="2.0", id=request.id, result=_text({"echo": request.method}))

    server = _Server(answer)
    seen: list[Any] = []

    async def drive() -> None:
        async with RecordMode(server, recording) as (read, write):
            await write.send(_request(1, "tools/list"))
            seen.append(await _next(read))
            await write.send(
                SessionMessage(types.JSONRPCNotification(jsonrpc="2.0", method="notifications/initialized"))
            )
            await write.send(_request(2, "tools/call", {"name": "bad", "arguments": {}}))
            seen.append(await _next(read))
            await write.send(_request(3, "tools/call", {"name": "csi_model_info", "arguments": {"path": "/q/T.EDB"}}))
            seen.append(await _next(read))

    anyio.run(drive)
    assert [type(m).__name__ for m in seen] == ["JSONRPCResponse", "JSONRPCError", "JSONRPCResponse"]
    assert [m.method for m in server.received if isinstance(m, types.JSONRPCRequest | types.JSONRPCNotification)] == [
        "tools/list",
        "notifications/initialized",
        "tools/call",
        "tools/call",
    ]
    assert [p.name for p in _files(out)] == ["001-tools-list.json", "002-bad.json", "003-csi_model_info.json"]
    assert json.loads((out / "002-bad.json").read_text(encoding="utf-8"))["error"] == {
        "code": -32602,
        "message": "unknown tool for <user>",
    }
    assert json.loads((out / "003-csi_model_info.json").read_text(encoding="utf-8"))["request"] == {
        "name": "csi_model_info",
        "arguments": {"path": "<path>/<model-1>.EDB"},
    }
    assert verify_manifest(out) == []


def test_record_mode_drops_project_information_reads(tmp_path: Path) -> None:
    recording, _run, out = _recording(tmp_path)
    server = _Server(lambda r: types.JSONRPCResponse(jsonrpc="2.0", id=r.id, result=_text({"rows": [{"A": 1}]})))

    async def drive() -> None:
        async with RecordMode(server, recording) as (read, write):
            for number, table in enumerate(("Project Information", "project_information", "Story Definitions"), 1):
                await write.send(
                    _request(number, "tools/call", {"name": "csi_db_table_read", "arguments": {"table": table}})
                )
                await _next(read)

    anyio.run(drive)
    [only] = _files(out)
    assert only.name == "001-csi_db_table_read.json"
    assert json.loads(only.read_text(encoding="utf-8"))["request"]["arguments"] == {"table": "Story Definitions"}


def test_revit_sanitized(tmp_path: Path) -> None:
    """AC31: titles, paths and user names are replaced (spec 0011 section 4.13 / AC31)."""
    run, out = tmp_path / "run", tmp_path / "recordings" / "sasaah-revit-mcp-build1"
    run.mkdir()
    tools = [
        {"name": n, "inputSchema": SCHEMA}
        for n in ("revit_open_model", "revit_get_model_metadata", "revit_connection_status")
    ]
    recording = Recording(
        out,
        run,
        adapter="sasaah-revit-mcp",
        build="0123456789ab+fedcba987654",
        tool_names=frozenset(t["name"] for t in tools),
        user="jdoe",
        home=HOME,
    )
    house = f"{HOME}/Clients/Acme Tower/Tower-A.rvt"
    title = "Acme Tower Project"
    recording.add("tools/list", None, result={"tools": tools})
    recording.add(
        "tools/call",
        {"name": "revit_open_model", "arguments": {"path": house, "activate": True}},
        result=_text({"opened": True, "path": house}),
    )
    recording.add(
        "tools/call",
        {"name": "revit_get_model_metadata", "arguments": {}},
        result=_text(
            {
                "title": title,
                "path": house,
                "message": f"Document {title} opened by jdoe",
            }
        ),
    )
    assert recording.finish() == out / "manifest.json"
    names = [p.name for p in _files(out)]
    assert names == [
        "001-tools-list.json",
        "002-revit_open_model.json",
        "003-revit_get_model_metadata.json",
    ]
    for path in _files(out):
        text = path.read_text(encoding="utf-8")
        for leak in ("jdoe", "Acme", "Tower", "Clients", "Project", str(tmp_path)):
            assert leak not in text, (path.name, leak)
    opened = json.loads((out / names[1]).read_text(encoding="utf-8"))
    assert opened["request"] == {
        "name": "revit_open_model",
        "arguments": {"path": "<path>/<model-1>.rvt", "activate": True},
    }
    meta = _body(out / names[2])
    assert meta["title"] == "<title-1>"
    assert meta["path"] == "<path>/<model-1>.rvt"
    assert meta["message"] == "Document <title-1> opened by <user>"
    assert verify_manifest(out) == []
