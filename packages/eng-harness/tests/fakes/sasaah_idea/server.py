"""Synthetic Sasaah IDEA MCP server: a test double, never packaged (spec 0014 section 4.12, lead decision D-5).

Run as a script over stdio. Tool schemas come from ``schemas.json`` (the 9 served tools plus ``idea_run_script``,
listed unless ``--disable-script`` is passed or the ``script_enabled`` fault enables listing). Replies follow the
Sasaah shape: one JSON text block, and ``isError`` with ``{code, message, data}`` on failure.

Native loads and saves read and write a ``.ideaCon``-like JSON file through a temporary file and atomic ``os.replace``.
Calculations return synthetic checks from a deterministic **non-engineering** formula:

- ``Plates``: ``25.0 + (sum(|forces|) / 1000.0) % 70.0`` (percent, always in ``[25.0, 95.0)``)
- ``Bolts``: ``15.0 + (sum(|forces|) / 2000.0) % 70.0`` (percent, always in ``[15.0, 85.0)``)

Faults come from the JSON control file named by ``SASAAH_IDEA_FAKE_CONTROL``:
``service_stopped``, ``live_create_fallback``, ``license_refused``, ``license_hang``, ``timeout_calculate``,
``timeout_set_loads`` (``applied`` bool, default true; optional ``mismatch`` bool), ``unexpected_shape``,
``errors_in_reply``, ``all_zero_loads``, ``passed_disagrees``, ``zero_utilization_true``, ``script_enabled``,
``read_only_listed_wrong``, ``zero_connections_calculated``, and ``crash_during_call``.
"""

import asyncio
import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from mcp import types
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server

SCHEMAS = json.loads((Path(__file__).resolve().parent / "schemas.json").read_text(encoding="utf-8"))
TOOLS: dict[str, dict[str, Any]] = {t["name"]: t["input_schema"] for t in SCHEMAS["tools"]}
KINDS: dict[str, str] = {t["name"]: t["server_kind"] for t in SCHEMAS["tools"]}
SCRIPT_TOOL = "idea_run_script"
FORCE_KEYS = ("n", "qy", "qz", "mx", "my", "mz")
CONTROL = os.environ.get("SASAAH_IDEA_FAKE_CONTROL")
DEFAULT_LIMIT = 500
DEFAULT_INSTALLED: list[dict[str, Any]] = [{"version": "24.1", "has_rest_api": True, "hidden_calculator": True}]
DEFAULT_SERVICE: dict[str, Any] = {"reachable": True, "service_version": "24.1.0"}
CALC_FAULTS = {
    "zero_connections_calculated",
    "errors_in_reply",
    "zero_utilization_true",
    "passed_disagrees",
}


