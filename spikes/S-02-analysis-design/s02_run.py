#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["mcp>=2,<3"]
# ///
"""Spike S-02: analysis and design through sasaah-csi-mcp (19 section 2). Run by the owner on the ETABS machine.

    uv run --script s02_run.py --model <model.EDB> --server-exe <sasaah-csi-mcp.exe> [options]
    uv run --script s02_run.py --help
    uv run --script s02_run.py --model <model.EDB> --server-exe <exe> --dry-run

What it does (all on a COPY of the model that it makes inside the run folder; the original is only read, and its
SHA-256 is compared before and after):
  1. starts sasaah-csi-mcp over stdio (official MCP Python SDK), launches ETABS through it and opens the copy;
  2. times save, analysis and design over several runs (including save-before-run, and the unlock after analysis);
  3. checks that a write is refused while the model is locked (a dry-run call, so nothing changes) and that
     csi_unlock_model lifts it;
  4. starts a second server with a SHORT call timeout against the same ETABS and runs analysis (and optionally
     design) through it: records what the server returns, how long the first server then waits for the host, and the
     model state and units afterwards (the evidence for TIMEOUT_UNKNOWN_OUTCOME);
  5. watches the ETABS windows all the time (Windows only, read only: it never clicks or sends anything) and
     reports every dialog it sees.
Writes record.json (machine readable) and summary.md into the run folder. Nothing is a live result until the
owner has run it: everything here is "needs local test".

Tool names and arguments come from spikes/S-12-sasaah-tool-inventory/inventory/sasaah-csi-mcp.json. Escape-hatch
tools are refused by the code (FORBIDDEN_TOOLS) and never called. Spike code never ships.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime as dt
import hashlib
import json
import platform
import re
import shutil
import statistics
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SPIKE = "S-02"
SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------------------------------------------
# Tools this spike may call (names and arguments: S-12 inventory sasaah-csi-mcp.json).
# ---------------------------------------------------------------------------------------------------------------
ALLOWED_TOOLS = frozenset({
    "csi_status", "csi_launch", "csi_attach", "csi_detach", "csi_exit",
    "csi_open_model", "csi_save_model", "csi_model_info",
    "csi_run_analysis", "csi_design_run", "csi_analysis_status", "csi_unlock_model",
    "csi_add_point",  # only with dry_run=true, to probe model_locked without changing the model
})
FORBIDDEN_TOOLS = frozenset({  # S-12 classification "escape-hatch"; never callable from this code
    "csi_run_script", "csi_db_tables_apply", "csi_invoke", "csi_object_add", "csi_object_delete",
    "csi_object_set", "csi_object_get",
})
DESIGN_KINDS = ("concrete", "steel")  # csi_design_run kinds supported per S-12 report section 1 (step 12)
HOST_BUSY_THRESHOLD_S = 0.5  # spike heuristic (not an engineering value): extra wait that counts as "host still busy"
TIMEOUT_TEST_CHOICES = ("analysis", "design")

_clock: Callable[[], float] = time.perf_counter  # check.py replaces this with a fake clock


class ForbiddenTool(RuntimeError):
    pass


def guard_tool(tool: str, args: dict[str, Any]) -> None:
    if tool in FORBIDDEN_TOOLS:
        raise ForbiddenTool(f"{tool} is an escape-hatch tool and is never called")
    if tool not in ALLOWED_TOOLS:
        raise ForbiddenTool(f"{tool} is not in this spike's list of tools")
    if tool == "csi_add_point" and args.get("dry_run") is not True:
        raise ForbiddenTool("csi_add_point may only be called with dry_run=true")


# ---------------------------------------------------------------------------------------------------------------
# Replies and sessions
# ---------------------------------------------------------------------------------------------------------------
@dataclass
class Reply:
    tool: str
    ok: bool
    elapsed_s: float
    code: str | None = None  # server error code (csi_error, timeout, model_locked, ...) or client-side kind
    message: str | None = None
    payload: Any = None  # parsed JSON (dict for most tools), or None
    text: str = ""
    kind: str = "ok"  # ok | tool_error | protocol_error | client_timeout | exception


def parse_result(tool: str, result: Any, elapsed_s: float) -> Reply:
    """Turns an MCP CallToolResult into a Reply. The CSI server sends JSON text; errors carry {code, message, data}."""
    texts = [c.text for c in getattr(result, "content", []) if getattr(c, "type", None) == "text"]
    text = "\n".join(texts)
    payload: Any = None
    if text:
        with contextlib.suppress(ValueError):
            payload = json.loads(text)
    if getattr(result, "is_error", False):
        code = message = None
        if isinstance(payload, dict):
            code, message = payload.get("code"), payload.get("message")
        return Reply(tool, False, elapsed_s, code or "unknown_error", message or text[:300], payload, text, "tool_error")
    return Reply(tool, True, elapsed_s, None, None, payload, text)


class Session:
    """Base class: guard, time and never raise. Subclasses implement _call and close."""

    label = "?"
    synthetic = False

    async def call(self, tool: str, args: dict[str, Any] | None = None, timeout_s: float | None = None) -> Reply:
        args = dict(args or {})
        guard_tool(tool, args)
        t0 = _clock()
        try:
            reply = await self._call(tool, args, timeout_s)
        except ForbiddenTool:
            raise
        except TimeoutError as exc:
            reply = Reply(tool, False, 0.0, "client_timeout", str(exc), kind="client_timeout")
        except Exception as exc:  # noqa: BLE001 - the spike records every failure instead of stopping
            kind = "protocol_error" if type(exc).__name__ == "MCPError" else "exception"
            code = f"mcp_{getattr(exc, 'code', '')}" if kind == "protocol_error" else type(exc).__name__
            reply = Reply(tool, False, 0.0, code, str(exc)[:300], kind=kind)
        reply.elapsed_s = _clock() - t0
        return reply

    async def _call(self, tool: str, args: dict[str, Any], timeout_s: float | None) -> Reply:
        raise NotImplementedError

    async def list_tool_names(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class McpSession(Session):
    """A real stdio connection to sasaah-csi-mcp with the official MCP Python SDK (mcp 2.x: mcp.Client)."""

    def __init__(self, label: str, exe: str, args: list[str], stderr_path: Path, mode: str = "auto") -> None:
        self.label, self._exe, self._args, self._stderr_path, self._mode = label, exe, args, stderr_path, mode
        self._stack: contextlib.AsyncExitStack | None = None
        self._client: Any = None

    async def open(self) -> McpSession:
        from mcp import Client
        from mcp.client.stdio import StdioServerParameters, stdio_client

        self._stack = contextlib.AsyncExitStack()
        errlog = self._stack.enter_context(open(self._stderr_path, "w", encoding="utf-8"))  # noqa: SIM115
        params = StdioServerParameters(command=self._exe, args=self._args)
        client = Client(stdio_client(params, errlog=errlog), mode=self._mode)
        self._client = await self._stack.enter_async_context(client)
        return self

    async def _call(self, tool: str, args: dict[str, Any], timeout_s: float | None) -> Reply:
        result = await self._client.call_tool(tool, args or None, read_timeout_seconds=timeout_s)
        return parse_result(tool, result, 0.0)

    async def list_tool_names(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        cursor = None
        while True:
            page = await self._client.list_tools(cursor=cursor)
            out += [{"name": t.name, "input_schema": getattr(t, "input_schema", None)} for t in page.tools]
            cursor = getattr(page, "next_cursor", None)
            if not cursor:
                return out

    async def close(self) -> None:
        if self._stack is not None:
            with contextlib.suppress(Exception):
                await self._stack.aclose()
            self._stack = None


SessionFactory = Callable[[str, list[str]], Awaitable[Session]]


# ---------------------------------------------------------------------------------------------------------------
# Window probe: dialogs, detected and reported, never clicked. Read-only Win32 calls (EnumWindows and getters).
# ---------------------------------------------------------------------------------------------------------------
class WindowProbe:
    available = False
    note = "window probe not available on this platform"

    def snapshot(self, pids: set[int]) -> list[dict[str, Any]]:
        return []


class Win32WindowProbe(WindowProbe):
    available = True
    note = "Win32 EnumWindows, read only"

    def snapshot(self, pids: set[int]) -> list[dict[str, Any]]:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        found: list[dict[str, Any]] = []
        proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def visit(hwnd: Any, _lparam: Any) -> bool:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids and user32.IsWindowVisible(hwnd):
                title = ctypes.create_unicode_buffer(256)
                cls = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, title, 256)
                user32.GetClassNameW(hwnd, cls, 256)
                found.append({
                    "hwnd": int(hwnd), "title": title.value, "class": cls.value,
                    "enabled": bool(user32.IsWindowEnabled(hwnd)),
                    "has_owner": bool(user32.GetWindow(hwnd, 4)),  # GW_OWNER
                    "pid": pid.value,
                })
            return True

        user32.EnumWindows(proc_type(visit), 0)
        return found


def default_probe() -> WindowProbe:
    return Win32WindowProbe() if sys.platform == "win32" else WindowProbe()


def classify_windows(windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dialog = owned window or the standard dialog class. Modal suspected = a dialog exists and some non-dialog
    window of the program is disabled. Titles of non-dialog windows (which carry the model name) are not kept."""
    is_dialog = [w for w in windows if w.get("has_owner") or w.get("class") == "#32770"]
    others_disabled = any(not w.get("enabled", True) for w in windows if w not in is_dialog)
    return [
        {"title": w.get("title", ""), "class": w.get("class", ""), "hwnd": w.get("hwnd"),
         "enabled": w.get("enabled", True), "modal_suspected": others_disabled}
        for w in is_dialog
    ]


