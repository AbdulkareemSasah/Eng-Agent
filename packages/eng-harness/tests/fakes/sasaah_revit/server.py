"""Synthetic Sasaah Revit MCP server: a test double, never packaged (spec 0011 section 4.13, lead decision D-5).

Run as a script over stdio. The tool list is generated from ``schemas.json`` (the inventory schemas of the 21
allowlisted MCP names of spec 0011 section 4.4). Success replies are one JSON text block. Failures use ``isError``
with one string ``"<code> <message> <hint>"`` (S-12 report section 6 / spec 0011 section 4.7).

State is in memory. Faults come from the JSON control file named by ``SASAAH_REVIT_FAKE_CONTROL``::

    {"faults": [{"fault": "dialog_declined", "tool": "revit_set_element_parameter_values"}], "seed": {...}}

A matching fault fires once and is removed. Faults that simulate a lost reply (``lost_pipe``,
``dialog_unanswered``, the first attempt of ``retry_token_consumed``, and ``retry_duplicate`` with
``lose_reply``) withhold the reply after an optional ``seconds`` delay (default 30) so the client timeout path
runs; tests pass a small ``seconds`` value. Units of parameter storage are raw feet with ``specId`` and
``builtInParameter`` (spec 0011 section 4.13); list elevations are millimetres as the live server returns.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import types
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server

SCHEMAS = json.loads((Path(__file__).resolve().parent / "schemas.json").read_text(encoding="utf-8"))
TOOLS: dict[str, dict[str, Any]] = {t["name"]: t["input_schema"] for t in SCHEMAS["tools"]}
KINDS: dict[str, str] = {t["name"]: t["server_kind"] for t in SCHEMAS["tools"]}
CONTROL = os.environ.get("SASAAH_REVIT_FAKE_CONTROL")
DEFAULT_PIPE = "\\\\.\\pipe\\sasaah-revit-fake"
DEFAULT_CATALOG = "0123456789abcdef"
DEFAULT_VERSION = "2026"
# Spec 0011 section 4.3 / 4.4: code-toolset names the build check refuses when listed.
CODE_TOOLSET_NAMES = (
    "revit_send_code_to_revit",
    "revit_compile_and_run",
    "revit_dev_hot_run",
    "revit_dev_hot_unload",
    "revit_dev_hot_sessions",
    "revit_run_baked_tool",
    "revit_list_baked_tools",
)
DESTRUCTIVE = {name for name, kind in KINDS.items() if kind == "destructive"}
WRITE_KINDS = {"write", "destructive"}
SESSION_TOOLS = {
    "revit_connection_status",
    "revit_ping",
    "revit_get_current_target",
    "revit_list_available_targets",
}
LOST_REPLY_FAULTS = {"lost_pipe", "dialog_unanswered"}


class BridgeError(Exception):
    """A Revit bridge failure served as ``"<code> <message> <hint>"`` (spec 0011 section 4.7)."""

    def __init__(self, code: str, message: str, hint: str = "") -> None:
        text = f"{code} {message}".strip() if code else message
        if hint:
            text = f"{text} {hint}".strip()
        super().__init__(text)
        self.code = code
        self.message = message
        self.hint = hint


def _read_control() -> dict[str, Any]:
    if not CONTROL:
        return {}
    path = Path(CONTROL)
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _write_control(data: dict[str, Any]) -> None:
    if not CONTROL:
        return
    Path(CONTROL).write_text(json.dumps(data), encoding="utf-8")


def _default_seed() -> dict[str, Any]:
    """A small in-memory model: one level, grid, column, framing member and type (spec 0011 section 4.13)."""
    length_param = {
        "name": "b",
        "value": 1.0,  # raw feet (spec 0011 section 4.13)
        "specId": "autodesk.spec.aec:length-2.0.0",
        "builtInParameter": "STRUCTURAL_SECTION_COMMON_WIDTH",
        "storageType": "Double",
        "isReadOnly": False,
    }
    type_row = {
        "type_id": 2001,
        "family": "Concrete-Rectangular-Column",
        "name": "C300x300",
        "family_id": 1001,
        "category": "OST_StructuralColumns",
        "parameters": [dict(length_param)],
        "instance_ids": [3001],
    }
    column = {
        "element_id": 3001,
        "unique_id": "col-3001",
        "category": "OST_StructuralColumns",
        "family": type_row["family"],
        "type_id": type_row["type_id"],
        "type_name": type_row["name"],
        "level_id": 100,
        "level_name": "Level 1",
        "location_kind": "point",
        "i": {"x": 0.0, "y": 0.0, "z": 0.0},
        "j": None,
        "rotation": 0.0,
        "parameters": [dict(length_param)],
    }
    framing = {
        "element_id": 3002,
        "unique_id": "frm-3002",
        "category": "OST_StructuralFraming",
        "family": "Concrete-Rectangular-Beam",
        "type_id": 2002,
        "type_name": "B300x600",
        "level_id": 100,
        "level_name": "Level 1",
        "location_kind": "curve",
        "i": {"x": 0.0, "y": 0.0, "z": 10.0},
        "j": {"x": 20.0, "y": 0.0, "z": 10.0},
        "rotation": None,
        "parameters": [],
    }
    return {
        "pipe_name": DEFAULT_PIPE,
        "targets": [{"pipe_name": DEFAULT_PIPE, "revit_version": DEFAULT_VERSION}],
        "catalog_version": DEFAULT_CATALOG,
        "ping_status": "ok",
        "uptime_s": 1.0,
        "document": {
            "path": r"C:\models\synthetic.rvt",
            "title": "synthetic",
            "is_workshared": False,
            "revit_version": DEFAULT_VERSION,
        },
        "active_path": r"C:\models\synthetic.rvt",
        "levels": [{"element_id": 100, "name": "Level 1", "elevation_mm": 0.0}],
        "grids": [
            {
                "element_id": 110,
                "name": "A",
                "start": {"x": 0.0, "y": 0.0, "z": 0.0},
                "end": {"x": 10000.0, "y": 0.0, "z": 0.0},
                "length_mm": 10000.0,
            }
        ],
        "elements": [column, framing],
        "types": [
            type_row,
            {
                "type_id": 2002,
                "family": "Concrete-Rectangular-Beam",
                "name": "B300x600",
                "family_id": 1002,
                "category": "OST_StructuralFraming",
                "parameters": [],
                "instance_ids": [3002],
            },
        ],
        "worksets": [{"id": 1, "name": "Workset1", "kind": "UserWorkset", "element_count": 2}],
        "warnings": [],
        "destructive_toolset": True,
        "code_toolset": False,
        "consumed_tokens": [],
        "next_element_id": 4000,
        "next_type_id": 3000,
    }


class State:
    """In-memory document state and the control-file fault dispatcher."""

    def __init__(self) -> None:
        control = _read_control()
        seed = control.get("seed", {})
        base = _default_seed()
        if isinstance(seed, dict):
            base.update(copy.deepcopy(seed))
        if isinstance(control.get("model"), dict):
            base = copy.deepcopy(control["model"])
        self.model: dict[str, Any] = base
        self.read_only = "--read-only" in sys.argv
        pipe_flag = None
        if "--pipe-name" in sys.argv:
            pipe_flag = sys.argv[sys.argv.index("--pipe-name") + 1]
        if pipe_flag:
            self.model["pipe_name"] = pipe_flag
            targets = self.model.setdefault("targets", [])
            if targets and isinstance(targets[0], dict):
                targets[0]["pipe_name"] = pipe_flag

    def persist(self) -> None:
        """Write the model into the control file so a restarted process sees applied writes."""
        if not CONTROL:
            return
        data = _read_control()
        data["model"] = self.model
        _write_control(data)

    def pop_fault(self, tool: str, kinds: set[str]) -> dict[str, Any] | None:
        """Remove and return the first pending fault of ``kinds`` matching ``tool`` (or any tool)."""
        if not CONTROL:
            return None
        data = _read_control()
        for index, entry in enumerate(data.get("faults", [])):
            if entry["fault"] in kinds and entry.get("tool", tool) == tool:
                del data["faults"][index]
                _write_control(data)
                return dict(entry)
        return None

    def has_fault(self, kind: str) -> dict[str, Any] | None:
        for entry in _read_control().get("faults", []):
            if entry["fault"] == kind:
                return dict(entry)
        return None


STATE = State()


async def _withhold(fault: dict[str, Any] | None) -> None:
    """Delay then never reply, so the client times out (lost-reply faults of spec 0011 section 4.13)."""
    seconds = 30.0 if fault is None else float(fault.get("seconds", 30.0))
    await asyncio.sleep(seconds)
    await asyncio.Future()


def _error_result(text: str) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=True)


def _ok_result(body: dict[str, Any] | list[Any] | str | int | float | bool | None) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(body))], is_error=False)


def _note(name: str, args: dict[str, Any]) -> None:
    if not CONTROL:
        return
    data = _read_control()
    entry = {"tool": name, "args": args}
    calls = data.get("calls")
    data["calls"] = [*calls, entry] if isinstance(calls, list) else [entry]
    _write_control(data)


def _element(element_id: int) -> dict[str, Any]:
    for row in STATE.model["elements"]:
        if row["element_id"] == element_id:
            return row
    raise BridgeError("invalid_request", f"Element {element_id} was not found.")


def _type(type_id: int) -> dict[str, Any]:
    for row in STATE.model["types"]:
        if int(row["type_id"]) == int(type_id):
            return row
    raise BridgeError("invalid_request", f"Type {type_id} was not found.")


def _require_document() -> dict[str, Any]:
    document = STATE.model.get("document")
    if not isinstance(document, dict) or not document.get("path"):
        raise BridgeError("invalid_request", "No document is open.")
    return document


def _check_active_document() -> None:
    document = _require_document()
    if STATE.model.get("active_path") != document.get("path"):
        raise BridgeError("invalid_request", "Another document is active.")


def _param_list(owner: dict[str, Any]) -> list[dict[str, Any]]:
    params = owner.setdefault("parameters", [])
    assert isinstance(params, list)
    return params


def _set_param(owner: dict[str, Any], name: str, value: Any, *, by_guid: str | None = None) -> None:
    params = _param_list(owner)
    for row in params:
        if by_guid is not None and row.get("guid") == by_guid:
            row["value"] = value
            return
        if by_guid is None and row.get("name") == name:
            row["value"] = value
            return
    row = {
        "name": name,
        "value": value,
        "specId": "autodesk.spec.aec:length-2.0.0",
        "builtInParameter": name.upper(),
        "storageType": "Double",
        "isReadOnly": False,
    }
    if by_guid is not None:
        row["guid"] = by_guid
    params.append(row)


def _listed_tools() -> list[types.Tool]:
    tools: list[types.Tool] = []
    destructive_off = STATE.has_fault("destructive_toolset_off") is not None or not STATE.model.get(
        "destructive_toolset", True
    )
    code_on = STATE.has_fault("code_toolset_on") is not None or bool(STATE.model.get("code_toolset"))
    for name, schema in TOOLS.items():
        if STATE.read_only and KINDS[name] in WRITE_KINDS:
            continue
        if destructive_off and name in DESTRUCTIVE:
            continue
        tools.append(types.Tool(name=name, input_schema=schema))
    if code_on:
        empty: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}
        for name in CODE_TOOLSET_NAMES:
            tools.append(types.Tool(name=name, input_schema=empty))
    return tools


def _connection_status() -> dict[str, Any]:
    document = STATE.model.get("document") or {}
    return {
        "ping_status": STATE.model.get("ping_status", "ok"),
        "catalog_version": STATE.model.get("catalog_version", DEFAULT_CATALOG),
        "pipe_name": STATE.model.get("pipe_name", DEFAULT_PIPE),
        "revit_version": document.get("revit_version", DEFAULT_VERSION),
        "title": document.get("title"),
        "path": document.get("path"),
        "is_workshared": bool(document.get("is_workshared")),
    }


def _open_model(args: dict[str, Any]) -> dict[str, Any]:
    path = args.get("path")
    if not isinstance(path, str) or not path:
        raise BridgeError("invalid_request", "path is required.")
    if STATE.pop_fault("revit_open_model", {"workshared_open"}):
        STATE.model["document"] = {
            "path": path,
            "title": Path(path).stem,
            "is_workshared": True,
            "revit_version": DEFAULT_VERSION,
        }
        STATE.model["active_path"] = path
        return {"opened": True, "path": path, "is_workshared": True, "local_path": path + "-local"}
    STATE.model["document"] = {
        "path": path,
        "title": Path(path).stem,
        "is_workshared": False,
        "revit_version": DEFAULT_VERSION,
    }
    if args.get("activate", True):
        STATE.model["active_path"] = path
    return {"opened": True, "path": path, "is_workshared": False}


def _list_elements(args: dict[str, Any]) -> dict[str, Any]:
    category = args.get("category")
    level_id = args.get("level_id")
    limit = int(args.get("limit") or 200)
    rows = [
        row
        for row in STATE.model["elements"]
        if row.get("category") == category and (level_id is None or row.get("level_id") == level_id)
    ]
    if STATE.pop_fault("revit_list_elements", {"response_too_large"}):
        raise BridgeError("", "RESPONSE_TOO_LARGE: the reply exceeded the transport limit.")
    return {"count": min(len(rows), limit), "items": rows[:limit], "truncated": len(rows) > limit}


def _details(args: dict[str, Any]) -> dict[str, Any]:
    ids = args.get("elementIds") or []
    items = [_element(int(eid)) for eid in ids]
    return {"items": copy.deepcopy(items)}


def _parameters_for(ids: list[Any], *, types: bool) -> dict[str, Any]:
    items = []
    for raw in ids:
        owner = _type(int(raw)) if types else _element(int(raw))
        items.append(
            {
                "id": int(raw),
                "parameters": copy.deepcopy(_param_list(owner)),
            }
        )
    return {"items": items}


def _family_types(args: dict[str, Any]) -> dict[str, Any]:
    family_id = args.get("family_id")
    family_name = args.get("family_name")
    rows = [
        row
        for row in STATE.model["types"]
        if (family_id is None or row.get("family_id") == family_id)
        and (family_name is None or row.get("family") == family_name)
    ]
    start = int(args.get("start_index") or 0)
    max_types = int(args.get("max_types") or len(rows) or 1)
    slice_rows = rows[start : start + max_types]
    return {"count": len(rows), "items": copy.deepcopy(slice_rows), "truncated": start + max_types < len(rows)}


def _duplicate_type(args: dict[str, Any]) -> dict[str, Any]:
    source = _type(int(args["source_type_id"]))
    new_name = args["new_type_name"]
    if any(row.get("name") == new_name and row.get("family") == source["family"] for row in STATE.model["types"]):
        raise BridgeError("invalid_request", f"Type name {new_name!r} already exists.")
    if args.get("type_parameter_overrides"):
        raise BridgeError("invalid_request", "type_parameter_overrides are refused by the harness rule.")
    new_id = int(STATE.model["next_type_id"])
    STATE.model["next_type_id"] = new_id + 1
    created = {
        "type_id": new_id,
        "family": source["family"],
        "name": new_name,
        "family_id": source["family_id"],
        "category": source["category"],
        "parameters": copy.deepcopy(_param_list(source)),
        "instance_ids": [],
    }
    STATE.model["types"].append(created)
    return {"type_id": new_id, "name": new_name, "family": source["family"]}


def _apply_write(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "revit_duplicate_family_type":
        return _duplicate_type(args)
    if name == "revit_set_type_parameter_values":
        type_ids = args.get("typeIds") or []
        if not type_ids:
            raise BridgeError("invalid_request", "typeIds is required.")
        for tid in type_ids:
            _set_param(_type(int(tid)), str(args["parameterName"]), args["value"])
        return {"ok": True, "typeIds": list(type_ids)}
    if name == "revit_set_element_parameter_values":
        for eid in args["elementIds"]:
            _set_param(_element(int(eid)), str(args["parameterName"]), args["value"])
        return {"ok": True, "elementIds": list(args["elementIds"])}
    if name == "revit_set_parameter_value_by_guid":
        for eid in args["elementIds"]:
            target = args.get("target", "auto")
            owner = _type(int(_element(int(eid))["type_id"])) if target == "type" else _element(int(eid))
            _set_param(owner, str(args["guid"]), args["value"], by_guid=str(args["guid"]))
        return {"ok": True, "elementIds": list(args["elementIds"])}
    if name == "revit_change_element_type":
        type_id = int(args["typeId"])
        _type(type_id)
        changed = []
        for eid in args["elementIds"]:
            row = _element(int(eid))
            if STATE.pop_fault(name, {"element_replaced"}):
                new_id = int(STATE.model["next_element_id"])
                STATE.model["next_element_id"] = new_id + 1
                replacement = copy.deepcopy(row)
                replacement["element_id"] = new_id
                replacement["unique_id"] = f"replaced-{new_id}"
                replacement["type_id"] = type_id
                STATE.model["elements"] = [e for e in STATE.model["elements"] if e["element_id"] != row["element_id"]]
                STATE.model["elements"].append(replacement)
                changed.append({"old_element_id": row["element_id"], "element_id": new_id, "type_id": type_id})
            else:
                row["type_id"] = type_id
                type_row = _type(type_id)
                row["type_name"] = type_row["name"]
                row["family"] = type_row["family"]
                changed.append({"element_id": row["element_id"], "type_id": type_id})
        return {"ok": True, "changed": changed}
    raise BridgeError("invalid_request", f"Unhandled write tool {name}.")


def _run_write(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "revit_open_model":
        return _open_model(args)
    return _apply_write(name, args)


async def _handle_write(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if STATE.read_only:
        raise BridgeError("invalid_request", "Server is running in read-only mode.")
    if not STATE.model.get("destructive_toolset", True) and name in DESTRUCTIVE:
        raise BridgeError("forbidden_destructive", "Destructive toolset is off.")
    if STATE.pop_fault(name, {"other_document_active"}):
        STATE.model["active_path"] = r"C:\models\other.rvt"
    if name != "revit_open_model":
        _check_active_document()

    if STATE.pop_fault(name, {"dialog_declined"}):
        raise BridgeError(
            "forbidden_destructive",
            "Destructive operation was not confirmed in Revit.",
            "declined by the user",
        )
    if unanswered := STATE.pop_fault(name, {"dialog_unanswered"}):
        await _withhold(unanswered)

    if STATE.pop_fault(name, {"commit_unchecked"}):
        return {"ok": True, "committed": False}

    if lost := STATE.pop_fault(name, LOST_REPLY_FAULTS):
        if lost["fault"] == "lost_pipe" and lost.get("applied"):
            _run_write(name, args)
            STATE.persist()
        await _withhold(lost)

    if retry_dup := STATE.pop_fault(name, {"retry_duplicate"}):
        first = _run_write(name, args)
        if retry_dup.get("applied_twice", True):
            _run_write(name, args)
        if retry_dup.get("lose_reply"):
            STATE.persist()
            await _withhold(retry_dup)
        return first

    markers = STATE.model.setdefault("consumed_tokens", [])
    marker = f"{name}:{json.dumps(args, sort_keys=True)}"
    if marker in markers:
        # Resend after retry_token_consumed: the token was single-use (spec 0011 section 4.7 / 4.13).
        raise BridgeError(
            "forbidden_destructive",
            "Invalid or already consumed confirmation token",
            "NOT executed",
        )
    if token_fault := STATE.pop_fault(name, {"retry_token_consumed"}):
        # First attempt: apply and lose the reply so the client times out.
        markers.append(marker)
        _run_write(name, args)
        STATE.persist()
        await _withhold(token_fault)

    if STATE.pop_fault(name, {"timeout_not_started"}):
        raise BridgeError("timeout", f"{name} was NOT executed", "the request never started.")
    if STATE.pop_fault(name, {"timeout_executing"}):
        raise BridgeError("timeout", f"{name} is already executing", "the previous request is still running.")

    return _run_write(name, args)


def _is_write(name: str) -> bool:
    return name == "revit_open_model" or name in DESTRUCTIVE or KINDS.get(name) == "write"


async def _call(name: str, args: dict[str, Any]) -> dict[str, Any] | list[Any]:
    if name not in TOOLS and name not in CODE_TOOLSET_NAMES:
        raise BridgeError("invalid_request", f"Unknown tool {name}.")
    if name in CODE_TOOLSET_NAMES:
        raise BridgeError("invalid_request", f"{name} is a code-toolset hatch and is not served for work.")

    if not _is_write(name) and (lost := STATE.pop_fault(name, LOST_REPLY_FAULTS)):
        await _withhold(lost)

    if name == "revit_connection_status":
        return _connection_status()
    if name == "revit_ping":
        return {"ok": True, "uptime_s": float(STATE.model.get("uptime_s", 1.0))}
    if name == "revit_get_current_target":
        return {"pipe_name": STATE.model.get("pipe_name", DEFAULT_PIPE)}
    if name == "revit_list_available_targets":
        return {"targets": copy.deepcopy(STATE.model.get("targets", []))}
    if name == "revit_get_model_metadata":
        document = _require_document()
        return {
            "title": document.get("title"),
            "path": document.get("path"),
            "is_workshared": bool(document.get("is_workshared")),
            "revit_version": document.get("revit_version", DEFAULT_VERSION),
            "active_path": STATE.model.get("active_path"),
        }
    if name == "revit_list_levels":
        return {"levels": copy.deepcopy(STATE.model["levels"])}
    if name == "revit_list_grids":
        return {"grids": copy.deepcopy(STATE.model["grids"])}
    if name == "revit_list_elements":
        return _list_elements(args)
    if name == "revit_get_element_details":
        return _details(args)
    if name == "revit_get_element_parameters":
        return _parameters_for(list(args.get("elementIds") or []), types=False)
    if name == "revit_get_type_parameters":
        ids = list(args.get("typeIds") or args.get("elementIds") or [])
        return _parameters_for(ids, types=True)
    if name == "revit_get_available_family_types":
        category = args.get("category")
        rows = [row for row in STATE.model["types"] if category is None or row.get("category") == category]
        return {"items": copy.deepcopy(rows)}
    if name == "revit_list_family_types_in_family":
        return _family_types(args)
    if name == "revit_list_worksets":
        return {"worksets": copy.deepcopy(STATE.model["worksets"])}
    if name == "revit_get_model_warnings_summary":
        return {"warnings": copy.deepcopy(STATE.model["warnings"])}
    if _is_write(name):
        return await _handle_write(name, args)
    raise BridgeError("invalid_request", f"Unhandled tool {name}.")


async def on_list_tools(
    ctx: ServerRequestContext[Any], params: types.PaginatedRequestParams | None
) -> types.ListToolsResult:
    """Serve the tool list generated from ``schemas.json``, honouring toolset faults and ``--read-only``."""
    return types.ListToolsResult(tools=_listed_tools())


async def on_call_tool(ctx: ServerRequestContext[Any], params: types.CallToolRequestParams) -> types.CallToolResult:
    """Run one tool and answer in the Revit reply shape (JSON success, string error)."""
    args = dict(params.arguments or {})
    try:
        result = _ok_result(await _call(params.name, args))
        STATE.persist()
        return result
    except BridgeError as error:
        STATE.persist()
        return _error_result(str(error))
    finally:
        _note(params.name, args)


async def main() -> None:
    """Serve over stdio until the client closes the pipe."""
    server: Server[Any] = Server("sasaah-revit-fake", on_list_tools=on_list_tools, on_call_tool=on_call_tool)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
