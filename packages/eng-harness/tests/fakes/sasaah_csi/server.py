"""Synthetic Sasaah CSI MCP server: a test double, never packaged (spec 0002 section 4.8.3, lead decision D-5).

Run as a script over stdio. The tool list is generated from ``schemas.json`` (a copy of the S-12 inventory's names and
input schemas for the non-excluded tools). Replies follow the Sasaah shape: one JSON text block, and ``isError`` with
``{code, message, data}`` on failure. State is in memory. Faults come from the JSON control file named by the
environment variable ``SASAAH_CSI_FAKE_CONTROL``::

    {"faults": [{"fault": "timeout_before_apply", "tool": "csi_add_point"}], "seed": {"points": [...], "tables": {...}}}

A fault fires once and is removed from the file. Faults: ``timeout_before_apply``, ``timeout_after_apply``,
``crash_during_call``, ``units_left_changed``, ``slow_analysis`` (optional ``seconds``) and ``com_worker_recycled``.
Units are the Sasaah tokens of the S-12 report (section 4); the fake invents no engineering value.

Product modes (control ``product`` or launch/attach argument): ETABS (default), SAFE (spec 0008) and SAP2000
(spec 0012 §4.1: gap tools return ``unsupported_by_version``, frame replies omit ``label`` and ``story``, added
frames are renamed, a blank model has no sections).
"""

import asyncio
import json
import os
import sys
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
RESULTS = (
    "csi_results_base_reactions",
    "csi_results_joint_reactions",
    "csi_results_frame_forces",
    "csi_results_story_drifts",
)
COMBO_NAMES = ("Linear Add", "Envelope", "Absolute Add", "SRSS")  # the schema's combo_type codes 0 to 3
NEEDS_LAUNCHED = {"csi_open_model", "csi_new_model", "csi_new_blank_model", "csi_exit"}
COLLECTIONS = (
    "stories", "grids", "points", "frames", "areas", "materials", "frame_sections", "area_sections",
    "load_patterns", "load_cases", "load_combos",
)  # fmt: skip
# Spec 0012 §4.1 gaps: the server answers unsupported_by_version (status `gap`).
SAP2000_UNSUPPORTED = frozenset(
    {
        "csi_list_stories",
        "csi_list_grids",
        "csi_frame_details",
        "csi_export_joint",
        "csi_results_story_drifts",
        "csi_new_model",
    }
)


