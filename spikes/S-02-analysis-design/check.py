#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["mcp>=2,<3"]
# ///
"""CI check for spike S-02 (CI runs every spikes/*/check.py on Linux; no host program is needed).

It proves that s02_run.py parses and that its logic works, by running it against a STUB session that replays
SYNTHETIC replies. The synthetic replies are invented for this test from the S-12 tool schemas
(spikes/S-12-sasaah-tool-inventory/inventory/sasaah-csi-mcp.json) and from reading the Sasaah sources; they are not
host results. The stub also validates every call's arguments against the S-12 input schema.

Also checks: every tool the script may call exists in the inventory and is not an escape hatch; escape-hatch calls
are refused; the real MCP SDK pieces the script uses (mcp 2.x) construct; the record and summary contain no paths.
Exit code 0 on success, 1 on any failure.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import s02_run as s02  # noqa: E402

INVENTORY = HERE.parent / "S-12-sasaah-tool-inventory" / "inventory" / "sasaah-csi-mcp.json"
TOOLS = {t["name"]: t for t in json.loads(INVENTORY.read_text(encoding="utf-8"))["tools"]}
failures: list[str] = []


def expect(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)
        print(f"FAIL: {msg}")
    else:
        print(f"ok:   {msg}")


TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}


def validate_args(tool: str, args: dict[str, Any]) -> list[str]:
    schema = TOOLS[tool]["input_schema"]
    props = schema.get("properties", {})
    errs = [f"{tool}: unknown argument {k}" for k in args if k not in props]
    errs += [f"{tool}: missing {k}" for k in schema.get("required") or [] if k not in args]
    for k, v in args.items():
        t = props.get(k, {}).get("type")
        if t in TYPES and (not isinstance(v, TYPES[t]) or (t != "boolean" and isinstance(v, bool))):
            errs.append(f"{tool}: argument {k} is not {t}")
    return errs


class FakeClock:
    def __init__(self) -> None:
        self.t = 100.0

    def now(self) -> float:
        return self.t


class SynthHost:
    """SYNTHETIC ETABS stand-in: just enough state to replay the replies the script reads."""

    ANALYSIS_S, DESIGN_S = 30.0, 12.0

    def __init__(self, clock: FakeClock) -> None:
        self.clock, self.units, self.locked = clock, "kN_m_C", False
        self.busy_until, self.pending_lock = 0.0, False
        self.dialog_visible = False
        self.calls: list[str] = []

    def settle(self) -> None:
        if self.clock.t < self.busy_until:
            self.clock.t = self.busy_until  # a call to the busy host waits
        if self.pending_lock and self.clock.t >= self.busy_until:
            self.locked, self.pending_lock = True, False

    def handle(self, tool: str, args: dict[str, Any], timeout_s: int) -> tuple[bool, Any]:
        self.settle()
        self.calls.append(tool)
        c = self.clock
        if tool == "csi_launch":
            return True, {"product": "ETABS", "pid": 4242, "launched": True}
        if tool == "csi_status":
            return True, {"attached": True, "target": {"pid": 4242, "product": "ETABS"}}
        if tool == "csi_attach":
            return True, {"attached": True, "pid": 4242}
        if tool == "csi_open_model":
            c.t += 2
            return True, {"opened": True}
        if tool == "csi_save_model":
            c.t += 1.5
            self.dialog_visible = False
            return True, {"saved": True}
        if tool == "csi_model_info":
            c.t += 0.05
            return True, {"product": "ETABS", "units": self.units, "program_version": "22.0.0",
                          "model_path": "C:\\Users\\someone\\work\\copy.EDB", "locked": self.locked,
                          "counts": {"points": 10, "frames": 12, "areas": 3}}
        if tool in ("csi_run_analysis", "csi_design_run"):
            dur = self.ANALYSIS_S if tool == "csi_run_analysis" else self.DESIGN_S
            if tool == "csi_design_run" and not self.locked:
                return False, {"code": "csi_error", "message": "no analysis results", "data": None}
            start = c.t
            if dur > timeout_s:
                c.t = start + timeout_s
                self.busy_until = start + dur
                self.pending_lock = tool == "csi_run_analysis"
                return False, {"code": "timeout", "message": f"timed out after {timeout_s} s", "data": None}
            c.t = start + dur
            if tool == "csi_run_analysis":
                self.locked = True
                return True, {"started": True}
            return True, {"designed": True, "kind": args["kind"]}
        if tool == "csi_analysis_status":
            return True, {"cases": [{"case": "DEAD", "status_code": 4}]}
        if tool == "csi_unlock_model":
            self.locked = False
            return True, {"unlocked": True}
        if tool == "csi_add_point":
            if self.locked:
                return False, {"code": "model_locked", "message": "needs an unlocked model", "data": None}
            return True, {"dry_run": True, "plan": {}}
        if tool == "csi_exit":
            return True, {"exited": {}}
        return False, {"code": "csi_error", "message": f"synthetic host does not know {tool}", "data": None}


class StubSession(s02.Session):
    synthetic = True

    def __init__(self, host: SynthHost, label: str, args: list[str]) -> None:
        self.host, self.label = host, label
        self.timeout_s = int(args[args.index("--call-timeout-sec") + 1])

    async def _call(self, tool: str, args: dict[str, Any], timeout_s: float | None) -> s02.Reply:
        errs = validate_args(tool, args)
        if errs:
            failures.extend(errs)
            return s02.Reply(tool, False, 0.0, "invalid_args", "; ".join(errs), kind="tool_error")
        ok, payload = self.host.handle(tool, args, self.timeout_s)
        if ok:
            return s02.Reply(tool, True, 0.0, payload=payload, text=json.dumps(payload))
        return s02.Reply(tool, False, 0.0, payload["code"], payload["message"], payload, json.dumps(payload), "tool_error")

    async def list_tool_names(self) -> list[dict[str, Any]]:
        return [{"name": n, "input_schema": t["input_schema"]} for n, t in TOOLS.items()]


class FakeProbe(s02.WindowProbe):
    available, note = True, "fake window probe (synthetic)"

    def __init__(self, host: SynthHost) -> None:
        self.host = host

    def snapshot(self, pids: set[int]) -> list[dict[str, Any]]:
        wins = [{"hwnd": 1, "title": "ETABS - model", "class": "Afx:Main", "enabled": not self.host.dialog_visible, "has_owner": False}]
        if self.host.dialog_visible:
            wins.append({"hwnd": 2, "title": "Save Model As", "class": "#32770", "enabled": True, "has_owner": True})
        return wins


def check_inventory() -> None:
    names = set(TOOLS)
    expect(s02.ALLOWED_TOOLS <= names, "every tool the script may call exists in the S-12 inventory")
    expect(not any(TOOLS[n]["classification"] == "escape-hatch" for n in s02.ALLOWED_TOOLS), "no allowed tool is an escape hatch")
    escapes = {n for n, t in TOOLS.items() if t["classification"] == "escape-hatch"}
    expect(escapes <= s02.FORBIDDEN_TOOLS, "every escape hatch of the inventory is on the forbidden list")
    expect(not (s02.ALLOWED_TOOLS & s02.FORBIDDEN_TOOLS), "allowed and forbidden lists are disjoint")


async def check_guard() -> None:
    host = SynthHost(FakeClock())
    s = StubSession(host, "main", ["--call-timeout-sec", "5"])
    for tool, args in (("csi_run_script", {}), ("csi_db_tables_apply", {}), ("csi_delete_object", {}), ("csi_add_point", {"x": 0, "y": 0, "z": 0})):
        try:
            await s.call(tool, args)
            expect(False, f"{tool} is refused")
        except s02.ForbiddenTool:
            expect(True, f"{tool} is refused")


async def check_run(tmp: Path) -> None:
    clock = FakeClock()
    s02._clock = clock.now
    host = SynthHost(clock)
    model = tmp / "orig.EDB"
    model.write_bytes(b"synthetic model bytes")

    async def factory(label: str, args: list[str]) -> s02.Session:
        return StubSession(host, label, args)

    cfg = s02.Config(model, "sasaah-csi-mcp.exe", runs=2, timeout_tests=("analysis", "design"), run_root=tmp, dialog_poll_sec=0.01)
    rec = await s02.run_spike(cfg, factory, FakeProbe(host), tmp / "run")
    expect(not rec["errors"], f"run finished without errors {rec['errors']}")
    expect(rec["synthetic"] is True, "record is marked synthetic")
    expect(rec["original_model"]["unchanged"] and (tmp / "run" / "model-copy" / "orig.EDB").is_file(), "original untouched, copy made")
    expect(rec["stats"]["analysis"]["n"] == 2 and rec["stats"]["analysis"]["median_s"] == 30.0, "analysis times measured (synthetic 30 s)")
    expect(rec["stats"]["design"]["median_s"] == 12.0, "design times measured (synthetic 12 s)")
    expect(rec["runs"][0]["after_analysis"]["locked"] is True, "locked after analysis recorded")
    ml = rec["model_locked"]
    expect(ml["write_probe_while_locked"]["code"] == "model_locked", "write probe while locked returns model_locked")
    expect(ml["write_probe_after_unlock"]["ok"] and ml["locked_after_unlock"] is False, "unlock lifts the lock")
    tt = {t["tool"]: t for t in rec["timeout_tests"]}
    ta = tt["csi_run_analysis"]
    expect(ta["configured_call_timeout_s"] == 9, "auto short timeout is 30 percent of the fastest analysis")
    expect(ta["reply"]["code"] == "timeout" and ta["reply"]["returned_after_s"] == 9.0, "short-timeout reply recorded with its time")
    expect(ta["host_still_busy_after_return"] and 20 < ta["extra_wait_after_return_s"] < 22, "extra wait after the timeout recorded")
    expect(ta["state_after"]["locked"] is True and ta["units_unchanged"], "state and units afterwards recorded")
    expect(ta["case_status_codes"] == [{"case": "DEAD", "status_code": 4}], "case status recorded")
    expect(tt["csi_design_run"]["reply"]["code"] == "timeout", "design timeout recorded")
    expect("csi_run_script" not in host.calls and "csi_db_tables_apply" not in host.calls, "no escape hatch was called")
    expect(host.calls.count("csi_exit") == 1, "host exited at the end")
    text = (tmp / "run" / "record.json").read_text(encoding="utf-8") + (tmp / "run" / "summary.md").read_text(encoding="utf-8")
    expect("Users" not in text and "someone" not in text, "record and summary contain no full paths")
    expect("SYNTHETIC" in text, "summary says the replies are synthetic")
    # dialog detection, with a dialog shown during the unsaved probe
    host2 = SynthHost(clock)
    orig = host2.handle

    def handle(tool: str, args: dict[str, Any], t: int) -> tuple[bool, Any]:
        if tool == "csi_run_analysis" and host2.calls.count("csi_run_analysis") >= 1:
            host2.dialog_visible = True
        return orig(tool, args, t)

    host2.handle = handle  # type: ignore[method-assign]

    async def factory2(label: str, args: list[str]) -> s02.Session:
        return StubSession(host2, label, args)

    cfg2 = s02.Config(model, "x.exe", runs=1, timeout_tests=(), probe_unsaved=True, run_root=tmp, dialog_poll_sec=0.01)
    rec2 = await s02.run_spike(cfg2, factory2, FakeProbe(host2), tmp / "run2")
    d = rec2["dialogs"]
    expect(any(x["title"] == "Save Model As" and x["modal_suspected"] for x in d), "a modal dialog is detected and reported")
    expect("unsaved_probe" in rec2, "unsaved probe recorded")


def check_sdk_and_cli(tmp: Path) -> None:
    import mcp_types
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters, stdio_client

    ok = s02.parse_result("csi_model_info", mcp_types.CallToolResult(content=[mcp_types.TextContent(text='{"units":"kN_m_C"}')]), 1.0)
    bad = s02.parse_result("csi_unlock_model", mcp_types.CallToolResult(
        content=[mcp_types.TextContent(text='{"code":"model_locked","message":"m","data":null}')], is_error=True), 1.0)
    expect(ok.ok and ok.payload == {"units": "kN_m_C"}, "SDK success result parses")
    expect(not bad.ok and bad.code == "model_locked", "SDK error result parses to its code")
    params = StdioServerParameters(command="sasaah-csi-mcp.exe", args=["--call-timeout-sec", "5"])
    client = Client(stdio_client(params, errlog=sys.stderr), mode="auto", read_timeout_seconds=5)
    expect(client is not None and "read_timeout_seconds" in Client.__dataclass_fields__, "mcp.Client(stdio_client(...)) constructs (mcp 2.x API)")
    expect(s02.main(["--model", "m.EDB", "--server-exe", "s.exe", "--dry-run"]) == 0, "--dry-run runs and exits 0")
    try:
        s02.build_parser().parse_args(["--help"])
    except SystemExit as e:
        expect(e.code == 0, "--help exits 0")
    expect(not (Path("spike-runs")).exists(), "dry run wrote nothing")


def main() -> int:
    check_inventory()
    asyncio.run(check_guard())
    with tempfile.TemporaryDirectory() as d:
        asyncio.run(check_run(Path(d)))
        check_sdk_and_cli(Path(d))
    print(f"\n{'FAILED: ' + str(len(failures)) if failures else 'S-02 check passed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