class DialogWatcher:
    def __init__(self, probe: WindowProbe, poll_s: float) -> None:
        self.probe, self.poll_s = probe, poll_s
        self.pids: set[int] = set()
        self.seen: dict[tuple[Any, str, str], dict[str, Any]] = {}
        self._phase = "setup"

    def _sample(self) -> None:
        if not self.pids:
            return
        now = _clock()
        for d in classify_windows(self.probe.snapshot(self.pids)):
            key = (d["hwnd"], d["title"], d["class"])
            rec = self.seen.setdefault(key, {**d, "first_seen_s": now, "phases": []})
            rec["last_seen_s"] = now
            rec["modal_suspected"] = rec["modal_suspected"] or d["modal_suspected"]
            if self._phase not in rec["phases"]:
                rec["phases"].append(self._phase)

    async def during(self, phase: str, coro: Awaitable[Reply]) -> Reply:
        self._phase = phase
        stop = asyncio.Event()

        async def loop() -> None:
            while not stop.is_set():
                await asyncio.to_thread(self._sample)
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), self.poll_s)

        task = asyncio.create_task(loop())
        try:
            return await coro
        finally:
            stop.set()
            await task
            await asyncio.to_thread(self._sample)

    def report(self) -> list[dict[str, Any]]:
        return sorted(self.seen.values(), key=lambda r: r["first_seen_s"])


