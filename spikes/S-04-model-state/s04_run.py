#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["mcp>=2,<3"]
# ///
"""Spike S-04: reading the model state through sasaah-csi-mcp (19 section 2). Run by the owner on the ETABS machine.

    uv run --script s04_run.py --model <model.EDB> --server-exe <sasaah-csi-mcp.exe> [options]
    uv run --script s04_run.py --help
    uv run --script s04_run.py --model <model.EDB> --server-exe <exe> --dry-run

What it does (on a COPY of the model made inside the run folder; the original is hashed before and after):
  1. starts sasaah-csi-mcp over stdio (official MCP Python SDK), launches ETABS through it, opens the copy;
  2. reads the model state the edit kinds of 18 section 2 touch (read tools and read-only table reads), several times,
     and times every read;
  3. computes a fingerprint (SHA-256 over a canonical form) per section and overall; reports whether two reads of
     the same model give the same fingerprint, and which sections differ if not;
  4. PAUSES and asks you to make listed edits by hand in the ETABS window, then reads again and prints the
     differences, and for each edit you say you made whether the reads noticed it;
  5. saves, reopens the copy and reads again (does the fingerprint, and a hand-written identity, survive?).
Identity stamping: no allowlisted tool writes project information (S-12 gap S12-G6), and the table-write tool is an
escape hatch that is never called. So the identity is written by hand (edit E10) and read back with a table read.
Writes record.json and summary.md into the run folder. Everything is "needs local test". Spike code never ships.
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
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SPIKE = "S-04"
SCHEMA_VERSION = 1

# Tools this spike may call (names and arguments: S-12 inventory sasaah-csi-mcp.json). All are reads except the
# session/file tools needed to open, save and reopen the copy.
ALLOWED_TOOLS = frozenset({
    "csi_status", "csi_launch", "csi_exit", "csi_open_model", "csi_save_model", "csi_model_info",
    "csi_list_stories", "csi_list_grids", "csi_list_points", "csi_list_frames", "csi_list_areas",
    "csi_list_materials", "csi_list_frame_sections", "csi_list_area_sections", "csi_list_load_patterns",
    "csi_list_load_cases", "csi_list_load_combos", "csi_db_table_read", "csi_frame_details",
    "csi_get_assigned_loads",
})
FORBIDDEN_TOOLS = frozenset({  # S-12 classification "escape-hatch"; never callable from this code
    "csi_run_script", "csi_db_tables_apply", "csi_invoke", "csi_object_add", "csi_object_delete",
    "csi_object_set", "csi_object_get",
})
# Present-units token: CsiUnits.cs KnownUnits in the Sasaah repository (S-12 report section 4). Used only so that
# every read is made in the same units; the spike does not interpret any value.
DEFAULT_UNITS = "kN_m_C"
_clock: Callable[[], float] = time.perf_counter  # check.py replaces this with a fake clock


class ForbiddenTool(RuntimeError):
    pass


def guard_tool(tool: str, args: dict[str, Any]) -> None:
    if tool in FORBIDDEN_TOOLS:
        raise ForbiddenTool(f"{tool} is an escape-hatch tool and is never called")
    if tool not in ALLOWED_TOOLS:
        raise ForbiddenTool(f"{tool} is not in this spike's list of tools")


# ---------------------------------------------------------------------------------------------------------------
# Shared layer (a deliberate copy of the one in the S-02 script; spikes are standalone)
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
# What is read. Table names: Sasaah docs/csi-mcp-server/reference/etabs22-all-tables.json (ETABS 22 table list).
# A name that this ETABS version does not know shows up as a failed read in the record; that is a finding too.
# ---------------------------------------------------------------------------------------------------------------
LIST_READS = [  # key, tool, takes units, edit kinds (18 section 2) it serves
    ("stories", "csi_list_stories", True, "structure"),
    ("grids", "csi_list_grids", True, "structure"),
    ("points", "csi_list_points", True, "restraints, geometry"),
    ("frames", "csi_list_frames", True, "assign section, geometry"),
    ("areas", "csi_list_areas", True, "thickness, geometry"),
    ("materials", "csi_list_materials", False, "define section"),
    ("frame_sections", "csi_list_frame_sections", False, "define section"),
    ("area_sections", "csi_list_area_sections", False, "define section, thickness"),
    ("load_patterns", "csi_list_load_patterns", False, "load patterns"),
    ("load_cases", "csi_list_load_cases", False, "load patterns"),
    ("load_combos", "csi_list_load_combos", False, "combinations"),
]
TABLE_READS = [  # table name, edit kinds
    ("Story Definitions", "structure"),
    ("Point Object Connectivity", "geometry"),
    ("Joint Assignments - Restraints", "restraints"),
    ("Frame Assignments - Section Properties", "assign section"),
    ("Frame Assignments - Property Modifiers", "define section"),
    ("Frame Assignments - Releases and Partial Fixity", "define section"),
    ("Area Assignments - Section Properties", "thickness"),
    ("Area Assignments - Thickness Overwrites", "thickness"),
    ("Frame Section Property Definitions - Concrete Rectangular", "define section"),
    ("Slab Property Definitions", "define section, thickness"),
    ("Wall Property Definitions - Specified", "define section, thickness"),
    ("Material Properties - General", "define section"),
    ("Material Properties - Concrete Data", "define section"),
    ("Frame Loads Assignments - Distributed", "loads"),
    ("Frame Loads Assignments - Point", "loads"),
    ("Area Load Assignments - Uniform", "loads"),
    ("Joint Loads Assignments - Force", "loads"),
    ("Load Pattern Definitions", "load patterns"),
    ("Load Combination Definitions", "combinations"),
    ("Project Information", "identity"),
]
IDENTITY_TABLE = "t:Project Information"
SENSITIVE_SECTIONS = {IDENTITY_TABLE}  # their rows are never written to the record (client names may be in them)
DROP_KEYS = {"model_path", "locked", "program_version", "program_version_number"}  # session state, not model state

# Hand edits (18 section 2 edit kinds, plus identity). id, text, read keys that should notice it.
EDITS = [
    ("E1", "Change the section of ONE frame to another section that already exists (assign section)", ("frames", "t:Frame Assignments - Section Properties")),
    ("E2", "Add ONE load pattern named SPIKE_LP (load patterns)", ("load_patterns", "t:Load Pattern Definitions")),
    ("E3", "Change the restraint of ONE joint (restraints)", ("points", "t:Joint Assignments - Restraints")),
    ("E4", "Change the thickness of ONE slab or wall section (thickness)", ("area_sections", "t:Slab Property Definitions", "t:Wall Property Definitions - Specified")),
    ("E5", "Assign a distributed load to ONE frame in any pattern (frame load)", ("t:Frame Loads Assignments - Distributed",)),
    ("E6", "Change the concrete strength of ONE material (define material)", ("materials", "t:Material Properties - Concrete Data")),
    ("E7", "Add ONE load combination named SPIKE_COMBO (combination)", ("load_combos", "t:Load Combination Definitions")),
    ("E8", "Move ONE joint by a small distance (geometry)", ("points", "frames", "t:Point Object Connectivity")),
    ("E9", "Set a property modifier on ONE frame (define section)", ("t:Frame Assignments - Property Modifiers", "frame_details")),
    ("E10", "Type the identity text shown below into Project Information, field Project Number (identity)", (IDENTITY_TABLE,)),
]


@dataclass
class Config:
    model: Path
    server_exe: str
    product: str = "ETABS"
    version: str | None = None
    units: str = DEFAULT_UNITS
    repeats: int = 3
    sample_objects: int = 5
    limit: int = 20000
    round_digits: int | None = 6
    long_timeout_sec: int = 600
    skip_edits: bool = False
    skip_reopen: bool = False
    run_root: Path = Path("spike-runs")
    server_args: tuple[str, ...] = ()
    mode: str = "auto"


def build_reads(cfg: Config, sample: dict[str, list[str]]) -> list[dict[str, Any]]:
    """The full list of reads for one pass. sample = names of frames and areas whose per-object data is read."""
    units = {"units": cfg.units}
    reads: list[dict[str, Any]] = [{"key": "model_info", "tool": "csi_model_info", "args": {}, "kinds": "all"}]
    for key, tool, takes_units, kinds in LIST_READS:
        reads.append({"key": key, "tool": tool, "args": {"limit": cfg.limit, **(units if takes_units else {})}, "kinds": kinds})
    for name, kinds in TABLE_READS:
        reads.append({"key": f"t:{name}", "tool": "csi_db_table_read", "args": {"table": name, "row_limit": cfg.limit}, "kinds": kinds})
    if sample.get("frames"):
        reads.append({"key": "frame_details", "tool": "csi_frame_details", "args": {"frames": sample["frames"], **units}, "kinds": "define section"})
    for kind in ("frame", "area"):
        for n in sample.get(f"{kind}s", []):
            reads.append({"key": f"loads:{kind}:{n}", "tool": "csi_get_assigned_loads",
                          "args": {"object_type": kind, "name": n, **units}, "kinds": "loads"})
    return reads


# ---------------------------------------------------------------------------------------------------------------
# Canonical form, fingerprint, differences
# ---------------------------------------------------------------------------------------------------------------
def project(key: str, payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    p = {k: v for k, v in payload.items() if k not in DROP_KEYS}
    return {k: p[k] for k in ("product", "units", "counts") if k in p} if key == "model_info" else p


def rnd(x: Any, nd: int | None) -> Any:
    if isinstance(x, float):
        return x if nd is None else round(x, nd) + 0.0
    if isinstance(x, dict):
        return {k: rnd(v, nd) for k, v in x.items()}
    if isinstance(x, list):
        return [rnd(v, nd) for v in x]
    return x


def cj(x: Any) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def section_fingerprints(key: str, payload: Any, nd: int | None) -> dict[str, str]:
    """ordered: lists keep their order. unordered: lists directly under the payload are sorted first."""
    p = rnd(project(key, payload), nd)
    ordered = hashlib.sha256(cj(p).encode()).hexdigest()
    if isinstance(p, dict):
        q = {k: (sorted(v, key=cj) if isinstance(v, list) else v) for k, v in p.items()}
    else:
        q = p
    return {"ordered": ordered, "unordered": hashlib.sha256(cj(q).encode()).hexdigest()}


def overall(sections: dict[str, dict[str, str]], which: str) -> str:
    return hashlib.sha256(cj({k: v[which] for k, v in sorted(sections.items())}).encode()).hexdigest()


def flatten(x: Any, prefix: str = "", out: dict[str, Any] | None = None) -> dict[str, Any]:
    out = {} if out is None else out
    if isinstance(x, dict):
        for k, v in x.items():
            flatten(v, f"{prefix}/{k}", out)
    elif isinstance(x, list):
        if x and all(isinstance(i, dict) and isinstance(i.get("name"), str) for i in x):
            for i in x:
                flatten({k: v for k, v in i.items() if k != "name"}, f"{prefix}[{i['name']}]", out)
        elif x and all(isinstance(i, list) for i in x):
            counts = Counter(cj(i) for i in x)
            for row, n in counts.items():
                out[f"{prefix}[row {row}]"] = n
        else:
            for n, i in enumerate(x):
                flatten(i, f"{prefix}[{n}]", out)
    else:
        out[prefix] = x
    return out


def diff_payloads(a: Any, b: Any, nd: int | None, limit: int = 40) -> dict[str, Any]:
    fa, fb = flatten(rnd(a, nd)), flatten(rnd(b, nd))
    added = sorted(k for k in fb if k not in fa)
    removed = sorted(k for k in fa if k not in fb)
    changed = sorted(k for k in fa if k in fb and fa[k] != fb[k])
    return {
        "added": len(added), "removed": len(removed), "changed": len(changed),
        "examples": ([f"+ {k}" for k in added[:limit]] + [f"- {k}" for k in removed[:limit]]
                     + [f"~ {k}: {fa[k]!r} -> {fb[k]!r}" for k in changed[:limit]])[:limit],
    }


# ---------------------------------------------------------------------------------------------------------------
# Reading passes
# ---------------------------------------------------------------------------------------------------------------
@dataclass
class ReadPass:
    label: str
    results: dict[str, dict[str, Any]]  # key -> {ok, code, message, elapsed_s, payload (kept in memory only)}
    total_s: float

    def sections(self, nd: int | None) -> dict[str, dict[str, str]]:
        return {k: section_fingerprints(k, r["payload"], nd) for k, r in self.results.items() if r["ok"]}


def item_count(payload: Any) -> int | None:
    if isinstance(payload, dict):
        for k in ("count", "record_count", "returned"):
            if isinstance(payload.get(k), int):
                return payload[k]
    return None


async def read_all(session: Session, cfg: Config, sample: dict[str, list[str]], label: str) -> ReadPass:
    results: dict[str, dict[str, Any]] = {}
    t0 = _clock()
    for rd in build_reads(cfg, sample):
        r = await session.call(rd["tool"], rd["args"], cfg.long_timeout_sec)
        results[rd["key"]] = {"ok": r.ok, "code": r.code, "message": scrub_text(r.message or "")[:200],
                              "elapsed_s": r.elapsed_s, "payload": r.payload if r.ok else None, "kinds": rd["kinds"]}
    return ReadPass(label, results, _clock() - t0)


def pick_sample(first: ReadPass, n: int) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"frames": [], "areas": []}
    for kind in ("frames", "areas"):
        p = first.results.get(kind, {}).get("payload")
        names = sorted(i["name"] for i in p.get("items", []) if isinstance(i, dict) and isinstance(i.get("name"), str)) if isinstance(p, dict) else []
        out[kind] = names[:n]
    return out


def pass_summary(p: ReadPass, nd: int | None) -> dict[str, Any]:
    secs = p.sections(nd)
    return {"label": p.label, "total_s": round(p.total_s, 3), "failed_reads": sorted(k for k, r in p.results.items() if not r["ok"]),
            "fingerprint_unordered": overall(secs, "unordered"), "fingerprint_ordered": overall(secs, "ordered")}


def compare_passes(a: ReadPass, b: ReadPass, nd: int | None) -> dict[str, Any]:
    sa, sb = a.sections(nd), b.sections(nd)
    out: dict[str, Any] = {"same_unordered": overall(sa, "unordered") == overall(sb, "unordered"),
                           "same_ordered": overall(sa, "ordered") == overall(sb, "ordered"), "sections": {}}
    for k in sorted(set(sa) | set(sb)):
        if k not in sa or k not in sb:
            out["sections"][k] = {"only_in": "first" if k in sa else "second"}
        elif sa[k] != sb[k]:
            entry: dict[str, Any] = {"unordered_differs": sa[k]["unordered"] != sb[k]["unordered"],
                                     "order_differs": sa[k]["ordered"] != sb[k]["ordered"]}
            if k in SENSITIVE_SECTIONS:
                entry["differences"] = "rows not recorded (may hold client names)"
            else:
                entry["differences"] = diff_payloads(project(k, a.results[k]["payload"]), project(k, b.results[k]["payload"]), nd)
            out["sections"][k] = entry
    return out


def timing_table(passes: list[ReadPass]) -> dict[str, Any]:
    rows = {}
    for k in passes[0].results:
        times = [p.results[k]["elapsed_s"] for p in passes if k in p.results and p.results[k]["ok"]]
        n = item_count(passes[0].results[k]["payload"])
        s = stats(times)
        if n and times:
            s["items"] = n
            s["median_ms_per_item"] = round(1000 * statistics.median(times) / n, 3)
        s["ok"] = passes[0].results[k]["ok"]
        s["code"] = passes[0].results[k]["code"]
        rows[k] = s
    return {"per_read": rows, "pass_total": stats([p.total_s for p in passes])}


def truncation_warnings(p: ReadPass) -> list[str]:
    return sorted(k for k, r in p.results.items() if r["ok"] and isinstance(r["payload"], dict) and r["payload"].get("truncated"))


# ---------------------------------------------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------------------------------------------
AskFn = Callable[[str], str]


def find_text(payload: Any, needle: str) -> bool:
    return needle in cj(payload)


def _diff_text(v: dict[str, Any]) -> str:
    d = v.get("differences")
    if isinstance(d, str):
        return d
    return f"+{d['added']} -{d['removed']} ~{d['changed']}" if d else str(v)


async def phase_hand_edits(s: Session, cfg: Config, rec: dict[str, Any], base: ReadPass, sample: dict[str, list[str]],
                           ask: AskFn, say: Callable[[str], None], stamp: str) -> ReadPass | None:
    if cfg.skip_edits:
        rec["hand_edits"] = {"skipped": "--skip-edits"}
        return None
    say("\n=== HAND EDITS ===\nIn the ETABS window (the copy opened by this script, never the original), make as many of these\nedits as you can. Skipping some is fine.\n")
    for eid, text, _ in EDITS:
        say(f"  {eid}: {text}")
    say(f"\nIdentity text for E10: {stamp}\nDo not save. Do not run analysis. Do not close ETABS.")
    if ask("\nPress Enter when the edits are done (or type q to skip this phase): ").strip().lower() == "q":
        rec["hand_edits"] = {"skipped": "owner skipped"}
        return None
    after = await read_all(s, cfg, sample, "after hand edits")
    comparison = compare_passes(base, after, cfg.round_digits)
    say("\n=== DIFFERENCES SEEN BY THE READS ===")
    for k, v in comparison["sections"].items():
        say(f"  {k}: {_diff_text(v)}")
        d = v.get("differences")
        if isinstance(d, dict):
            for ex in d["examples"][:6]:
                say(f"      {ex}")
    if not comparison["sections"]:
        say("  (none: the reads saw no difference)")
    made = [eid for eid, text, _ in EDITS if ask(f"Did you make {eid} ({text[:50]}...)? [y/N]: ").strip().lower() == "y"]
    changed = set(comparison["sections"])
    verdicts = []
    expected_all: set[str] = set()
    for eid, _text, keys in EDITS:
        if eid not in made:
            continue
        expected_all |= set(keys)
        hit = [k for k in keys if k in changed or (k == "frame_details" and any(c.startswith(("frame_details", "loads:")) for c in changed))]
        verdicts.append({"edit": eid, "expected_in": list(keys), "noticed_in": hit, "noticed": bool(hit)})
    say("\n=== EDIT BY EDIT ===")
    for v in verdicts:
        say(f"  {v['edit']}: {'NOTICED in ' + ', '.join(v['noticed_in']) if v['noticed'] else 'NOT NOTICED by any read'}")
    rec["hand_edits"] = {"edits_made": made, "verdicts": verdicts, "undetected": [v["edit"] for v in verdicts if not v["noticed"]],
                         "changed_sections_not_explained_by_a_declared_edit": sorted(k for k in changed if k not in expected_all and not k.startswith(("frame_details", "loads:"))),
                         "comparison": comparison, "pass": pass_summary(after, cfg.round_digits)}
    rec["identity"]["hand_stamp_made"] = "E10" in made
    rec["identity"]["stamp_read_back_after_edit"] = find_text(after.results.get(IDENTITY_TABLE, {}).get("payload"), stamp) if "E10" in made else None
    rec["identity"]["identity_table_read_ok"] = after.results.get(IDENTITY_TABLE, {}).get("ok")
    return after


async def run_spike(cfg: Config, open_session: Callable[[str, list[str]], Awaitable[Session]], run_dir: Path,
                    ask: AskFn = input, say: Callable[[str], None] = print) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    nd = cfg.round_digits
    stamp = f"SPIKE-S04-{run_dir.name[-16:]}"
    rec: dict[str, Any] = {
        "spike": SPIKE, "schema": SCHEMA_VERSION, "synthetic": False, "needs_local_test": True,
        "started_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "environment": {"platform": platform.platform(), "python": platform.python_version()},
        "inputs": {"model_file": cfg.model.name, "server_exe": Path(cfg.server_exe).name, "product": cfg.product, "units_requested": cfg.units,
                   "repeats": cfg.repeats, "sample_objects": cfg.sample_objects, "round_digits": nd, "list_and_row_limit": cfg.limit},
        "identity": {"stamp_by_tool": "not possible: no allowlisted tool writes project information (S-12 gap S12-G6); csi_db_tables_apply is an escape hatch and is never called",
                     "stamp_text": stamp},
        "errors": [],
    }
    model_dir = run_dir / "model-copy"
    model_dir.mkdir(exist_ok=True)
    before = sha256_file(cfg.model)
    copy = model_dir / cfg.model.name
    shutil.copy2(cfg.model, copy)
    rec["original_model"] = {"sha256_before": before}
    s: Session | None = None
    try:
        s = await open_session("main", ["--call-timeout-sec", str(cfg.long_timeout_sec), *cfg.server_args])
        rec["synthetic"] = bool(s.synthetic)
        launch_args: dict[str, Any] = {"product": cfg.product, "visible": True}
        if cfg.version:
            launch_args["version"] = cfg.version
        r = await s.call("csi_launch", launch_args)
        rec["launch"] = {"ok": r.ok, "code": r.code, "message": scrub_text(r.message or ""), "elapsed_s": round(r.elapsed_s, 3)}
        if r.ok:
            r = await s.call("csi_open_model", {"path": str(copy), "confirm": True})
            rec["open"] = {"ok": r.ok, "code": r.code, "message": scrub_text(r.message or ""), "elapsed_s": round(r.elapsed_s, 3)}
        if not r.ok:
            raise RuntimeError("host did not start or the copy did not open: see launch and open")
        first = await read_all(s, cfg, {}, "sample finder")
        sample = pick_sample(first, cfg.sample_objects)
        rec["sample"] = {"frames": len(sample["frames"]), "areas": len(sample["areas"])}
        passes = [await read_all(s, cfg, sample, f"baseline {i}") for i in range(1, cfg.repeats + 1)]
        rec["timing"] = timing_table(passes)
        rec["passes"] = [pass_summary(p, nd) for p in passes]
        rec["truncated_reads"] = truncation_warnings(passes[0])
        stability = [compare_passes(passes[0], p, nd) for p in passes[1:]]
        rec["stability"] = {"repeats": cfg.repeats, "all_same_unordered": all(c["same_unordered"] for c in stability),
                            "all_same_ordered": all(c["same_ordered"] for c in stability),
                            "unstable_sections": sorted({k for c in stability for k in c["sections"]}),
                            "details": [c for c in stability if c["sections"]][:1]}
        ident = passes[0].results.get(IDENTITY_TABLE, {})
        rec["identity"]["read_before_ok"] = ident.get("ok")
        rec["identity"]["read_before_code"] = ident.get("code")
        if ident.get("ok") and isinstance(ident["payload"], dict):
            rec["identity"]["columns"] = ident["payload"].get("columns")
        last = passes[0]
        edited = await phase_hand_edits(s, cfg, rec, passes[0], sample, ask, say, stamp)
        if edited is not None:
            last = edited
        if not cfg.skip_reopen:
            sv = await s.call("csi_save_model", {"confirm": True})
            op = await s.call("csi_open_model", {"path": str(copy), "confirm": True}) if sv.ok else sv
            ro: dict[str, Any] = {"save_ok": sv.ok, "save_code": sv.code, "open_ok": op.ok, "open_code": op.code}
            if op.ok:
                re_pass = await read_all(s, cfg, sample, "after save and reopen")
                cmp_ = compare_passes(last, re_pass, nd)
                ro.update({"fingerprint_same_as_before_save": cmp_["same_unordered"], "same_order": cmp_["same_ordered"],
                           "sections_that_differ": cmp_["sections"], "pass": pass_summary(re_pass, nd)})
                if rec["identity"].get("hand_stamp_made"):
                    rec["identity"]["stamp_read_back_after_reopen"] = find_text(re_pass.results.get(IDENTITY_TABLE, {}).get("payload"), stamp)
            rec["save_and_reopen"] = ro
    except ForbiddenTool:
        raise
    except Exception as exc:  # noqa: BLE001
        rec["errors"].append(f"{type(exc).__name__}: {scrub_text(str(exc))[:300]}")
    finally:
        if s is not None:
            ex = await s.call("csi_exit", {"confirm": True})
            rec["exit"] = {"ok": ex.ok, "code": ex.code}
            await s.close()
        after_hash = sha256_file(cfg.model)
        rec["original_model"].update({"sha256_after": after_hash, "unchanged": after_hash == before})
        rec["finished_utc"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        (run_dir / "record.json").write_text(json.dumps(scrub(rec), indent=2, ensure_ascii=False), encoding="utf-8")
        (run_dir / "summary.md").write_text(render_summary(scrub(rec)), encoding="utf-8")
    return rec


def _f(v: Any) -> str:
    return "-" if v is None else str(v)


def render_summary(rec: dict[str, Any]) -> str:
    L = [f"# Spike S-04 run summary{' (SYNTHETIC replies, not a host result)' if rec.get('synthetic') else ''}", "",
         f"Started {rec['started_utc']} UTC, finished {rec.get('finished_utc', '-')} UTC. Record: record.json. Needs local test until the report is written.", "",
         f"- Model file (a copy was used): {rec['inputs']['model_file']}; original unchanged: {rec['original_model'].get('unchanged')}",
         f"- Units requested for reads: {rec['inputs']['units_requested']}; float rounding in the fingerprint: {rec['inputs']['round_digits']} digits (a spike setting, not an engineering value)", ""]
    if rec["errors"]:
        L += ["## Errors (the run did not finish cleanly)", ""] + [f"- {e}" for e in rec["errors"]] + [""]
    t = rec.get("timing")
    if t:
        pt = t["pass_total"]
        L += ["## Time to read the model state", "", f"One full pass: median {pt.get('median_s')} s, min {pt.get('min_s')} s, max {pt.get('max_s')} s over {pt['n']} passes.", "",
              "| Read | ok | items | median s | max s | ms per item |", "|---|---|---|---|---|---|"]
        for k, v in t["per_read"].items():
            L.append(f"| {k} | {v['ok']} {_f(v['code']) if not v['ok'] else ''} | {_f(v.get('items'))} | {_f(v.get('median_s'))} | {_f(v.get('max_s'))} | {_f(v.get('median_ms_per_item'))} |")
        L.append("")
        if rec["truncated_reads"]:
            L += [f"Truncated reads (the fingerprint does not cover everything; raise --limit): {', '.join(rec['truncated_reads'])}", ""]
    st = rec.get("stability")
    if st:
        L += ["## Stability (same model read repeatedly)", "",
              f"- Same fingerprint every time, order ignored: {st['all_same_unordered']}; order included: {st['all_same_ordered']}",
              f"- Sections that differed between reads: {st['unstable_sections'] or 'none'}",
              f"- Fingerprint of the first read (order ignored): {rec['passes'][0]['fingerprint_unordered']}", ""]
    he = rec.get("hand_edits")
    if he:
        L += ["## Edits made by hand", ""]
        if "skipped" in he:
            L.append(f"- Skipped: {he['skipped']}")
        else:
            L += [f"- Edits you said you made: {', '.join(he['edits_made']) or 'none'}", f"- NOT noticed by any read: {he['undetected'] or 'none'}",
                  f"- Sections that changed without a matching declared edit: {he['changed_sections_not_explained_by_a_declared_edit'] or 'none'}", "",
                  "| Edit | noticed | in |", "|---|---|---|"]
            L += [f"| {v['edit']} | {v['noticed']} | {', '.join(v['noticed_in']) or '-'} |" for v in he["verdicts"]]
            L += ["", "Differences by section:", ""]
            for k, v in he["comparison"]["sections"].items():
                L.append(f"- {k}: {_diff_text(v)}")
                d = v.get("differences")
                if isinstance(d, dict):
                    L += [f"    - {ex}" for ex in d["examples"][:5]]
        L.append("")
    ident = rec["identity"]
    L += ["## Identity (project information)", "", f"- Stamp with a tool: {ident['stamp_by_tool']}",
          f"- Project Information read before: ok={_f(ident.get('read_before_ok'))} {_f(ident.get('read_before_code'))}; columns: {_f(ident.get('columns'))}",
          f"- Hand stamp made: {_f(ident.get('hand_stamp_made'))}; read back after the edit: {_f(ident.get('stamp_read_back_after_edit'))}; after save and reopen: {_f(ident.get('stamp_read_back_after_reopen'))}", ""]
    sr = rec.get("save_and_reopen")
    if sr:
        L += ["## Save and reopen", "", f"- Save ok: {sr['save_ok']} {_f(sr['save_code'])}; reopen ok: {sr['open_ok']} {_f(sr['open_code'])}",
              f"- Fingerprint same as before save: {_f(sr.get('fingerprint_same_as_before_save'))} (order included: {_f(sr.get('same_order'))})",
              f"- Sections that differ: {list(sr.get('sections_that_differ', {})) or 'none'}", ""]
    L += ["Send record.json and this file back. Check that no client or project name appears before you send them.", ""]
    return "\n".join(L)


# ---------------------------------------------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="s04_run.py", description="Spike S-04: reading the model state through sasaah-csi-mcp, on a copy of a model.",
                                epilog="Needs ETABS on this machine. Everything it measures is a local result. See README.md.")
    p.add_argument("--model", type=Path, required=True, help="the ETABS model to test; it is copied, never changed")
    p.add_argument("--server-exe", required=True, help="path to sasaah-csi-mcp (the exe built from Sasaah)")
    p.add_argument("--product", default="ETABS", help="product for csi_launch (default ETABS)")
    p.add_argument("--version", default=None, help="product version for csi_launch")
    p.add_argument("--units", default=DEFAULT_UNITS, help=f"units token for unit-aware reads (default {DEFAULT_UNITS})")
    p.add_argument("--repeats", type=int, default=3, help="number of baseline reads, at least 2 (default 3)")
    p.add_argument("--sample-objects", type=int, default=5, help="frames and areas whose per-object details and loads are read (default 5)")
    p.add_argument("--limit", type=int, default=20000, help="item and row limit of list and table reads (default 20000)")
    p.add_argument("--round-digits", type=int, default=6, help="decimals kept for numbers in the fingerprint; -1 keeps all (default 6)")
    p.add_argument("--long-timeout-sec", type=int, default=600, help="call timeout of the server (default 600)")
    p.add_argument("--skip-edits", action="store_true", help="skip the pause for hand edits")
    p.add_argument("--skip-reopen", action="store_true", help="skip save and reopen")
    p.add_argument("--run-root", type=Path, default=Path("spike-runs"), help="folder for run folders (default ./spike-runs)")
    p.add_argument("--server-arg", action="append", default=[], help="extra argument for the server (repeatable)")
    p.add_argument("--mode", default="auto", help="MCP connect mode of the SDK client (auto or legacy)")
    p.add_argument("--dry-run", action="store_true", help="print the plan; start nothing, copy nothing, write nothing")
    return p


def config_from_args(a: argparse.Namespace) -> Config:
    if a.repeats < 2:
        raise SystemExit("--repeats must be at least 2 (stability needs two reads)")
    return Config(a.model, a.server_exe, a.product, a.version, a.units, a.repeats, a.sample_objects, a.limit,
                  None if a.round_digits < 0 else a.round_digits, a.long_timeout_sec, a.skip_edits, a.skip_reopen,
                  a.run_root, tuple(a.server_arg), a.mode)


def dry_run_text(cfg: Config) -> str:
    one = {"frames": ["<frame>"], "areas": ["<area>"]} if cfg.sample_objects else {}
    reads = build_reads(cfg, one)
    L = ["DRY RUN: nothing is started, copied or written.",
         f"Model file : {cfg.model.name} ({'found' if cfg.model.is_file() else 'NOT FOUND'}); copied into the run folder; the original is only hashed.",
         f"Server     : {Path(cfg.server_exe).name} ({'found' if Path(cfg.server_exe).is_file() else 'NOT FOUND'}) over stdio.",
         f"Run folder : {cfg.run_root}/S-04-<UTC time>/  (record.json, summary.md, model-copy/, server log)",
         f"Plan: csi_launch (visible), csi_open_model on the copy, then {cfg.repeats} baseline passes of {len(reads)} reads"
         f" (the per-object lines below repeat for up to {cfg.sample_objects} frames and {cfg.sample_objects} areas):"]
    L += [f"  {r['key']:<62} {r['tool']}  [{r['kinds']}]" for r in reads]
    L += ["Then " + ("no hand-edit pause (--skip-edits)." if cfg.skip_edits else "a PAUSE for these hand edits in the ETABS window:")]
    if not cfg.skip_edits:
        L += [f"  {eid}: {text}" for eid, text, _ in EDITS]
    L += ["Then " + ("no save and reopen." if cfg.skip_reopen else "csi_save_model, csi_open_model, one more pass; csi_exit."),
          "Tools that may be called: " + ", ".join(sorted(ALLOWED_TOOLS)), "Never called (escape hatches): " + ", ".join(sorted(FORBIDDEN_TOOLS))]
    return "\n".join(L)


async def main_async(cfg: Config) -> int:
    if not cfg.model.is_file():
        print(f"error: model file not found: {cfg.model.name}", file=sys.stderr)
        return 2
    if not Path(cfg.server_exe).is_file():
        print(f"error: server executable not found: {Path(cfg.server_exe).name}", file=sys.stderr)
        return 2
    run_dir = (cfg.run_root / f"S-04-{dt.datetime.now(dt.UTC).strftime('%Y%m%dT%H%M%SZ')}").resolve()
    if cfg.model.resolve().is_relative_to(run_dir):
        print("error: the run folder must not contain the model", file=sys.stderr)
        return 2
    run_dir.mkdir(parents=True, exist_ok=True)

    async def factory(label: str, args: list[str]) -> Session:
        return await McpSession(label, cfg.server_exe, args, run_dir / f"server-{label}.stderr.log", cfg.mode).open()

    print(f"Run folder: {run_dir}")
    rec = await run_spike(cfg, factory, run_dir)
    print((run_dir / "summary.md").read_text(encoding="utf-8"))
    print(f"\nSend back: {run_dir / 'record.json'} and {run_dir / 'summary.md'}")
    return 1 if rec["errors"] else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = config_from_args(args)
    if args.dry_run:
        print(dry_run_text(cfg))
        return 0
    return asyncio.run(main_async(cfg))


if __name__ == "__main__":
    sys.exit(main())