class SasaahError(Exception):
    """A Sasaah error reply ``{code, message, data}``."""

    def __init__(self, code: str, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data or {}


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


class State:
    """In-memory project state and control-file fault dispatcher for the IDEA fake."""

    def __init__(self) -> None:
        control = _read_control()
        seed = control.get("seed", {})
        self.installed: list[dict[str, Any]] = list(seed.get("installed", DEFAULT_INSTALLED))
        self.service: dict[str, Any] = dict(seed.get("service", DEFAULT_SERVICE))
        self.disable_script: bool = "--disable-script" in sys.argv
        self.read_only: bool = "--read-only" in sys.argv
        self.project: dict[str, Any] | None = None

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

    def has_fault(self, kind: str, *, tool: str | None = None) -> dict[str, Any] | None:
        """Return the first matching pending fault without removing it."""
        for entry in _read_control().get("faults", []):
            if entry["fault"] == kind and (tool is None or entry.get("tool") == tool):
                return dict(entry)
        return None


STATE = State()


def _read_ideacon(path_value: Any) -> dict[str, Any]:
    if not isinstance(path_value, str) or not path_value:
        raise SasaahError("idea_error", "Project file path is required.")
    path = Path(path_value)
    if not path.is_file():
        raise SasaahError("idea_error", f"Project file not found: {path_value}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SasaahError("iom_error", f"Failed to read .ideaCon file: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("connections"), list):
        raise SasaahError("iom_error", "Invalid .ideaCon file: missing connections list.")
    return data


def _write_ideacon_atomic(path_value: str, data: dict[str, Any]) -> None:
    target = Path(path_value)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent, prefix=".idea_", suffix=".tmp", delete=False
        ) as handle:
            tmp_path = handle.name
            handle.write(json.dumps(data, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    except Exception:
        if tmp_path is not None and Path(tmp_path).exists():
            Path(tmp_path).unlink(missing_ok=True)
        raise


def _select_connections(
    connections: list[dict[str, Any]], connection_id: Any, *, allow_all: bool
) -> list[dict[str, Any]]:
    if connection_id is None:
        if allow_all or len(connections) == 1:
            return connections
        raise SasaahError("idea_error", "connection_id is required when the project has multiple connections.")
    matches = [c for c in connections if str(c.get("id")) == str(connection_id) or c.get("name") == connection_id]
    if not matches:
        raise SasaahError("connection_not_found", f"Connection {connection_id!r} was not found.")
    return matches


def _is_zero_effect(effect: dict[str, Any]) -> bool:
    segments = [*(effect.get("forcesOnSegments") or []), *(effect.get("forcesPercentageOnSegments") or [])]
    if not segments:
        return True
    return all(float(seg.get(key, 0.0)) == 0.0 for seg in segments for key in FORCE_KEYS)


def _deterministic_checks(conn: dict[str, Any]) -> list[dict[str, Any]]:
    """Compute synthetic non-engineering checks from the connection's load effects."""
    if isinstance(conn.get("checks"), list) and conn["checks"]:
        return [dict(c) for c in conn["checks"]]
    total = 0.0
    case_id: str | None = None
    for effect in conn.get("loads") or []:
        if case_id is None and effect.get("name"):
            case_id = str(effect["name"])
        for seg in effect.get("forcesOnSegments") or []:
            total += sum(abs(float(seg.get(k, 0.0))) for k in FORCE_KEYS)
    plates_val = round(25.0 + (total / 1000.0) % 70.0, 2)
    bolts_val = round(15.0 + (total / 2000.0) % 70.0, 2)
    return [
        {
            "name": "Plates",
            "check_value": plates_val,
            "check_status": True,
            "skipped": False,
            "message": "OK",
            "load_case_id": case_id,
        },
        {
            "name": "Bolts",
            "check_value": bolts_val,
            "check_status": True,
            "skipped": False,
            "message": "OK",
            "load_case_id": case_id,
        },
    ]


def _stub_reply(connections: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return Sasaah's deterministic offline stub summary (spec 0014 section 1 item 3, AC11)."""
    target = connections or [{"id": 1, "name": "CON1"}]
    stub_checks = [
        ("Plates", 35.0),
        ("Bolts", 42.0),
        ("Welds", 51.0),
        ("Buckling", 47.0),
        ("Concrete block", 10.0),
    ]
    return {
        "offline_stub": True,
        "backend": "file",
        "notice": "REST service unreachable; returning offline stub summary.",
        "connections": [
            {
                "connection_id": conn["id"],
                "name": conn["name"],
                "passed": True,
                "calculated": True,
                "checks": [
                    {
                        "name": name,
                        "check_value": value,
                        "check_status": True,
                        "skipped": False,
                        "message": "Offline stub.",
                        "unity_check_message": "Offline stub.",
                        "load_case_id": None,
                    }
                    for name, value in stub_checks
                ],
                "errors": [],
                "warnings": [],
            }
            for conn in target
        ],
    }


def _apply_calc_faults(tool: str, rows: list[dict[str, Any]], fault: dict[str, Any] | None) -> list[dict[str, Any]]:
    if fault is None:
        return rows
    kind = fault["fault"]
    out = copy.deepcopy(rows)
    if kind == "zero_connections_calculated":
        for row in out:
            row.update(calculated=False, passed=False, checks=[], errors=[], warnings=[])
        return out
    if kind == "errors_in_reply":
        errors = list(fault.get("errors", ["CBFEM analysis failed: singular stiffness matrix."]))
        for row in out:
            row.update(calculated=True, passed=False, checks=[], errors=errors)
        return out
    if kind == "zero_utilization_true":
        for row in out:
            checks = row.get("checks") or []
            if checks:
                checks[0].update(check_value=0.0, check_status=True, skipped=False)
            else:
                row["checks"] = [
                    {
                        "name": "Plates",
                        "check_value": 0.0,
                        "check_status": True,
                        "skipped": False,
                        "message": "OK",
                        "load_case_id": None,
                    }
                ]
        return out
    if kind == "passed_disagrees":
        for row in out:
            row["passed"] = True
            checks = row.setdefault("checks", [])
            checks.append(
                {
                    "name": "Welds",
                    "check_value": 112.0,
                    "check_status": False,
                    "skipped": False,
                    "message": "Utilization exceeds 100%",
                    "load_case_id": None,
                }
            )
        return out
    return out


async def _check_license_faults(tool: str) -> None:
    if STATE.pop_fault(tool, {"license_refused"}):
        raise SasaahError("service_unavailable", "IDEA StatiCa service refused request: no license seat available.")
    if hang := STATE.pop_fault(tool, {"license_hang"}):
        await asyncio.sleep(float(hang.get("seconds", 30.0)))


def _unexpected(tool: str) -> dict[str, Any] | None:
    if fault := STATE.pop_fault(tool, {"unexpected_shape"}):
        reply = fault.get("reply")
        return dict(reply) if isinstance(reply, dict) else {"unexpected": True, "payload": "malformed"}
    return None


def _require_project() -> dict[str, Any]:
    if STATE.project is None:
        raise SasaahError("no_project", "No IDEA project is currently open.")
    return STATE.project


def _status_reply() -> dict[str, Any]:
    stopped = STATE.pop_fault("idea_status", {"service_stopped"}) is not None
    script_fault = STATE.pop_fault("idea_status", {"script_enabled"}) is not None
    ro_fault = STATE.pop_fault("idea_status", {"read_only_listed_wrong"}) is not None
    reachable = bool(STATE.service.get("reachable", True)) and not stopped
    service = {"reachable": reachable, "service_version": STATE.service.get("service_version") if reachable else None}
    current = (
        {
            "file_path": STATE.project["file_path"],
            "backend": STATE.project["backend"],
            "live_project": STATE.project["live_project"],
        }
        if STATE.project is not None
        else None
    )
    return {
        "installed": copy.deepcopy(STATE.installed),
        "service": service,
        "read_only": STATE.read_only or ro_fault,
        "script_enabled": (not STATE.disable_script) or script_fault,
        "current_project": current,
    }


def _open_project(args: dict[str, Any]) -> dict[str, Any]:
    path_str = str(args.get("path") or "")
    data = _read_ideacon(path_str)
    stopped = STATE.pop_fault("idea_open_project", {"service_stopped"}) is not None
    fallback = STATE.pop_fault("idea_open_project", {"live_create_fallback"}) is not None
    reachable = bool(STATE.service.get("reachable", True)) and not stopped
    live = reachable and not fallback
    backend = "rest" if live else "file"
    connections = [{"id": c["id"], "name": c["name"], "calculated": False} for c in data["connections"]]
    STATE.project = {
        "file_path": path_str,
        "backend": backend,
        "service_reachable": reachable,
        "live_project": live,
        "connections": connections,
        "raw_connections": copy.deepcopy(data["connections"]),
        "results": {},
    }
    return {
        "file_path": path_str,
        "backend": backend,
        "service_reachable": reachable,
        "live_project": live,
        "connections": copy.deepcopy(connections),
    }


def _list_connections(args: dict[str, Any]) -> dict[str, Any]:
    proj = _require_project()
    limit = int(args.get("limit") or DEFAULT_LIMIT)
    conns = proj["connections"]
    return {
        "file_path": proj["file_path"],
        "backend": proj["backend"],
        "service_reachable": proj["service_reachable"],
        "live_project": proj["live_project"],
        "connections": copy.deepcopy(conns[:limit]),
        "count": min(len(conns), limit),
        "truncated": len(conns) > limit,
    }


async def _rest_calculate(args: dict[str, Any]) -> dict[str, Any]:
    proj = _require_project()
    if STATE.read_only:
        raise SasaahError("read_only", "Server is running in read-only mode.")
    if not args.get("confirm"):
        raise SasaahError("confirmation_required", "idea_calculate requires confirm=true.")
    req_ids = args.get("connection_ids")
    conns_by_id = {c["id"]: c for c in proj["raw_connections"]}
    if req_ids is not None:
        for cid in req_ids:
            if cid not in conns_by_id:
                raise SasaahError("connection_not_found", f"Connection {cid!r} was not found.")
        selected = [conns_by_id[cid] for cid in req_ids]
    else:
        selected = list(proj["raw_connections"])
    await _check_license_faults("idea_calculate")
    if STATE.pop_fault("idea_calculate", {"timeout_calculate"}):
        raise SasaahError("timeout", "The call timed out.")
    stopped = STATE.pop_fault("idea_calculate", {"service_stopped", "live_create_fallback"}) is not None
    if stopped or not proj["live_project"] or not STATE.service.get("reachable", True):
        return _stub_reply(selected)
    if bad := _unexpected("idea_calculate"):
        return bad
    rows = [
        {
            "connection_id": c["id"],
            "name": c["name"],
            "passed": True,
            "calculated": True,
            "checks": _deterministic_checks(c),
            "errors": [],
            "warnings": [],
        }
        for c in selected
    ]
    fault = STATE.pop_fault("idea_calculate", CALC_FAULTS)
    rows = _apply_calc_faults("idea_calculate", rows, fault)
    if fault is None or fault["fault"] != "zero_connections_calculated":
        for row in rows:
            proj["results"][row["connection_id"]] = copy.deepcopy(row)
        for summary_conn in proj["connections"]:
            if summary_conn["id"] in proj["results"]:
                summary_conn["calculated"] = True
    return {"route": "rest", "backend": "rest", "offline_stub": False, "connections": rows}


async def _rest_get_check_results(args: dict[str, Any]) -> dict[str, Any]:
    proj = _require_project()
    cid = args.get("connection_id")
    conns_by_id = {c["id"]: c for c in proj["raw_connections"]}
    if cid is not None and cid not in conns_by_id:
        raise SasaahError("connection_not_found", f"Connection {cid!r} was not found.")
    selected = [conns_by_id[cid]] if cid is not None else list(proj["raw_connections"])
    await _check_license_faults("idea_get_check_results")
    stub_fault = STATE.pop_fault("idea_get_check_results", {"service_stopped", "live_create_fallback"}) is not None
    if stub_fault or not proj["live_project"]:
        return _stub_reply(selected)
    if bad := _unexpected("idea_get_check_results"):
        return bad
    rows = [
        copy.deepcopy(
            proj["results"].get(
                c["id"],
                {
                    "connection_id": c["id"],
                    "name": c["name"],
                    "passed": False,
                    "calculated": False,
                    "checks": [],
                    "errors": [],
                    "warnings": [],
                },
            )
        )
        for c in selected
    ]
    fault = STATE.pop_fault("idea_get_check_results", CALC_FAULTS)
    rows = _apply_calc_faults("idea_get_check_results", rows, fault)
    return {"route": "rest", "backend": proj["backend"], "offline_stub": False, "connections": rows}


async def _native_get_loads(args: dict[str, Any]) -> dict[str, Any]:
    await _check_license_faults("idea_native_get_loads")
    if bad := _unexpected("idea_native_get_loads"):
        return bad
    data = _read_ideacon(args.get("path"))
    selected = _select_connections(data["connections"], args.get("connection_id"), allow_all=True)
    if len(selected) == 1:
        conn = selected[0]
        return {
            "connection": conn["name"],
            "connection_id": conn["id"],
            "loads": copy.deepcopy(conn.get("loads", [])),
        }
    return {
        "connections": [
            {"connection": c["name"], "connection_id": c["id"], "loads": copy.deepcopy(c.get("loads", []))}
            for c in selected
        ]
    }


async def _native_set_loads(args: dict[str, Any]) -> dict[str, Any]:
    if STATE.read_only:
        raise SasaahError("read_only", "Server is running in read-only mode.")
    if not args.get("confirm"):
        raise SasaahError("confirmation_required", "idea_native_set_loads requires confirm=true.")
    await _check_license_faults("idea_native_set_loads")
    data = _read_ideacon(args.get("path"))
    conn = _select_connections(data["connections"], args.get("connection_id"), allow_all=False)[0]
    if STATE.pop_fault("idea_native_set_loads", {"all_zero_loads"}):
        raise SasaahError("idea_error", "All load effects are zero; IDEA rejects loading with no non-zero effects.")
    raw_loads = args.get("loads")
    if not isinstance(raw_loads, list) or not all(isinstance(e, dict) for e in raw_loads):
        raise SasaahError("idea_error", "loads must be a list of effect objects.")
    dropped_zero = [str(e.get("name") or e.get("id") or "") for e in raw_loads if _is_zero_effect(e)]
    kept = [copy.deepcopy(e) for e in raw_loads if not _is_zero_effect(e)]
    if not kept:
        raise SasaahError("idea_error", "All load effects are zero; IDEA rejects loading with no non-zero effects.")
    timeout_fault = STATE.pop_fault("idea_native_set_loads", {"timeout_set_loads"})
    if timeout_fault is not None and not timeout_fault.get("applied", True):
        raise SasaahError("timeout", "The call timed out.")
    if timeout_fault is not None and timeout_fault.get("mismatch"):
        for seg in kept[0].get("forcesOnSegments") or []:
            seg["n"] = float(seg.get("n", 0.0)) + 1.0
            break
    conn["loads"] = kept
    target_path = str(args.get("out_path") or args["path"])
    _write_ideacon_atomic(target_path, data)
    if timeout_fault is not None:
        raise SasaahError("timeout", "The call timed out.")
    if bad := _unexpected("idea_native_set_loads"):
        return bad
    return {
        "connection": conn["name"],
        "connection_id": conn["id"],
        "out_path": target_path,
        "effects_written": len(kept),
        "dropped_zero": dropped_zero,
    }


async def _native_calculate(args: dict[str, Any]) -> dict[str, Any]:
    if args.get("save") and not args.get("confirm"):
        raise SasaahError("confirmation_required", "idea_native_calculate requires confirm=true when save=true.")
    await _check_license_faults("idea_native_calculate")
    if STATE.pop_fault("idea_native_calculate", {"timeout_calculate"}):
        raise SasaahError("timeout", "The call timed out.")
    data = _read_ideacon(args.get("path"))
    selected = _select_connections(data["connections"], args.get("connection_id"), allow_all=True)
    if bad := _unexpected("idea_native_calculate"):
        return bad
    rows = [
        {
            "connection_id": c["id"],
            "name": c["name"],
            "passed": True,
            "calculated": True,
            "checks": _deterministic_checks(c),
            "errors": [],
            "warnings": [],
        }
        for c in selected
    ]
    fault = STATE.pop_fault("idea_native_calculate", CALC_FAULTS)
    rows = _apply_calc_faults("idea_native_calculate", rows, fault)
    if args.get("save") and (fault is None or fault["fault"] != "zero_connections_calculated"):
        by_id = {row["connection_id"]: row for row in rows}
        for conn in data["connections"]:
            if conn["id"] in by_id:
                conn["calculated"] = True
                conn["checks"] = by_id[conn["id"]]["checks"]
        _write_ideacon_atomic(str(args.get("out_path") or args["path"]), data)
    return {"route": "native", "backend": None, "offline_stub": False, "connections": rows}


async def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name not in TOOLS:
        raise SasaahError("idea_error", f"Unknown tool {name}.")
    if STATE.pop_fault(name, {"crash_during_call"}):
        os._exit(1)
    if name == "idea_status":
        await _check_license_faults(name)
        return _unexpected(name) or _status_reply()
    if name == "idea_open_project":
        await _check_license_faults(name)
        return _unexpected(name) or _open_project(args)
    if name == "idea_close_project":
        STATE.project = None
        return _unexpected(name) or {"closed": True}
    if name == "idea_list_connections":
        _require_project()
        return _unexpected(name) or _list_connections(args)
    if name == "idea_calculate":
        return await _rest_calculate(args)
    if name == "idea_get_check_results":
        return await _rest_get_check_results(args)
    if name == "idea_native_get_loads":
        return await _native_get_loads(args)
    if name == "idea_native_set_loads":
        return await _native_set_loads(args)
    if name == "idea_native_calculate":
        return await _native_calculate(args)
    if name == SCRIPT_TOOL:
        if STATE.disable_script:
            raise SasaahError("script_disabled", "C# scripting is disabled (--disable-script).")
        if STATE.read_only:
            raise SasaahError("read_only", "Server is running in read-only mode.")
        return {"executed": True}
    raise SasaahError("idea_error", f"Unhandled tool {name}.")


def _reply(body: dict[str, Any], *, error: bool) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(body))], is_error=error)