def find_pids(node: Any) -> set[int]:
    out: set[int] = set()
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("pid", "process_id") and isinstance(v, int):
                out.add(v)
            else:
                out |= find_pids(v)
    elif isinstance(node, list):
        for v in node:
            out |= find_pids(v)
    return out


# ---------------------------------------------------------------------------------------------------------------
# Privacy: records keep base names, never full paths
# ---------------------------------------------------------------------------------------------------------------
_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|/)[^\s\"'<>|]*[\\/][^\s\"'<>|]+")


def scrub_text(s: str) -> str:
    return _PATH_RE.sub(lambda m: "<path>/" + re.split(r"[\\/]", m.group(0))[-1], s)


def scrub(node: Any) -> Any:
    if isinstance(node, str):
        return scrub_text(node)
    if isinstance(node, dict):
        return {k: scrub(v) for k, v in node.items()}
    if isinstance(node, list):
        return [scrub(v) for v in node]
    return node


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    out: dict[str, Any] = {
        "n": len(values), "min_s": round(min(values), 3), "median_s": round(statistics.median(values), 3),
        "mean_s": round(statistics.fmean(values), 3), "max_s": round(max(values), 3),
    }
    if len(values) > 1:
        out["stdev_s"] = round(statistics.stdev(values), 3)
    return out


def info_view(reply: Reply) -> dict[str, Any]:
    p = reply.payload if isinstance(reply.payload, dict) else {}
    return {"ok": reply.ok, "code": reply.code, "units": p.get("units"), "locked": p.get("locked"),
            "counts": p.get("counts"), "product": p.get("product"), "program_version": p.get("program_version")}


# ---------------------------------------------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------------------------------------------
@dataclass
class Config:
    model: Path
    server_exe: str
    product: str = "ETABS"
    version: str | None = None
    runs: int = 3
    design_kind: str = "concrete"
    skip_design: bool = False
    short_timeout_sec: int | None = None
    long_timeout_sec: int = 900
    timeout_tests: tuple[str, ...] = ("analysis",)
    probe_unsaved: bool = False
    keep_open: bool = False
    run_root: Path = Path("spike-runs")
    dialog_poll_sec: float = 0.5
    host_pid: int | None = None
    server_args: tuple[str, ...] = ()
    mode: str = "auto"


@dataclass
class Ctx:
    cfg: Config
    run_dir: Path
    open_session: SessionFactory
    watcher: DialogWatcher
    record: dict[str, Any]
    model_copy: Path | None = None
    s1: Session | None = None
    pid_known: set[int] = field(default_factory=set)


async def timed(ctx: Ctx, name: str, session: Session, tool: str, args: dict[str, Any] | None = None,
                timeout_s: float | None = None) -> Reply:
    args = args or {}
    reply = await ctx.watcher.during(name, session.call(tool, args, timeout_s))
    ctx.record["steps"].append(scrub({
        "step": name, "server": session.label, "tool": tool, "args": {k: v for k, v in args.items() if k != "path"},
        "ok": reply.ok, "code": reply.code, "message": (reply.message or "")[:300], "elapsed_s": round(reply.elapsed_s, 3),
        "kind": reply.kind,
    }))
    return reply


async def get_info(ctx: Ctx, name: str, session: Session | None = None, timeout_s: float | None = None) -> dict[str, Any]:
    r = await timed(ctx, name, session or ctx.s1, "csi_model_info", {}, timeout_s)  # type: ignore[arg-type]
    return info_view(r)


async def ensure_unlocked(ctx: Ctx, why: str) -> dict[str, Any] | None:
    info = await get_info(ctx, f"{why}: info before unlock")
    if info.get("locked"):
        r = await timed(ctx, f"{why}: unlock", ctx.s1, "csi_unlock_model", {"confirm": True})  # type: ignore[arg-type]
        return {"unlocked": r.ok, "code": r.code, "elapsed_s": round(r.elapsed_s, 3)}
    return None


async def save_model(ctx: Ctx, name: str) -> Reply:
    # Without a path the server saves to the model's own file (the copy); the file exists, so confirm is required.
    return await timed(ctx, name, ctx.s1, "csi_save_model", {"confirm": True})  # type: ignore[arg-type]