class SasaahError(Exception):
    """A Sasaah error reply ``{code, message, data}``."""

    def __init__(self, code: str, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data or {}


class State:
    """The in-memory model and session of the fake."""

    def __init__(self) -> None:
        control = json.loads(Path(CONTROL).read_text()) if CONTROL else {}
        self.product = control.get("product", "ETABS")
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


def _flag(name: str) -> Any:
    """A flag of the host program (`locked`, `analyzed`, `designed`): every server of a run sees the same one.

    The host is one process, so the servers of its roles share these flags through the control file; without one the
    flag is the in-memory value.
    """
    if CONTROL:
        shared = json.loads(Path(CONTROL).read_text()).get("host", {})
        if name in shared:
            return shared[name]
    return STATE.model.get(name)


def _set_flag(name: str, value: Any) -> None:
    STATE.model[name] = value
    if CONTROL:
        path = Path(CONTROL)
        data = json.loads(path.read_text())
        data.setdefault("host", {})[name] = value
        path.write_text(json.dumps(data))


def _timeout() -> SasaahError:
    STATE.session_valid = False  # the cached session is invalidated (S-12 section 5)
    return SasaahError("timeout", "The call timed out.")


def _launch_pid(*, fresh: bool) -> int:
    """The next pid, starting at 4242.

    A launch whose current target is some other pid (an attach) keeps answering 4242. A launch with no target, and a
    launch of the instance this server last started, takes the next pid so a restore can see a distinct instance.
    """
    global _NEXT_PID
    if CONTROL:
        data = json.loads(Path(CONTROL).read_text())
        if data.get("persist_model"):
            return int(max(data.get("launched", [PID - 1]))) + 1
    if not fresh and STATE.target is not None and STATE.target.get("pid") != _NEXT_PID - 1:
        return PID
    pid = _NEXT_PID
    _NEXT_PID += 1
    return pid


def _session(name: str, args: dict[str, Any], *, fresh: bool = False) -> dict[str, Any]:
    if name == "csi_status":
        return {"read_only": False, "script_enabled": False, "instances": [], "current_target": STATE.target}
    if name == "csi_launch":
        STATE.target = {
            "product": args.get("product") or STATE.product,
            "pid": _launch_pid(fresh=fresh),
            "launched": True,
        }
        STATE.session_valid = True
        return dict(STATE.target)
    if name == "csi_attach":
        override = args.get("target")
        target = override if isinstance(override, dict) else {}
        STATE.target = {
            "product": target.get("product") or args.get("product") or STATE.product,
            "pid": target.get("pid") or args.get("pid") or PID,
            "launched": False,
        }
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
    rows: list[dict[str, Any]] = STATE.model[kind]
    for row in rows:
        if row.get("name") == name:
            return row
    raise SasaahError("not_found", f"No {kind[:-1]} named {name}.")


def _edit(name: str, args: dict[str, Any], units: str) -> bool:
    """Apply an edit tool of spec 0002 section 4.6.2 to the model and its tables; False for any other tool."""
    a = args
    if name == "csi_set_point_load":
        _find("points", a["name"])
        table = "Joint Loads Assignments - Force"
        keys = ("UniqueName", "LoadPattern")
        old: dict[str, Any] = next(
            (
                r
                for r in STATE.model["tables"].get(table, [])
                if r.get("UniqueName") == a["name"] and r.get("LoadPattern") == a["load_pattern"]
            ),
            {},
        )
        # Always keep XDim/YDim columns (SAFE field map requires them); preserve prior values when Replace.
        row: dict[str, Any] = {"XDim": old.get("XDim"), "YDim": old.get("YDim")}
        row.update(UniqueName=a["name"], LoadPattern=a["load_pattern"])
        moments = [value * LENGTH_M[units] / LENGTH_M[STATE.resting] for value in a["moment"]]
        row.update(zip(("FX", "FY", "FZ", "MX", "MY", "MZ"), [*a["force"], *moments], strict=True))
        rows = STATE.model["tables"].setdefault(table, [])
        rows[:] = [r for r in rows if any(r.get(k) != row[k] for k in keys)]
        if any([*a["force"], *a["moment"]]):
            rows.append(row)
    elif name == "csi_assign_frame_section":
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


def _add(kind: str, args: dict[str, Any], product: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = STATE.model[kind]
    # Spec 0012 §4.1 serve-diff: SAP2000 AddByCoord ignores the requested name (evidence L).
    if kind == "frames" and product == "SAP2000":
        name = f"Frame{len(items) + 1}"
    else:
        name = args.get("name") or f"{kind[:-1]}{len(items) + 1}"
    skip = {"units", "target", "dry_run"}
    if kind == "frames" and product == "SAP2000":
        skip = skip | {"label", "story", "name"}
    row = {**{k: v for k, v in args.items() if k not in skip}, "name": name}
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


def _list(kind: str, args: dict[str, Any], units: str, product: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = STATE.model[kind]
    limit = int(args.get("limit") or DEFAULT_LIMIT)
    page = items[:limit]
    # Spec 0012 §4.1 serve-diff: SAP2000 frame replies have no label or story.
    if kind == "frames" and product == "SAP2000":
        page = [{k: v for k, v in item.items() if k not in ("label", "story")} for item in page]
    return {"count": min(len(items), limit), "items": page, "truncated": len(items) > limit, "units": units}


def _analysis(name: str, args: dict[str, Any], units: str) -> dict[str, Any]:
    """Analysis, design and results tools of spec 0002 section 4.6.1; the seed supplies every result row.

    `csi_run_analysis` answers `{started: true}` only after it finished (S-12 section 5) and leaves the model locked.
    `csi_analysis_status` answers raw per-case codes (the test values 1 and 4 mean nothing: the server does not decode
    them). The results tools answer the seed's rows of the tool, `model["results"][tool]`, as seeded and not rescaled
    (the reply's `units` names the call's token; a test seeds the rows in the units it calls with);
    a design result needs a design run of its kind first (the tool's description).
    """
    model = STATE.model
    if name == "csi_run_analysis":
        _set_flag("locked", True)
        _set_flag("analyzed", True)
        return {"started": True}
    if name == "csi_analysis_status":
        code = 4 if _flag("analyzed") else 1
        return {"cases": [{"case": row["name"], "status_code": code} for row in model["load_cases"]]}
    if name in RESULTS:
        rows = model.get("results", {}).get(name, [])
        limit = int(model.get("result_limits", {}).get(name, args.get("limit") or DEFAULT_LIMIT))
        return {"items": rows[:limit], "count": min(len(rows), limit), "truncated": len(rows) > limit, "units": units}
    kind = args.get("kind")
    if name == "csi_design_run":
        if kind in ("aluminum", "coldformed"):  # the tool's description: SAFEv1 and ETABSv1 have no such designers
            raise SasaahError("unsupported_by_version", f"Design kind {kind} is not supported by this version.")
        _set_flag("designed", sorted({*(_flag("designed") or []), *([kind] if kind else [])}))
        return {"kind": kind, "completed": True}
    if kind not in (_flag("designed") or []):
        raise SasaahError("csi_error", f"No {kind} design results exist; run csi_design_run first.")
    rows = [r for r in model.get("design_results", {}).get(kind, []) if args.get("name") in (None, r.get("frame"))]
    limit = int(args.get("limit") or 500)
    return {"items": rows[:limit], "count": min(len(rows), limit), "truncated": len(rows) > limit}


def _in_group(row: dict[str, Any], group: str) -> bool:
    if row.get("Group") == group:
        return True
    groups = row.get("groups")
    return isinstance(groups, list | tuple | set) and group in groups


def _apply(name: str, args: dict[str, Any], units: str, product: str) -> dict[str, Any]:
    model = STATE.model
    if product == "SAP2000" and name in SAP2000_UNSUPPORTED:
        raise SasaahError("unsupported_by_version", f"{name} is not supported by this version.")
    if name == "csi_new_model" and product == "SAFE":
        raise SasaahError("unsupported_by_version", "Creating a model is not supported by this version.")
    if name == "csi_new_blank_model" and product == "SAP2000":
        # Spec 0012 §4.1 / SP-1: a blank SAP2000 model ships no sections (evidence L).
        model["frame_sections"] = []
        model["area_sections"] = []
        return {"ok": True}
    if name == "csi_db_table_fields":
        table = args.get("table")
        rows = model["tables"].get(table, [])
        fields = model.get("table_fields", {}).get(table, list(rows[0]) if rows else [])
        return {"fields": fields}
    if name == "csi_model_info":
        counts = {kind: len(model[kind]) for kind in COLLECTIONS}
        return {
            "units": model["units"],
            "locked": _flag("locked"),
            "model_path": model["model_path"],
            "object_counts": counts,
            "counts": counts,
            "program_version": "22.0.0",
        }
    if name in ("csi_run_analysis", "csi_analysis_status", "csi_design_run", "csi_design_results") or name in RESULTS:
        return _analysis(name, args, units)
    if name.startswith("csi_list_") and name[len("csi_list_") :] in COLLECTIONS:
        return _list(name[len("csi_list_") :], args, units, product)
    if name == "csi_db_table_read":
        table = args.get("table")
        rows = model["tables"].get(table, [])
        if group := args.get("group"):
            rows = [r for r in rows if _in_group(r, group)]
        configured = model.get("result_limits", {}).get(table)
        requested = args.get("row_limit")
        limit = (
            min(int(requested or DEFAULT_LIMIT), int(configured))
            if configured is not None
            else int(requested or DEFAULT_LIMIT)
        )
        return {"rows": rows[:limit], "truncated": len(rows) > limit}
    adds = {"csi_add_point": "points", "csi_add_frame_by_coord": "frames", "csi_add_area_by_coord": "areas"}
    adds.update(csi_add_load_pattern="load_patterns", csi_add_load_combo="load_combos")
    if name in adds:
        return _add(adds[name], args, product)
    if _edit(name, args, units):
        return {"ok": True}
    if name == "csi_delete_load_combo":
        model["load_combos"] = [c for c in model["load_combos"] if c["name"] != args.get("name")]
        defs = model["tables"].get("Load Combination Definitions", [])
        model["tables"]["Load Combination Definitions"] = [r for r in defs if r["Name"] != args.get("name")]
    elif name == "csi_unlock_model":
        _set_flag("locked", False)
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
    if KINDS[name] in WRITE_KINDS and name not in LOCK_EXEMPT and _flag("locked"):
        raise SasaahError("model_locked", "The model is locked after analysis.")
    if STATE.pop_fault(name, {"timeout_before_apply"}):  # any call can time out, a read included (S-12 section 5)
        raise _timeout()
    if name == "csi_run_analysis" and (slow := STATE.pop_fault(name, {"slow_analysis"})):
        await asyncio.sleep(float(slow.get("seconds", 1.0)))
    override = args.get("target")
    product = (override.get("product") if "target" in props and isinstance(override, dict) else None) or STATE.target[
        "product"
    ]
    if STATE.pop_fault(name, {"present_units_mm"}):
        STATE.model["units"] = "kN_mm_C"
    previous = STATE.model["units"]
    STATE.resting = previous
    requested = args.get("units") if "units" in props else None
    leave = bool(requested) and STATE.pop_fault(name, {"units_left_changed"}) is not None
    if requested:
        STATE.model["units"] = requested
    try:
        result = (
            _session(name, args, fresh=fresh)
            if name == "csi_exit"
            else _apply(name, args, STATE.model["units"], product)
        )
    finally:
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
    audit = sys.argv[sys.argv.index("--audit-log") + 1] if "--audit-log" in sys.argv else ""
    role = Path(audit).name.removesuffix("-audit.jsonl").rsplit("-", 1)[-1]
    entry: dict[str, Any] = {"tool": name, "pid": pid, "path": args.get("path"), "role": role}
    if name == "csi_launch":
        if "product" in args:
            entry["product"] = args["product"]
        if isinstance(pid, int):
            entry["visible"] = bool(args.get("visible", False))
            launched = data.get("launched")
            data["launched"] = [*launched, pid] if isinstance(launched, list) else [pid]
    if name == "csi_open_model" and "confirm" in args:
        entry["confirm"] = bool(args["confirm"])
    calls = data.get("calls")
    data["calls"] = [*calls, entry] if isinstance(calls, list) else [entry]
    path.write_text(json.dumps(data))


async def on_call_tool(ctx: ServerRequestContext[Any], params: types.CallToolRequestParams) -> types.CallToolResult:
    """Run one tool and answer in the Sasaah reply shape."""
    args = dict(params.arguments or {})
    if CONTROL:
        data = json.loads(Path(CONTROL).read_text())
        if data.get("persist_model") and "model" in data:
            STATE.model = data["model"]
    try:
        return _reply(await _call(params.name, args), error=False)
    except SasaahError as error:
        return _reply({"code": error.code, "message": str(error), "data": error.data}, error=True)
    finally:
        if CONTROL:
            path = Path(CONTROL)
            data = json.loads(path.read_text())
            if data.get("persist_model"):
                data["model"] = STATE.model
                path.write_text(json.dumps(data))
        _note(params.name, args)  # os._exit on crash_during_call skips this, so that fault is not recorded as a call


async def main() -> None:
    """Serve over stdio until the client closes the pipe."""
    server: Server[Any] = Server("sasaah-csi-fake", on_list_tools=on_list_tools, on_call_tool=on_call_tool)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
