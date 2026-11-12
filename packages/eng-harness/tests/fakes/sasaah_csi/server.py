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
PID = 4242  # the first launched instance; each later csi_launch gets the next pid (a restore needs a distinct one)
_NEXT_PID = PID
KINDS: dict[str, str] = {t["name"]: t["server_kind"] for t in SCHEMAS["tools"]}  # S-12 inventory `server_kind`
WRITE_KINDS = {"Write", "Destructive"}  # S-12 report section 7: these raise model_locked while the model is locked
LOCK_EXEMPT = {"csi_unlock_model", "csi_save_model", "csi_run_analysis", "csi_design_run"}  # S-12 report section 7
LENGTH_M = {"kN_mm_C": 0.001, "kN_m_C": 1.0}  # metres per length unit of a token (S-12 report, section 4)
COMBO_NAMES = ("Linear Add", "Envelope", "Absolute Add", "SRSS")  # the schema's combo_type codes 0 to 3
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
        self.model.update(units=DEFAULT_UNITS, locked=False, model_path=None, tables={})
        self.resting = DEFAULT_UNITS  # the units the model shows between calls: the tables are read in these
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


def _launch_pid(*, fresh: bool) -> int:
    """The next pid, starting at 4242.

    A launch whose current target is some other pid (an attach) keeps answering 4242. A launch with no target, and a
    launch of the instance this server last started, takes the next pid so a restore can see a distinct instance.
    """
    global _NEXT_PID
    if not fresh and STATE.target is not None and STATE.target.get("pid") != _NEXT_PID - 1:
        return PID
    pid = _NEXT_PID
    _NEXT_PID += 1
    return pid


def _session(name: str, args: dict[str, Any], *, fresh: bool = False) -> dict[str, Any]:
    if name == "csi_status":
        return {"read_only": False, "script_enabled": False, "instances": [], "current_target": STATE.target}
    if name == "csi_launch":
        STATE.target = {"product": args.get("product", "ETABS"), "pid": _launch_pid(fresh=fresh), "launched": True}
        STATE.session_valid = True
        return dict(STATE.target)
    if name == "csi_attach":
        STATE.target = {"product": args.get("product", "ETABS"), "pid": args.get("pid", PID), "launched": False}
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


def _put(table: str, keys: tuple[str, ...], row: dict[str, Any]) -> None:
    """Replace the row of ``table`` with the same ``keys`` values, else append (a write is idempotent per object)."""
    rows: list[dict[str, Any]] = STATE.model["tables"].setdefault(table, [])
    rows[:] = [r for r in rows if any(r.get(k) != row[k] for k in keys)]
    rows.append(row)


def _find(kind: str, name: object) -> dict[str, Any]:
    for row in STATE.model[kind]:
        if row.get("name") == name:
            return row  # type: ignore[no-any-return]
    raise SasaahError("not_found", f"No {kind[:-1]} named {name}.")


def _edit(name: str, args: dict[str, Any], units: str) -> bool:
    """Apply an edit tool of spec 0002 section 4.6.2 to the model and its tables; False for any other tool."""
    a = args
    if name == "csi_assign_frame_section":
        _find("frames", a["name"])["section"] = a["section"]
    elif name == "csi_assign_area_section":
        _find("areas", a["name"])["section"] = a["section"]
        _put(
            "Area Assignments - Section Properties", ("UniqueName",), {"UniqueName": a["name"], "Section": a["section"]}
        )
    elif name == "csi_define_wall_section":
        thickness = float(a["thickness"]) * LENGTH_M[units] / LENGTH_M[STATE.resting]  # tables show the resting units
        row = {"Name": a["name"], "Material": a["material"], "Thickness": thickness}
        _put("Wall Property Definitions - Specified", ("Name",), row)
    elif name in ("csi_set_frame_load_distributed", "csi_set_area_load_uniform"):
        frame = name == "csi_set_frame_load_distributed"
        table = "Frame Loads Assignments - Distributed" if frame else "Area Load Assignments - Uniform"
        key = "Frame" if frame else "UniqueName"
        row = {key: a["name"], "LoadPattern": a["load_pattern"], "Value": a["value"]}
        _put(table, (key, "LoadPattern"), row)
    elif name == "csi_set_point_restraint":
        flags = dict(zip(("Ux", "Uy", "Uz", "Rx", "Ry", "Rz"), a["values"], strict=True))
        _put("Joint Assignments - Restraints", ("UniqueName",), {"UniqueName": a["name"], **flags})
    else:
        return False
    return True