def mcp_args(cfg: Config, run_dir: Path, label: str, call_timeout: int) -> list[str]:
    return ["--call-timeout-sec", str(call_timeout), "--audit-log", str(run_dir / f"csi-mcp-audit-{label}.jsonl"),
            *cfg.server_args]


def design_args(cfg: Config) -> dict[str, Any]:
    return {"kind": cfg.design_kind, "confirm": True}


async def phase_start(ctx: Ctx) -> bool:
    cfg, rec = ctx.cfg, ctx.record
    ctx.s1 = await ctx.open_session("main", mcp_args(cfg, ctx.run_dir, "main", cfg.long_timeout_sec))
    rec["synthetic"] = bool(ctx.s1.synthetic)
    tools = await ctx.s1.list_tool_names()
    names = sorted(t["name"] for t in tools)
    rec["server"] = {
        "tool_count": len(names),
        "tool_list_sha256": hashlib.sha256(json.dumps(tools, sort_keys=True, default=str).encode()).hexdigest(),
        "missing_tools": sorted(ALLOWED_TOOLS - set(names)),
        "escape_hatch_tools_listed": sorted(FORBIDDEN_TOOLS & set(names)),
        "note": "escape-hatch tools listed by the server are never called",
    }
    launch_args: dict[str, Any] = {"product": cfg.product, "visible": True}
    if cfg.version:
        launch_args["version"] = cfg.version
    r = await timed(ctx, "launch host", ctx.s1, "csi_launch", launch_args)
    rec["launch"] = {"ok": r.ok, "code": r.code, "message": scrub_text(r.message or ""), "elapsed_s": round(r.elapsed_s, 3)}
    if not r.ok:
        return False
    st = await timed(ctx, "status", ctx.s1, "csi_status")
    ctx.pid_known = find_pids(r.payload) | find_pids(st.payload)
    if cfg.host_pid:
        ctx.pid_known = {cfg.host_pid}
    ctx.watcher.pids = set(ctx.pid_known)
    rec["host"] = {"pids": sorted(ctx.pid_known), "window_probe": ctx.watcher.probe.note if ctx.watcher.probe.available
                   else ctx.watcher.probe.note, "dialog_detection": bool(ctx.watcher.probe.available and ctx.pid_known)}
    r = await timed(ctx, "open copy", ctx.s1, "csi_open_model", {"path": str(ctx.model_copy), "confirm": True})
    rec["open"] = {"ok": r.ok, "code": r.code, "message": scrub_text(r.message or ""), "elapsed_s": round(r.elapsed_s, 3)}
    if not r.ok:
        return False
    rec["initial_state"] = await get_info(ctx, "info after open")
    return True


async def phase_runs(ctx: Ctx) -> None:
    cfg, rec = ctx.cfg, ctx.record
    runs: list[dict[str, Any]] = []
    for i in range(1, cfg.runs + 1):
        run: dict[str, Any] = {"run": i}
        run["unlock_before"] = await ensure_unlocked(ctx, f"run {i}")
        save = await save_model(ctx, f"run {i}: save before analysis")
        run["save"] = {"ok": save.ok, "code": save.code, "elapsed_s": round(save.elapsed_s, 3)}
        run["units_before"] = (await get_info(ctx, f"run {i}: info before analysis"))["units"]
        a = await timed(ctx, f"run {i}: analysis", ctx.s1, "csi_run_analysis", {"confirm": True})  # type: ignore[arg-type]
        run["analysis"] = {"ok": a.ok, "code": a.code, "message": scrub_text(a.message or ""), "elapsed_s": round(a.elapsed_s, 3),
                           "reply": scrub(a.payload) if isinstance(a.payload, dict) else None}
        after_a = await get_info(ctx, f"run {i}: info after analysis")
        run["after_analysis"] = after_a
        if not cfg.skip_design:
            d = await timed(ctx, f"run {i}: design ({cfg.design_kind})", ctx.s1, "csi_design_run", design_args(cfg))  # type: ignore[arg-type]
            run["design"] = {"ok": d.ok, "code": d.code, "message": scrub_text(d.message or ""), "elapsed_s": round(d.elapsed_s, 3)}
            run["after_design"] = await get_info(ctx, f"run {i}: info after design")
        runs.append(run)
    rec["runs"] = runs
    ok = lambda key: [r[key]["elapsed_s"] for r in runs if r.get(key, {}).get("ok")]  # noqa: E731
    rec["stats"] = {"save": stats(ok("save")), "analysis": stats(ok("analysis")), "design": stats(ok("design"))}


