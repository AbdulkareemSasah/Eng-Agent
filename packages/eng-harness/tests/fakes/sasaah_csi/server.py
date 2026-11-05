"""Synthetic Sasaah CSI MCP server: a test double, never packaged (spec 0002 section 4.8.3, lead decision D-5).

Run as a script over stdio. The tool list is generated from ``schemas.json`` (a copy of the S-12 inventory's names and
input schemas for the non-excluded tools). Replies follow the Sasaah shape: one JSON text block, and ``isError`` with
``{code, message, data}`` on failure. State is in memory. Faults come from the JSON control file named by the
environment variable ``SASAAH_CSI_FAKE_CONTROL``::

    {"faults": [{"fault": "timeout_before_apply", "tool": "csi_add_point"}], "seed": {"points": [...], "tables": {...}}}

A fault fires once and is removed from the file. Faults: ``timeout_before_apply``, ``timeout_after_apply``,
``crash_during_call``, ``units_left_changed``, ``slow_analysis`` (optional ``seconds``) and ``com_worker_recycled``.
Units are the Sasaah tokens of the S-12 report (section 4); the fake invents no engineering value.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from mcp import types
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server

SCHEMAS = json.loads((Path(__file__).resolve().parent / "schemas.json").read_text())
TOOLS: dict[str, dict[str, Any]] = {t["name"]: t["input_schema"] for t in SCHEMAS["tools"]}
CONTROL = os.environ.get("SASAAH_CSI_FAKE_CONTROL")
DEFAULT_UNITS = "kN_m_C"
DEFAULT_LIMIT = 2000  # S-12 section 2: `limit` is at most 2000 on every list tool
PID = 4242  # a fixed fake process id
KINDS: dict[str, str] = {t["name"]: t["server_kind"] for t in SCHEMAS["tools"]}  # S-12 inventory `server_kind`
WRITE_KINDS = {"Write", "Destructive"}  # S-12 report section 7: these raise model_locked while the model is locked
LOCK_EXEMPT = {"csi_unlock_model", "csi_save_model", "csi_run_analysis", "csi_design_run"}  # S-12 report section 7
NEEDS_LAUNCHED = {"csi_open_model", "csi_new_model", "csi_new_blank_model", "csi_exit"}
COLLECTIONS = (
    "stories", "grids", "points", "frames", "areas", "materials", "frame_sections", "area_sections",
    "load_patterns", "load_cases", "load_combos",
)  # fmt: skip


class SasaahError(Exception):
    """A Sasaah error reply ``{code, message, data}``."""

    def __init__(self, code: str, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data or {}


class State:
    """The in-memory model and session of the fake."""

    def __init__(self) -> None:
        self.model: dict[str, Any] = {c: [] for c in COLLECTIONS}
        self.model.update(units=DEFAULT_UNITS, locked=False, file_path=None, tables={})
        self.target: dict[str, Any] | None = None
        self.session_valid = True
        if CONTROL:
            self.model.update(json.loads(Path(CONTROL).read_text()).get("seed", {}))

    def pop_fault(self, tool: str, kinds: set[str]) -> dict[str, Any] | None:
        """Remove and return the first pending fault of one of ``kinds`` aimed at ``tool`` (or at any tool)."""
        if not CONTROL:
            return None
        path = Path(CONTROL)
        data = json.loads(path.read_text())
        for index, entry in enumerate(data.get("faults", [])):
            if entry["fault"] in kinds and entry.get("tool", tool) == tool:
                del data["faults"][index]
                path.write_text(json.dumps(data))
                return dict(entry)
        return None


STATE = State()


def _timeout() -> SasaahError:
    STATE.session_valid = False  # the cached session is invalidated (S-12 section 5)
    return SasaahError("timeout", "The call timed out.")


def _session(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "csi_status":
        return {"read_only": False, "script_enabled": False, "instances": [], "current_target": STATE.target}
    if name in ("csi_attach", "csi_launch"):
        launched = name == "csi_launch"
        STATE.target = {"product": args.get("product", "ETABS"), "pid": args.get("pid", PID), "launched": launched}
        STATE.session_valid = True
        return dict(STATE.target)
    if name == "csi_detach":
        STATE.target = None
        return {"detached": True}
    assert STATE.target is not None
    if name == "csi_exit":
        pid = STATE.target["pid"]
        STATE.target = None
        return {"exited": True, "pid": pid}
    return {"ok": True}


def _add(kind: str, args: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = STATE.model[kind]
    name = args.get("name") or f"{kind[:-1]}{len(items) + 1}"
    items.append({**{k: v for k, v in args.items() if k not in ("units", "target", "dry_run")}, "name": name})
    return {"name": name}


def _list(kind: str, args: dict[str, Any], units: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = STATE.model[kind]
    limit = int(args.get("limit") or DEFAULT_LIMIT)
    return {"count": min(len(items), limit), "items": items[:limit], "truncated": len(items) > limit, "units": units}


def _apply(name: str, args: dict[str, Any], units: str) -> dict[str, Any]:
    model = STATE.model
    if name == "csi_model_info":
        return {"units": model["units"], "locked": model["locked"], "file_path": model["file_path"]}
    if name.startswith("csi_list_") and name[len("csi_list_") :] in COLLECTIONS:
        return _list(name[len("csi_list_") :], args, units)
    if name == "csi_db_table_read":
        rows = model["tables"].get(args.get("table"), [])
        limit = int(args.get("row_limit") or DEFAULT_LIMIT)
        return {"rows": rows[:limit], "truncated": len(rows) > limit}
    adds = {"csi_add_point": "points", "csi_add_frame_by_coord": "frames", "csi_add_area_by_coord": "areas"}
    adds.update(csi_add_load_pattern="load_patterns", csi_add_load_combo="load_combos")
    if name in adds:
        return _add(adds[name], args)
    if name == "csi_delete_load_combo":
        model["load_combos"] = [c for c in model["load_combos"] if c["name"] != args.get("name")]
    elif name == "csi_run_analysis":
        model["locked"] = True
    elif name == "csi_unlock_model":
        model["locked"] = False
    elif name in ("csi_save_model", "csi_open_model"):
        model["file_path"] = args.get("path", model["file_path"])
    return {"ok": True}


async def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name not in TOOLS:
        raise SasaahError("csi_error", f"Unknown tool {name}.")
    if STATE.pop_fault(name, {"crash_during_call"}):
        os._exit(1)  # B-123: a crashing server must die without cleanup
    if STATE.pop_fault(name, {"com_worker_recycled"}):
        raise SasaahError("com_worker_recycled", "The call never started: the worker was recycled.")
    if STATE.target is not None and not STATE.session_valid:
        STATE.target["launched"] = False  # a re-attached session is treated as a user instance
        STATE.session_valid = True
    props = TOOLS[name].get("properties", {})
    if name in ("csi_status", "csi_attach", "csi_launch", "csi_detach"):
        return _session(name, args)
    if STATE.target is None:
        raise SasaahError("no_target", "No CSI instance is attached.")
    if "confirm" in props and not args.get("confirm"):
        raise SasaahError("confirmation_required", f"{name} requires confirm=true.")
    if name in NEEDS_LAUNCHED and not STATE.target["launched"]:
        raise SasaahError("not_launched_by_server", "The instance was not launched by this server.")
    if KINDS[name] in WRITE_KINDS and name not in LOCK_EXEMPT and STATE.model["locked"]:
        raise SasaahError("model_locked", "The model is locked after analysis.")
    if STATE.pop_fault(name, {"timeout_before_apply"}):  # any call can time out, a read included (S-12 section 5)
        raise _timeout()
    if name == "csi_run_analysis" and (slow := STATE.pop_fault(name, {"slow_analysis"})):
        await asyncio.sleep(float(slow.get("seconds", 1.0)))
    previous = STATE.model["units"]
    requested = args.get("units") if "units" in props else None
    leave = bool(requested) and STATE.pop_fault(name, {"units_left_changed"}) is not None
    if requested:
        STATE.model["units"] = requested
    result = _session(name, args) if name == "csi_exit" else _apply(name, args, STATE.model["units"])
    if requested and not leave:
        STATE.model["units"] = previous
    if STATE.pop_fault(name, {"timeout_after_apply"}):
        raise _timeout()
    return result


def _reply(body: dict[str, Any], *, error: bool) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(body))], is_error=error)


async def on_list_tools(
    ctx: ServerRequestContext[Any], params: types.PaginatedRequestParams | None
) -> types.ListToolsResult:
    """Serve the tool list generated from ``schemas.json``."""
    return types.ListToolsResult(tools=[types.Tool(name=n, input_schema=s) for n, s in TOOLS.items()])


async def on_call_tool(ctx: ServerRequestContext[Any], params: types.CallToolRequestParams) -> types.CallToolResult:
    """Run one tool and answer in the Sasaah reply shape."""
    try:
        return _reply(await _call(params.name, dict(params.arguments or {})), error=False)
    except SasaahError as error:
        return _reply({"code": error.code, "message": str(error), "data": error.data}, error=True)


async def main() -> None:
    """Serve over stdio until the client closes the pipe."""
    server: Server[Any] = Server("sasaah-csi-fake", on_list_tools=on_list_tools, on_call_tool=on_call_tool)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
