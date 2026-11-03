#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["mcp>=2,<3"]
# ///
"""CI check for spike S-04 (CI runs every spikes/*/check.py on Linux; no host program is needed).

It proves that s04_run.py parses and that its logic works (reads, fingerprint, stability, hand-edit differences,
identity read-back, save and reopen), by running it against a STUB session that replays SYNTHETIC replies. The
synthetic replies are invented for this test from the S-12 tool schemas
(spikes/S-12-sasaah-tool-inventory/inventory/sasaah-csi-mcp.json) and from reading the Sasaah sources; they are not
host results. The stub validates every call's arguments against the S-12 input schema. The owner's hand edits are
simulated by the function that answers the script's questions.

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
import s04_run as s04  # noqa: E402

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


class SynthHost:
    """SYNTHETIC ETABS stand-in with a tiny model."""

    KNOWN_TABLES = {
        "Story Definitions", "Point Object Connectivity", "Joint Assignments - Restraints",
        "Frame Assignments - Section Properties", "Frame Assignments - Property Modifiers",
        "Frame Assignments - Releases and Partial Fixity", "Area Assignments - Section Properties",
        "Area Assignments - Thickness Overwrites", "Frame Section Property Definitions - Concrete Rectangular",
        "Slab Property Definitions", "Wall Property Definitions - Specified", "Material Properties - General",
        "Material Properties - Concrete Data", "Frame Loads Assignments - Distributed", "Frame Loads Assignments - Point",
        "Joint Loads Assignments - Force", "Load Pattern Definitions", "Load Combination Definitions", "Project Information",
        # "Area Load Assignments - Uniform" is left out on purpose: an unknown table must show as a failed read
    }

    def __init__(self) -> None:
        self.frames = {f"F{i}": {"p1": [i, 0.0, 0.0], "p2": [i, 0.0, 3.0 + 0.1 + 0.2], "section": "C30X30"} for i in range(1, 5)}
        self.patterns = ["DEAD", "LIVE"]
        self.project_number = ""
        self.reversed_rows = False
        self.shuffle = 0
        self.calls: list[str] = []

    def items(self, kind: str) -> list[dict[str, Any]]:
        if kind == "frames":
            return [{"name": n, "point1": f["p1"], "point2": f["p2"], "section": f["section"], "label": n, "story": "S1"} for n, f in self.frames.items()]
        if kind == "load_patterns":
            return [{"name": p, "type": "Dead"} for p in self.patterns]
        if kind == "load_cases":
            self.shuffle += 1  # flaky ORDER only: the content is the same
            names = ["DEAD", "LIVE"]
            return [{"name": n} for n in (names[::-1] if self.shuffle % 2 else names)]
        if kind == "areas":
            return [{"name": "A1", "points": ["P1", "P2", "P3"], "section": "SLAB"}]
        return [{"name": f"{kind}{i}"} for i in range(1, 3)]

    def table(self, name: str) -> dict[str, Any]:
        cols, rows = ["Name"], [["x"]]
        if name == "Frame Assignments - Section Properties":
            cols, rows = ["Frame", "Section"], [[n, f["section"]] for n, f in self.frames.items()]
        elif name == "Load Pattern Definitions":
            cols, rows = ["Name"], [[p] for p in self.patterns]
        elif name == "Project Information":
            cols, rows = ["ProjectNum"], [[self.project_number]]
        if self.reversed_rows:
            rows = rows[::-1]
        return {"table": name, "columns": cols, "rows": rows, "record_count": len(rows), "returned": len(rows), "truncated": False}

    def handle(self, tool: str, args: dict[str, Any]) -> tuple[bool, Any]:
        self.calls.append(tool)
        if tool in ("csi_launch", "csi_open_model", "csi_save_model", "csi_exit"):
            if tool == "csi_open_model":
                self.reversed_rows = True  # a reopened model lists rows in another order (synthetic assumption)
            return True, {"ok": True}
        if tool == "csi_model_info":
            return True, {"product": "ETABS", "units": "kN_m_C", "program_version": "22.0.0", "model_path": "C:\\Users\\someone\\work\\copy.EDB",
                          "locked": False, "counts": {"points": 8, "frames": len(self.frames), "areas": 1}}
        if tool == "csi_db_table_read":
            if args["table"] not in self.KNOWN_TABLES:
                return False, {"code": "csi_error", "message": "table not found", "data": None}
            return True, self.table(args["table"])
        if tool == "csi_frame_details":
            return True, {"frames": [{"name": n, "modifiers": [1] * 8} for n in args["frames"]], "units": args["units"]}
        if tool == "csi_get_assigned_loads":
            return True, {"object_type": args["object_type"], "name": args["name"], "loads": [], "units": args["units"]}
        kind = tool.removeprefix("csi_list_")
        its = self.items(kind)
        out: dict[str, Any] = {"items": its, "count": len(its), "truncated": False}
        if "units" in TOOLS[tool]["input_schema"]["properties"]:
            out["units"] = args["units"]
        return True, out


class StubSession(s04.Session):
    synthetic = True
    label = "main"

    def __init__(self, host: SynthHost) -> None:
        self.host = host

    async def _call(self, tool: str, args: dict[str, Any], timeout_s: float | None) -> s04.Reply:
        errs = validate_args(tool, args)
        if errs:
            failures.extend(errs)
            return s04.Reply(tool, False, 0.0, "invalid_args", "; ".join(errs), kind="tool_error")
        ok, payload = self.host.handle(tool, args)
        if ok:
            return s04.Reply(tool, True, 0.0, payload=payload, text=json.dumps(payload))
        return s04.Reply(tool, False, 0.0, payload["code"], payload["message"], payload, json.dumps(payload), "tool_error")


def check_inventory_and_guard() -> None:
    expect(s04.ALLOWED_TOOLS <= set(TOOLS), "every tool the script may call exists in the S-12 inventory")
    expect(not any(TOOLS[n]["classification"] == "escape-hatch" for n in s04.ALLOWED_TOOLS), "no allowed tool is an escape hatch")
    expect({n for n, t in TOOLS.items() if t["classification"] == "escape-hatch"} <= s04.FORBIDDEN_TOOLS, "all escape hatches are on the forbidden list")
    expect(not any(TOOLS[n]["classification"] in ("write", "analysis", "design") for n in s04.ALLOWED_TOOLS), "S-04 calls no write, analysis or design tool")
    for tool in ("csi_db_tables_apply", "csi_run_script", "csi_add_point"):
        try:
            asyncio.run(StubSession(SynthHost()).call(tool, {}))
            expect(False, f"{tool} is refused")
        except s04.ForbiddenTool:
            expect(True, f"{tool} is refused")


def check_logic() -> None:
    a = s04.section_fingerprints("x", {"items": [{"name": "a", "v": 0.1 + 0.2}]}, 6)
    b = s04.section_fingerprints("x", {"items": [{"name": "a", "v": 0.3}]}, 6)
    expect(a == b, "fingerprint ignores float noise below the rounding digits")
    c = s04.section_fingerprints("x", {"items": [{"name": "b"}, {"name": "a"}]}, 6)
    d = s04.section_fingerprints("x", {"items": [{"name": "a"}, {"name": "b"}]}, 6)
    expect(c["unordered"] == d["unordered"] and c["ordered"] != d["ordered"], "unordered fingerprint ignores list order, ordered does not")
    mi = s04.section_fingerprints("model_info", {"units": "u", "locked": True, "model_path": "p", "counts": {}}, 6)
    mj = s04.section_fingerprints("model_info", {"units": "u", "locked": False, "model_path": "q", "counts": {}}, 6)
    expect(mi == mj, "session state (lock, path) is not part of the fingerprint")
    df = s04.diff_payloads({"items": [{"name": "F1", "section": "A"}]}, {"items": [{"name": "F1", "section": "B"}, {"name": "F2", "section": "A"}]}, 6)
    expect((df["added"], df["removed"], df["changed"]) == (1, 0, 1), "diff finds an added item and a changed field")
    t = s04.diff_payloads({"rows": [["a", "1"]]}, {"rows": [["a", "2"]]}, 6)
    expect(t["added"] == 1 and t["removed"] == 1, "diff finds a changed table row as removed plus added")


async def check_run(tmp: Path) -> None:
    host = SynthHost()
    model = tmp / "orig.EDB"
    model.write_bytes(b"synthetic model bytes")
    answers = {"edits_done": False}

    def ask(prompt: str) -> str:
        if prompt.startswith("\nPress Enter"):  # the owner edits by hand now (simulated)
            host.frames["F2"]["section"] = "C40X40"
            host.patterns.append("SPIKE_LP")
            host.project_number = next(a for a in [stamp_holder["stamp"]])
            answers["edits_done"] = True
            return ""
        return "y" if prompt.split()[3] in ("E1", "E2", "E9", "E10") else "n"

    stamp_holder: dict[str, str] = {}
    lines: list[str] = []

    def say(text: str) -> None:
        lines.append(text)
        if text.startswith("\nIdentity text for E10: "):
            stamp_holder["stamp"] = text.split("E10: ")[1].splitlines()[0]

    async def factory(label: str, args: list[str]) -> s04.Session:
        return StubSession(host)

    cfg = s04.Config(model, "sasaah-csi-mcp.exe", repeats=3, run_root=tmp)
    rec = await s04.run_spike(cfg, factory, tmp / "S-04-20260101T000000Z", ask, say)
    expect(not rec["errors"], f"run finished without errors {rec['errors']}")
    expect(rec["synthetic"] is True and rec["original_model"]["unchanged"], "record marked synthetic; original untouched")
    expect(rec["timing"]["pass_total"]["n"] == 3 and len(rec["timing"]["per_read"]) >= 30, "every read is timed over all passes")
    expect(rec["timing"]["per_read"]["t:Area Load Assignments - Uniform"]["ok"] is False, "an unknown table shows as a failed read")
    expect("loads:frame:F1" in rec["timing"]["per_read"], "sampled per-object reads are included")
    st = rec["stability"]
    expect(st["all_same_unordered"] is True and st["all_same_ordered"] is False and st["unstable_sections"] == ["load_cases"],
           "stability: order-only change in one section is told apart from a content change")
    he = rec["hand_edits"]
    expect(he["edits_made"] == ["E1", "E2", "E9", "E10"], "edits declared by the owner are recorded")
    noticed = {v["edit"]: v["noticed"] for v in he["verdicts"]}
    expect(noticed == {"E1": True, "E2": True, "E9": False, "E10": True}, f"detected and undetected edits are told apart {noticed}")
    expect(he["undetected"] == ["E9"], "the edit the reads cannot see is listed as undetected")
    expect(he["changed_sections_not_explained_by_a_declared_edit"] == ["load_cases"] or he["changed_sections_not_explained_by_a_declared_edit"] == [],
           "unexplained changes are listed")
    expect(any("F2" in ex for ex in he["comparison"]["sections"]["frames"]["differences"]["examples"]), "the differences name the changed frame")
    ident = rec["identity"]
    expect(ident["stamp_read_back_after_edit"] is True and ident["stamp_read_back_after_reopen"] is True, "hand-written identity is read back, also after reopen")
    sr = rec["save_and_reopen"]
    expect(sr["fingerprint_same_as_before_save"] is True and sr["same_order"] is False, "reopen: same fingerprint, different row order is reported")
    text = (tmp / "S-04-20260101T000000Z" / "record.json").read_text(encoding="utf-8")
    expect(stamp_holder["stamp"] in json.dumps(rec["identity"]["stamp_text"]) and text.count(stamp_holder["stamp"]) == 1,
           "Project Information rows are not written to the record (the stamp appears once, as stamp_text)")
    expect("Users" not in text and "someone" not in text, "record contains no full paths")
    expect("SYNTHETIC" in (tmp / "S-04-20260101T000000Z" / "summary.md").read_text(encoding="utf-8"), "summary says the replies are synthetic")
    expect(not (set(host.calls) & s04.FORBIDDEN_TOOLS) and host.calls.count("csi_exit") == 1, "no escape hatch called; host exited")
    expect(any("DIFFERENCES SEEN" in x for x in lines), "differences are printed to the owner")


def check_cli() -> None:
    expect(s04.main(["--model", "m.EDB", "--server-exe", "s.exe", "--dry-run"]) == 0, "--dry-run runs and exits 0")
    try:
        s04.build_parser().parse_args(["--help"])
    except SystemExit as e:
        expect(e.code == 0, "--help exits 0")
    expect(not Path("spike-runs").exists(), "dry run wrote nothing")


def main() -> int:
    check_inventory_and_guard()
    check_logic()
    with tempfile.TemporaryDirectory() as d:
        asyncio.run(check_run(Path(d)))
    check_cli()
    print(f"\n{'FAILED: ' + str(len(failures)) if failures else 'S-04 check passed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