async def phase_locked(ctx: Ctx) -> None:
    probe_args = {"x": 0.0, "y": 0.0, "z": 0.0, "dry_run": True}  # dry run: the model is never changed
    out: dict[str, Any] = {}
    info = await get_info(ctx, "locked: info")
    out["locked_after_analysis"] = info.get("locked")
    r = await timed(ctx, "locked: write probe (dry run)", ctx.s1, "csi_add_point", probe_args)  # type: ignore[arg-type]
    out["write_probe_while_locked"] = {"ok": r.ok, "code": r.code, "message": scrub_text(r.message or "")}
    if info.get("locked"):
        u = await timed(ctx, "locked: unlock", ctx.s1, "csi_unlock_model", {"confirm": True})  # type: ignore[arg-type]
        out["unlock"] = {"ok": u.ok, "code": u.code, "elapsed_s": round(u.elapsed_s, 3)}
        out["locked_after_unlock"] = (await get_info(ctx, "locked: info after unlock")).get("locked")
        r2 = await timed(ctx, "locked: write probe after unlock (dry run)", ctx.s1, "csi_add_point", probe_args)  # type: ignore[arg-type]
        out["write_probe_after_unlock"] = {"ok": r2.ok, "code": r2.code, "message": scrub_text(r2.message or "")}
    else:
        out["unlock"] = "not needed: the model was not locked after analysis"
    ctx.record["model_locked"] = out


def auto_short_timeout(ctx: Ctx) -> int:
    if ctx.cfg.short_timeout_sec:
        return ctx.cfg.short_timeout_sec
    fastest = ctx.record.get("stats", {}).get("analysis", {}).get("min_s")
    # Spike parameter, not an engineering value: 30 percent of the fastest measured analysis, at least 1 second.
    return max(1, int((fastest or 10) * 0.3))


async def phase_timeout(ctx: Ctx) -> None:
    cfg = ctx.cfg
    results: list[dict[str, Any]] = []
    for which in cfg.timeout_tests:
        tool, args = ("csi_run_analysis", {"confirm": True}) if which == "analysis" else ("csi_design_run", design_args(cfg))
        short = auto_short_timeout(ctx)
        res: dict[str, Any] = {"tool": tool, "configured_call_timeout_s": short}
        await ensure_unlocked(ctx, f"timeout {which}")
        if which == "design":  # design needs analysis results
            await timed(ctx, "timeout design: analysis first", ctx.s1, "csi_run_analysis", {"confirm": True})  # type: ignore[arg-type]
        await save_model(ctx, f"timeout {which}: save")
        res["state_before"] = await get_info(ctx, f"timeout {which}: info before")
        s2 = await ctx.open_session("short", mcp_args(cfg, ctx.run_dir, "short", short))
        try:
            attach_args: dict[str, Any] = {"product": cfg.product}
            if ctx.pid_known:
                attach_args["pid"] = sorted(ctx.pid_known)[0]
            att = await timed(ctx, f"timeout {which}: attach second server", s2, "csi_attach", attach_args)
            res["attach"] = {"ok": att.ok, "code": att.code, "message": scrub_text(att.message or "")}
            if not att.ok:
                res["not_run"] = "the second server could not attach to the running host"
                results.append(res)
                continue
            t_start = _clock()
            r = await timed(ctx, f"timeout {which}: call with short timeout", s2, tool, args, timeout_s=short + 120)
            returned_s = _clock() - t_start
            res["reply"] = {"ok": r.ok, "code": r.code, "message": scrub_text(r.message or ""), "kind": r.kind,
                            "returned_after_s": round(returned_s, 3), "payload": scrub(r.payload) if r.ok else None}
            # The first server now waits for the host: how long until ETABS answers again?
            p = await timed(ctx, f"timeout {which}: first server waits for host", ctx.s1, "csi_model_info", {},  # type: ignore[arg-type]
                            timeout_s=cfg.long_timeout_sec)
            free_s = _clock() - t_start
            res["host_answered_again_after_s"] = round(free_s, 3)
            res["extra_wait_after_return_s"] = round(free_s - returned_s, 3)
            res["host_still_busy_after_return"] = (free_s - returned_s) > HOST_BUSY_THRESHOLD_S
            res["state_after"] = info_view(p)
            res["units_unchanged"] = res["state_before"].get("units") == res["state_after"].get("units")
            if which == "analysis":
                st = await timed(ctx, "timeout analysis: case status", ctx.s1, "csi_analysis_status", {})  # type: ignore[arg-type]
                cases = st.payload.get("cases") if isinstance(st.payload, dict) else None
                res["case_status_codes"] = scrub(cases) if isinstance(cases, list) else None
            info2 = await get_info(ctx, f"timeout {which}: second server info", s2, timeout_s=cfg.long_timeout_sec)
            res["second_server_info_after"] = info2
        finally:
            await s2.close()
        results.append(res)
    ctx.record["timeout_tests"] = results


async def phase_unsaved(ctx: Ctx) -> None:
    out: dict[str, Any] = {"warning": "may stop at a dialog; the script does not click it; dismiss it by hand"}
    await ensure_unlocked(ctx, "unsaved probe")
    r = await timed(ctx, "unsaved probe: analysis without save", ctx.s1, "csi_run_analysis", {"confirm": True},  # type: ignore[arg-type]
                    timeout_s=ctx.cfg.long_timeout_sec)
    out["analysis"] = {"ok": r.ok, "code": r.code, "message": scrub_text(r.message or ""), "elapsed_s": round(r.elapsed_s, 3)}
    ctx.record["unsaved_probe"] = out