def _listed_tools() -> list[types.Tool]:
    control = _read_control()
    script_fault = STATE.has_fault("script_enabled")
    include_script = (
        not STATE.disable_script
        or bool(control.get("list_run_script"))
        or (script_fault is not None and (bool(script_fault.get("listed")) or script_fault.get("tool") == "tools/list"))
    )
    ro_fault = STATE.has_fault("read_only_listed_wrong")
    omit = set(control.get("omit_tools", []))
    if ro_fault and ro_fault.get("omit_tool"):
        omit.add(str(ro_fault["omit_tool"]))
    tools: list[types.Tool] = []
    for name, schema in TOOLS.items():
        if name in omit:
            continue
        if name == SCRIPT_TOOL and not include_script:
            continue
        if STATE.read_only and KINDS[name] in ("Destructive", "Code"):
            continue
        tools.append(types.Tool(name=name, input_schema=schema))
    return tools


async def on_list_tools(
    ctx: ServerRequestContext[Any], params: types.PaginatedRequestParams | None
) -> types.ListToolsResult:
    """Serve the tool list generated from ``schemas.json``."""
    return types.ListToolsResult(tools=_listed_tools())


def _note(name: str, args: dict[str, Any]) -> None:
    if not CONTROL:
        return
    data = _read_control()
    entry = {"tool": name, "args_keys": sorted(args)}
    calls = data.get("calls")
    data["calls"] = [*calls, entry] if isinstance(calls, list) else [entry]
    _write_control(data)


async def on_call_tool(ctx: ServerRequestContext[Any], params: types.CallToolRequestParams) -> types.CallToolResult:
    """Run one tool and answer in the Sasaah reply shape."""
    args = dict(params.arguments or {})
    try:
        return _reply(await _call(params.name, args), error=False)
    except SasaahError as error:
        return _reply({"code": error.code, "message": str(error), "data": error.data}, error=True)
    finally:
        _note(params.name, args)


async def main() -> None:
    """Serve over stdio until the client closes the pipe."""
    server: Server[Any] = Server("sasaah-idea-fake", on_list_tools=on_list_tools, on_call_tool=on_call_tool)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