def _add(kind: str, args: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = STATE.model[kind]
    name = args.get("name") or f"{kind[:-1]}{len(items) + 1}"
    row = {**{k: v for k, v in args.items() if k not in ("units", "target", "dry_run")}, "name": name}
    if kind == "load_combos":  # store the list-reply shape (type, items), not the tool's arguments
        row = {"name": name, "type": args.get("combo_type", 0), "items": list(args.get("components") or [])}
    items[:] = [r for r in items if r["name"] != name]  # a combination is replaced, not duplicated (S-12 section 2)
    items.append(row)
    if kind == "load_patterns":
        table = {"Name": name, "Type": args.get("type", "Dead"), "SelfWtMultpl": args.get("self_weight", 0)}
        _put("Load Pattern Definitions", ("Name",), table)
    elif kind == "load_combos":
        _put("Load Combination Definitions", ("Name",), {"Name": name, "Type": COMBO_NAMES[row["type"]]})
    return {"name": name}


def _list(kind: str, args: dict[str, Any], units: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = STATE.model[kind]
    limit = int(args.get("limit") or DEFAULT_LIMIT)
    return {"count": min(len(items), limit), "items": items[:limit], "truncated": len(items) > limit, "units": units}


def _apply(name: str, args: dict[str, Any], units: str) -> dict[str, Any]:
    model = STATE.model
    if name == "csi_model_info":
        counts = {kind: len(model[kind]) for kind in COLLECTIONS}
        return {
            "units": model["units"],
            "locked": model["locked"],
            "model_path": model["model_path"],
            "object_counts": counts,
            "counts": counts,
            "program_version": "22.0.0",
        }
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
    if _edit(name, args, units):
        return {"ok": True}
    if name == "csi_delete_load_combo":
        model["load_combos"] = [c for c in model["load_combos"] if c["name"] != args.get("name")]
        defs = model["tables"].get("Load Combination Definitions", [])
        model["tables"]["Load Combination Definitions"] = [r for r in defs if r["Name"] != args.get("name")]
    elif name == "csi_run_analysis":
        model["locked"] = True
    elif name == "csi_unlock_model":
        model["locked"] = False
    elif name == "csi_open_model":
        model["model_path"] = args.get("path", model["model_path"])
    elif name == "csi_save_model":
        model["model_path"] = args.get("path", model["model_path"])
        saved = model["model_path"]
        if isinstance(saved, str) and Path(saved).is_file():  # a real save changes the bytes (spec 0002 section 4.5.7)
            with Path(saved).open("ab") as handle:
                handle.write(b"\n")
    return {"ok": True}


async def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name not in TOOLS:
        raise SasaahError("csi_error", f"Unknown tool {name}.")
    if STATE.pop_fault(name, {"crash_during_call"}):
        os._exit(1)  # B-123: a crashing server must die without cleanup
    if STATE.pop_fault(name, {"com_worker_recycled"}):
        raise SasaahError("com_worker_recycled", "The call never started: the worker was recycled.")
    target = STATE.target
    fresh = target is not None and not STATE.session_valid
    if target is not None and fresh:
        target["launched"] = False  # a re-attached session is treated as a user instance
        STATE.session_valid = True
    props = TOOLS[name].get("properties", {})
    if name in ("csi_status", "csi_attach", "csi_launch", "csi_detach"):
        return _session(name, args, fresh=fresh)
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
    STATE.resting = previous
    requested = args.get("units") if "units" in props else None
    leave = bool(requested) and STATE.pop_fault(name, {"units_left_changed"}) is not None
    if requested:
        STATE.model["units"] = requested
    result = _session(name, args, fresh=fresh) if name == "csi_exit" else _apply(name, args, STATE.model["units"])
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


def _note(name: str, args: dict[str, Any]) -> None:
    """Record the call, and a launch's pid, without dropping faults already in the control file."""
    if not CONTROL:
        return
    path = Path(CONTROL)
    data = json.loads(path.read_text()) if path.is_file() else {}
    if not isinstance(data, dict):
        return
    pid = STATE.target["pid"] if STATE.target is not None else None
    entry: dict[str, Any] = {"tool": name, "pid": pid, "path": args.get("path")}
    if name == "csi_launch" and isinstance(pid, int):
        entry["visible"] = bool(args.get("visible", False))
        launched = data.get("launched")
        data["launched"] = [*launched, pid] if isinstance(launched, list) else [pid]
    calls = data.get("calls")
    data["calls"] = [*calls, entry] if isinstance(calls, list) else [entry]
    path.write_text(json.dumps(data))


async def on_call_tool(ctx: ServerRequestContext[Any], params: types.CallToolRequestParams) -> types.CallToolResult:
    """Run one tool and answer in the Sasaah reply shape."""
    args = dict(params.arguments or {})
    try:
        return _reply(await _call(params.name, args), error=False)
    except SasaahError as error:
        return _reply({"code": error.code, "message": str(error), "data": error.data}, error=True)
    finally:
        _note(params.name, args)  # os._exit on crash_during_call skips this, so that fault is not recorded as a call


async def main() -> None:
    """Serve over stdio until the client closes the pipe."""
    server: Server[Any] = Server("sasaah-csi-fake", on_list_tools=on_list_tools, on_call_tool=on_call_tool)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