async def run_spike(cfg: Config, open_session: SessionFactory, probe: WindowProbe, run_dir: Path) -> dict[str, Any]:
    """Runs all phases and writes record.json and summary.md into run_dir. Returns the record."""
    run_dir.mkdir(parents=True, exist_ok=True)
    started = dt.datetime.now(dt.UTC)
    record: dict[str, Any] = {
        "spike": SPIKE, "schema": SCHEMA_VERSION, "synthetic": False, "needs_local_test": True,
        "started_utc": started.isoformat(timespec="seconds"),
        "environment": {"platform": platform.platform(), "python": platform.python_version()},
        "inputs": {k: v for k, v in {
            "model_file": cfg.model.name, "server_exe": Path(cfg.server_exe).name, "product": cfg.product,
            "runs": cfg.runs, "design_kind": None if cfg.skip_design else cfg.design_kind,
            "long_call_timeout_s": cfg.long_timeout_sec, "short_call_timeout_s": cfg.short_timeout_sec or "auto",
            "timeout_tests": list(cfg.timeout_tests), "probe_unsaved": cfg.probe_unsaved,
        }.items()},
        "steps": [], "errors": [],
    }
    ctx = Ctx(cfg, run_dir, open_session, DialogWatcher(probe, cfg.dialog_poll_sec), record)
    # Work only on a copy; the original is hashed before and after.
    model_dir = run_dir / "model-copy"
    model_dir.mkdir(exist_ok=True)
    before = sha256_file(cfg.model)
    ctx.model_copy = model_dir / cfg.model.name
    shutil.copy2(cfg.model, ctx.model_copy)
    record["original_model"] = {"sha256_before": before}
    record["copy"] = {"sha256": sha256_file(ctx.model_copy)}
    try:
        if await phase_start(ctx):
            await phase_runs(ctx)
            await phase_locked(ctx)
            if cfg.timeout_tests:
                await phase_timeout(ctx)
            if cfg.probe_unsaved:
                await phase_unsaved(ctx)
    except ForbiddenTool:
        raise
    except Exception as exc:  # noqa: BLE001
        record["errors"].append(f"{type(exc).__name__}: {scrub_text(str(exc))[:300]}")
    finally:
        if ctx.s1 is not None:
            if not cfg.keep_open:
                ex = await ctx.s1.call("csi_exit", {"confirm": True})
                record["exit"] = {"ok": ex.ok, "code": ex.code}
            await ctx.s1.close()
        after = sha256_file(cfg.model)
        record["original_model"].update({"sha256_after": after, "unchanged": after == before})
        record["dialogs"] = scrub(ctx.watcher.report())
        record["finished_utc"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        (run_dir / "record.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        (run_dir / "summary.md").write_text(render_summary(record), encoding="utf-8")
    return record


# ---------------------------------------------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------------------------------------------
def _fmt(v: Any) -> str:
    return "-" if v is None else str(v)


def render_summary(rec: dict[str, Any]) -> str:
    L: list[str] = []
    syn = " (SYNTHETIC replies, not a host result)" if rec.get("synthetic") else ""
    L += [f"# Spike S-02 run summary{syn}", "",
          f"Started {rec['started_utc']} UTC, finished {rec.get('finished_utc', '-')} UTC. Record: record.json. "
          "Everything here is from one local run (needs local test until the report is written).", ""]
    inp = rec["inputs"]
    L += ["## Inputs", "", f"- Model file (a copy was used): {inp['model_file']}; server: {inp['server_exe']}; product: {inp['product']}",
          f"- Runs: {inp['runs']}; design kind: {_fmt(inp['design_kind'])}; long call timeout {inp['long_call_timeout_s']} s; "
          f"short call timeout {inp['short_call_timeout_s']} s",
          f"- Original model unchanged: {rec.get('original_model', {}).get('unchanged')}", ""]
    if rec.get("errors"):
        L += ["## Errors (the run did not finish cleanly)", ""] + [f"- {e}" for e in rec["errors"]] + [""]
    srv = rec.get("server", {})
    if srv:
        L += ["## Server", "", f"- Tools listed: {srv['tool_count']}; missing tools this spike needs: {srv['missing_tools'] or 'none'}; "
              f"escape-hatch tools visible (never called): {srv['escape_hatch_tools_listed'] or 'none'}",
              f"- Launch: ok={rec.get('launch', {}).get('ok')} {_fmt(rec.get('launch', {}).get('code'))}; "
              f"open copy: ok={rec.get('open', {}).get('ok')} {_fmt(rec.get('open', {}).get('code'))}",
              f"- Dialog detection: {rec.get('host', {}).get('dialog_detection')} ({rec.get('host', {}).get('window_probe')})", ""]
    st = rec.get("stats")
    if st:
        L += ["## Run times (seconds)", "", "| Step | n | min | median | mean | max |", "|---|---|---|---|---|---|"]
        for k in ("save", "analysis", "design"):
            s = st[k]
            L.append(f"| {k} | {s['n']} | {_fmt(s.get('min_s'))} | {_fmt(s.get('median_s'))} | {_fmt(s.get('mean_s'))} | {_fmt(s.get('max_s'))} |")
        L += ["", "| Run | save | analysis | locked after analysis | design | units before | units after analysis |", "|---|---|---|---|---|---|---|"]
        for r in rec["runs"]:
            L.append(f"| {r['run']} | {r['save']['elapsed_s']} ({'ok' if r['save']['ok'] else r['save']['code']}) | "
                     f"{r['analysis']['elapsed_s']} ({'ok' if r['analysis']['ok'] else r['analysis']['code']}) | "
                     f"{_fmt(r['after_analysis'].get('locked'))} | "
                     f"{_fmt(r.get('design', {}).get('elapsed_s'))} ({'ok' if r.get('design', {}).get('ok') else _fmt(r.get('design', {}).get('code'))}) | "
                     f"{_fmt(r['units_before'])} | {_fmt(r['after_analysis'].get('units'))} |")
        L.append("")
    ml = rec.get("model_locked")
    if ml:
        L += ["## Model locked and unlock", "",
              f"- Locked after analysis: {_fmt(ml.get('locked_after_analysis'))}",
              f"- Write probe (dry run) while locked: {ml['write_probe_while_locked']}",
              f"- Unlock: {ml.get('unlock')}; locked afterwards: {_fmt(ml.get('locked_after_unlock'))}",
              f"- Write probe after unlock: {_fmt(ml.get('write_probe_after_unlock'))}", ""]
    for t in rec.get("timeout_tests", []):
        L += [f"## Short timeout: {t['tool']} with call timeout {t['configured_call_timeout_s']} s", ""]
        if t.get("not_run"):
            L += [f"- Not run: {t['not_run']} ({t.get('attach')})", ""]
            continue
        rp = t["reply"]
        L += [f"- The server returned: ok={rp['ok']}, code={_fmt(rp['code'])}, after {rp['returned_after_s']} s. Message: {_fmt(rp['message'])}",
              f"- The first server then waited {t['extra_wait_after_return_s']} s more before the host answered "
              f"(host still busy after the reply: {t['host_still_busy_after_return']}; total {t['host_answered_again_after_s']} s)",
              f"- State before: {t['state_before']}", f"- State after: {t['state_after']}",
              f"- Units unchanged: {t['units_unchanged']}; case status codes: {_fmt(t.get('case_status_codes'))}",
              f"- Second server (the one that timed out) state afterwards: {t['second_server_info_after']}", ""]
    up = rec.get("unsaved_probe")
    if up:
        L += ["## Analysis without saving first", "", f"- {up['analysis']}", ""]
    dl = rec.get("dialogs", [])
    L += ["## Dialogs seen (detected, never clicked)", ""]
    if not dl:
        L.append("- None seen" + ("" if rec.get("host", {}).get("dialog_detection") else " (detection was not available: see above)") + ".")
    for d in dl:
        L.append(f"- \"{d['title']}\" class {d['class']}, first seen {d['first_seen_s']:.1f} s, during: {', '.join(d['phases'])}, "
                 f"modal suspected: {d['modal_suspected']}")
    L += ["", "## Steps", "", "| Step | Server | Tool | ok | code | seconds |", "|---|---|---|---|---|---|"]
    for s in rec["steps"]:
        L.append(f"| {s['step']} | {s['server']} | {s['tool']} | {s['ok']} | {_fmt(s['code'])} | {s['elapsed_s']} |")
    L += ["", "Send record.json and this file back. Check that no client or project name appears before you send them.", ""]
    return "\n".join(L)


# ---------------------------------------------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="s02_run.py", description="Spike S-02: analysis and design through sasaah-csi-mcp, on a copy of a model.",
        epilog="Needs ETABS on this machine. Everything it measures is a local result. See README.md.")
    p.add_argument("--model", type=Path, required=True, help="the ETABS model to test; it is copied, never changed")
    p.add_argument("--server-exe", required=True, help="path to sasaah-csi-mcp (the exe built from Sasaah)")
    p.add_argument("--product", default="ETABS", help="product passed to csi_launch (default ETABS)")
    p.add_argument("--version", default=None, help="product version passed to csi_launch (default: server default)")
    p.add_argument("--runs", type=int, default=3, help="number of save+analysis+design runs (default 3)")
    p.add_argument("--design-kind", choices=DESIGN_KINDS, default="concrete", help="design kind for csi_design_run")
    p.add_argument("--skip-design", action="store_true", help="do not run design")
    p.add_argument("--short-timeout-sec", type=int, default=None,
                   help="call timeout of the second server; default: 30 percent of the fastest analysis, at least 1 s")
    p.add_argument("--long-timeout-sec", type=int, default=900, help="call timeout of the main server (default 900)")
    p.add_argument("--timeout-tests", default="analysis", help="comma list of analysis,design or none (default analysis)")
    p.add_argument("--probe-unsaved", action="store_true",
                   help="also run an analysis without saving first (may show a dialog; dismiss it by hand)")
    p.add_argument("--keep-open", action="store_true", help="leave ETABS open at the end")
    p.add_argument("--run-root", type=Path, default=Path("spike-runs"), help="folder for run folders (default ./spike-runs)")
    p.add_argument("--dialog-poll-sec", type=float, default=0.5, help="how often the ETABS windows are checked")
    p.add_argument("--host-pid", type=int, default=None, help="process id of ETABS if the server does not report it")
    p.add_argument("--server-arg", action="append", default=[], help="extra argument for the server (repeatable)")
    p.add_argument("--mode", default="auto", help="MCP connect mode of the SDK client (auto or legacy)")
    p.add_argument("--dry-run", action="store_true", help="print the plan; start nothing, copy nothing, write nothing")
    return p


def config_from_args(a: argparse.Namespace) -> Config:
    tests = () if a.timeout_tests.strip().lower() == "none" else tuple(t.strip() for t in a.timeout_tests.split(",") if t.strip())
    bad = [t for t in tests if t not in TIMEOUT_TEST_CHOICES]
    if bad:
        raise SystemExit(f"--timeout-tests: unknown {bad}; use analysis, design or none")
    if tests and "design" in tests and a.skip_design:
        raise SystemExit("--timeout-tests design needs design: remove --skip-design")
    if a.runs < 1:
        raise SystemExit("--runs must be at least 1")
    return Config(a.model, a.server_exe, a.product, a.version, a.runs, a.design_kind, a.skip_design, a.short_timeout_sec,
                  a.long_timeout_sec, tests, a.probe_unsaved, a.keep_open, a.run_root, a.dialog_poll_sec, a.host_pid,
                  tuple(a.server_arg), a.mode)


def dry_run_text(cfg: Config) -> str:
    lines = [
        "DRY RUN: nothing is started, copied or written.",
        f"Model file : {cfg.model.name} ({'found' if cfg.model.is_file() else 'NOT FOUND'}); it would be copied into the run folder; the original is only hashed.",
        f"Server     : {Path(cfg.server_exe).name} ({'found' if Path(cfg.server_exe).is_file() else 'NOT FOUND'}) over stdio, "
        f"main call timeout {cfg.long_timeout_sec} s, audit log in the run folder.",
        f"Run folder : {cfg.run_root}/S-02-<UTC time>/  (record.json, summary.md, model-copy/, server logs)",
        f"Window probe: {default_probe().note}",
        "Plan:",
        "  1. list tools; csi_launch (visible); csi_status; csi_open_model on the copy; csi_model_info",
        f"  2. {cfg.runs} runs of: unlock if locked, csi_save_model, csi_model_info, csi_run_analysis (timed), csi_model_info"
        + ("" if cfg.skip_design else f", csi_design_run kind={cfg.design_kind} (timed), csi_model_info"),
        "  3. model_locked probe: csi_add_point with dry_run=true while locked; csi_unlock_model; probe again",
    ]
    if cfg.timeout_tests:
        short = cfg.short_timeout_sec or "auto (30 percent of the fastest analysis, at least 1 s)"
        lines.append(f"  4. second server with --call-timeout-sec {short}: csi_attach, then {', '.join(cfg.timeout_tests)} "
                     "through it; the main server waits for the host (csi_model_info); csi_analysis_status")
    if cfg.probe_unsaved:
        lines.append("  5. csi_run_analysis without saving first (dialog probe)")
    lines.append(f"  6. {'leave ETABS open' if cfg.keep_open else 'csi_exit'}; hash the original again")
    lines.append("Tools that may be called: " + ", ".join(sorted(ALLOWED_TOOLS)))
    lines.append("Never called (escape hatches): " + ", ".join(sorted(FORBIDDEN_TOOLS)))
    return "\n".join(lines)


async def main_async(cfg: Config) -> int:
    if not cfg.model.is_file():
        print(f"error: model file not found: {cfg.model.name}", file=sys.stderr)
        return 2
    if not Path(cfg.server_exe).is_file():
        print(f"error: server executable not found: {Path(cfg.server_exe).name}", file=sys.stderr)
        return 2
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = (cfg.run_root / f"S-02-{stamp}").resolve()
    if run_dir == cfg.model.resolve().parent or cfg.model.resolve().is_relative_to(run_dir):
        print("error: the run folder must not contain the model", file=sys.stderr)
        return 2
    run_dir.mkdir(parents=True, exist_ok=True)

    async def factory(label: str, args: list[str]) -> Session:
        return await McpSession(label, cfg.server_exe, args, run_dir / f"server-{label}.stderr.log", cfg.mode).open()

    print(f"Run folder: {run_dir}")
    record = await run_spike(cfg, factory, default_probe(), run_dir)
    print((run_dir / "summary.md").read_text(encoding="utf-8"))
    print(f"\nSend back: {run_dir / 'record.json'} and {run_dir / 'summary.md'}")
    return 1 if record["errors"] else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = config_from_args(args)
    if args.dry_run:
        print(dry_run_text(cfg))
        return 0
    return asyncio.run(main_async(cfg))


if __name__ == "__main__":
    sys.exit(main())
