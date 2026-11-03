#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Throwaway extractor for spike S-12: Sasaah tool inventory from C# catalog sources.

Usage:
    uv run --script extract.py --sasaah <path to a Sasaah checkout> [--out inventory]

It reads the C# catalogs as text (static reading, nothing is compiled or run), evaluates the small
subset of C# that the catalogs use (string literals of every kind, interpolation, '+', and the
WithTarget/Plain helpers), and writes four JSON files. It never modifies the Sasaah checkout.
Spike code never ships (design/docs/architecture/19-roadmap-and-spikes.md).

The classification tables below are the spike author's judgement and are the only non-extracted
content; every entry that uses them says so in its "notes".
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EXPECTED_COMMIT = "61da80f61a6562c8e3553168056bc107e3f93013"
STATIC_NOTE = (
    "Built by static reading of the C# catalog sources with extract.py; nothing was run against a "
    "host. Compare with the live tools/list of the pinned build (needs local test)."
)

# ----------------------------------------------------------------------------------------------
# C# tokenizer and expression evaluator (subset)
# ----------------------------------------------------------------------------------------------


@dataclass
class Tok:
    kind: str  # STR, ID, P (punctuation)
    val: str
    line: int
    dollars: int = 0  # for STR: number of leading '$'
    raw_kind: str = ""  # "regular", "verbatim", "raw"


ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "0": "\0", "'": "'"}


def _unescape(body: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            n = body[i + 1]
            if n == "u" and i + 5 < len(body) + 0:
                out.append(chr(int(body[i + 2 : i + 6], 16)))
                i += 6
                continue
            out.append(ESCAPES.get(n, n))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def tokenize(src: str) -> list[Tok]:
    toks: list[Tok] = []
    i, n, line = 0, len(src), 1
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c.isspace():
            i += 1
            continue
        if src.startswith("//", i):
            while i < n and src[i] != "\n":
                i += 1
            continue
        if src.startswith("/*", i):
            j = src.index("*/", i + 2)
            line += src.count("\n", i, j)
            i = j + 2
            continue
        m = re.compile(r'(\$*)(@?)(\$*)"').match(src, i)
        if m and (m.group(1) or m.group(2) or m.group(3) or c == '"'):
            dollars = len(m.group(1)) + len(m.group(3))
            verbatim = bool(m.group(2))
            q = m.end() - 1  # index of first quote
            run = 0
            while q + run < n and src[q + run] == '"':
                run += 1
            start_line = line
            if run >= 3 and not verbatim:  # raw string literal
                delim = '"' * run
                after = q + run
                eol = src.find("\n", after)
                multiline = eol != -1 and src[after:eol].strip() == ""
                end = src.index(delim, after)
                # a longer run of quotes closes with the whole run; take the first match of exactly delim
                body = src[after:end]
                if multiline:
                    lines = body.split("\n")
                    indent = lines[-1]  # whitespace before the closing delimiter
                    content = [ln[len(indent):] if ln.startswith(indent) else ln.lstrip() for ln in lines[1:-1]]
                    val = "\n".join(content)
                else:
                    val = body
                toks.append(Tok("STR", val, start_line, dollars, "raw"))
                line += src.count("\n", i, end + run)
                i = end + run
                continue
            # regular or verbatim string
            j = q + 1
            buf_start = j
            while j < n:
                if verbatim:
                    if src[j] == '"':
                        if j + 1 < n and src[j + 1] == '"':
                            j += 2
                            continue
                        break
                else:
                    if src[j] == "\\":
                        j += 2
                        continue
                    if src[j] == '"':
                        break
                j += 1
            body = src[buf_start:j]
            val = body.replace('""', '"') if verbatim else _unescape(body)
            toks.append(Tok("STR", val, start_line, dollars, "verbatim" if verbatim else "regular"))
            line += src.count("\n", i, j)
            i = j + 1
            continue
        if c == "'":  # char literal
            j = i + 1
            while src[j] != "'":
                j += 2 if src[j] == "\\" else 1
            toks.append(Tok("STR", _unescape(src[i + 1 : j]), line, 0, "regular"))
            i = j + 1
            continue
        m = re.compile(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*").match(src, i)
        if m:
            toks.append(Tok("ID", m.group(0), line))
            i = m.end()
            continue
        m = re.compile(r"\d+(?:\.\d+)?").match(src, i)
        if m:
            toks.append(Tok("NUM", m.group(0), line))
            i = m.end()
            continue
        toks.append(Tok("P", c, line))
        i += 1
    return toks


class Parser:
    """Recursive descent over tokens for: expr := term ('+' term)*, term := STR | ID | ID '(' args ')' | '(' expr ')'."""

    def __init__(self, toks: list[Tok], pos: int = 0):
        self.t = toks
        self.p = pos

    def peek(self) -> Tok | None:
        return self.t[self.p] if self.p < len(self.t) else None

    def eat(self, val: str) -> None:
        tok = self.peek()
        if tok is None or tok.val != val or tok.kind not in ("P", "ID"):
            raise ValueError(f"expected {val!r} at line {tok.line if tok else '?'}, got {tok}")
        self.p += 1

    def expr(self):
        node = self.term()
        while (tok := self.peek()) and tok.kind == "P" and tok.val == "+":
            self.p += 1
            node = ("cat", node, self.term())
        return node

    def term(self):
        tok = self.peek()
        if tok is None:
            raise ValueError("unexpected end")
        if tok.kind == "STR":
            self.p += 1
            return ("str", tok)
        if tok.kind == "NUM":
            self.p += 1
            return ("num", tok.val)
        if tok.kind == "ID":
            self.p += 1
            nxt = self.peek()
            if nxt and nxt.kind == "P" and nxt.val == "(":
                self.p += 1
                args = []
                if not (self.peek().kind == "P" and self.peek().val == ")"):
                    args.append(self.expr())
                    while self.peek().kind == "P" and self.peek().val == ",":
                        self.p += 1
                        args.append(self.expr())
                self.eat(")")
                return ("call", tok.val, args)
            return ("id", tok.val)
        if tok.kind == "P" and tok.val == "(":
            self.p += 1
            node = self.expr()
            self.eat(")")
            return node
        raise ValueError(f"unexpected token {tok} at line {tok.line}")


class Evaluator:
    def __init__(self, consts: dict[str, str], funcs: dict):
        self.consts = consts
        self.funcs = funcs

    def ev(self, node) -> str:
        kind = node[0]
        if kind == "str":
            return self.interp(node[1])
        if kind == "num":
            return node[1]
        if kind == "id":
            name = node[1]
            if name in self.consts:
                return self.consts[name]
            if name in ("string.Empty",):
                return ""
            raise KeyError(f"unknown identifier {name}")
        if kind == "cat":
            return self.ev(node[1]) + self.ev(node[2])
        if kind == "call":
            fn = self.funcs[node[1]]
            return fn(*[self.ev(a) for a in node[2]])
        raise ValueError(node)

    def interp(self, tok: Tok) -> str:
        if tok.dollars == 0:
            return tok.val
        d = tok.dollars
        pat = re.compile(r"\{" * d + r"\s*([A-Za-z_][A-Za-z_0-9]*)\s*" + r"\}" * d)
        return pat.sub(lambda m: self.consts[m.group(1)], tok.val)


def split_args(toks: list[Tok], open_idx: int) -> tuple[list[list[Tok]], int]:
    """Given index of '(' return (list of token lists per top-level argument, index after ')')."""
    depth = 0
    args: list[list[Tok]] = [[]]
    i = open_idx
    while i < len(toks):
        t = toks[i]
        if t.kind == "P" and t.val in "([{":
            depth += 1
            if depth > 1:
                args[-1].append(t)
        elif t.kind == "P" and t.val in ")]}":
            depth -= 1
            if depth == 0:
                return ([a for a in args if a] if args != [[]] else []), i + 1
            args[-1].append(t)
        elif t.kind == "P" and t.val == "," and depth == 1:
            args.append([])
        else:
            args[-1].append(t)
        i += 1
    raise ValueError("unbalanced parentheses")


def eval_tokens(ev: Evaluator, arg: list[Tok]) -> str:
    p = Parser(arg)
    node = p.expr()
    if p.p != len(arg):
        raise ValueError(f"trailing tokens in argument at line {arg[p.p].line}")
    return ev.ev(node)


def collect_consts(toks: list[Tok]) -> dict[str, str]:
    """Collect 'const string NAME = <string literal>;' definitions (regular or raw strings)."""
    consts: dict[str, str] = {}
    for i, t in enumerate(toks):
        if t.kind == "ID" and t.val == "string" and i + 3 < len(toks):
            name, eq, lit = toks[i + 1], toks[i + 2], toks[i + 3]
            if name.kind == "ID" and eq.val == "=" and lit.kind == "STR" and lit.dollars == 0:
                if i > 0 and toks[i - 1].val == "const":
                    consts[name.val] = lit.val
    return consts


# ----------------------------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------------------------


def sasaah_commit(root: Path) -> str:
    head = (root / ".git" / "HEAD").read_text().strip()
    if head.startswith("ref:"):
        ref = head.split(" ", 1)[1]
        p = root / ".git" / ref
        if p.exists():
            return p.read_text().strip()
        packed = root / ".git" / "packed-refs"
        for ln in packed.read_text().splitlines():
            if ln.endswith(" " + ref):
                return ln.split()[0]
    return head


def rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


def write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def schema_props(schema: dict) -> dict:
    return schema.get("properties", {}) if isinstance(schema, dict) else {}


# ----------------------------------------------------------------------------------------------
# Judgement tables (author's classification; not extracted from the sources)
# ----------------------------------------------------------------------------------------------

CLASSES = {"read", "write", "analysis", "design", "session", "file", "escape-hatch"}

CSI_ESCAPE = {
    "csi_run_script": "Compiles and runs C# against the live model (kind Code).",
    "csi_db_tables_apply": "Writes database tables directly through ApplyEditedTables (kind Write; NOT hidden by DisableScript).",
    "csi_invoke": "Generic late-bound invoke on an allowlisted path list (needs --enable-generic-invoke).",
    "csi_object_add": "Generic object add by object_type and free method name (needs --enable-generic-invoke).",
    "csi_object_delete": "Generic object delete (needs --enable-generic-invoke).",
    "csi_object_set": "Generic setter by free method name (needs --enable-generic-invoke).",
    "csi_object_get": "Generic getter by free method name (needs --enable-generic-invoke); read-only but part of the generic family.",
}
CSI_SESSION = {"csi_status", "csi_attach", "csi_detach", "csi_launch", "csi_exit", "csi_refresh_view"}
CSI_FILE = {"csi_save_model", "csi_open_model", "csi_new_blank_model", "csi_new_model", "csi_export_joint"}
CSI_ANALYSIS = {"csi_run_analysis"}
CSI_DESIGN = {"csi_design_run"}
CSI_TOOLSET = {
    "analysis": {"csi_run_analysis", "csi_analysis_status"},
    "design": {
        "csi_design_run", "csi_design_results", "csi_list_design_combos", "csi_get_design_code",
        "csi_set_design_code", "csi_design_prefs_get", "csi_design_prefs_set",
    },
    "results": {
        "csi_results_joint_reactions", "csi_results_frame_forces", "csi_results_story_drifts",
        "csi_results_base_reactions", "csi_results_joint_displacements", "csi_results_frame_joint_forces",
        "csi_results_area_forces", "csi_results_link_forces", "csi_results_modal_periods",
        "csi_results_displacements_envelope",
    },
    "database_tables": {"csi_db_tables_list", "csi_db_table_read", "csi_db_table_fields", "csi_db_tables_apply"},
    "generic_invoke": {"csi_invoke", "csi_object_add", "csi_object_delete", "csi_object_set", "csi_object_get"},
    "script": {"csi_run_script"},
    "session": {"csi_status", "csi_attach", "csi_detach", "csi_launch", "csi_exit", "csi_refresh_view", "csi_get_selection", "csi_capture_window"},
    "file": {"csi_save_model", "csi_open_model", "csi_new_blank_model", "csi_new_model", "csi_export_joint"},
}
# Tools whose value arguments or results follow the model's PRESENT units with no per-call override.
CSI_UNSCOPED_QUANTITIES = {
    "csi_move_area": "dx, dy, dz are in the model's present length unit; no 'units' parameter.",
    "csi_define_material": "spec values are API parameters in the present units; no 'units' parameter.",
    "csi_define_frame_section": "spec values (dimensions) are API parameters in the present units; no 'units' parameter.",
    "csi_define_area_section": "spec values (thickness) are API parameters in the present units; no 'units' parameter.",
    "csi_define_load_case": "spec values are API parameters in the present units; no 'units' parameter.",
    "csi_set_frame_releases": "start_values/end_values (partial-fixity springs) are in the present units; no 'units' parameter.",
    "csi_get_assigned_loads": "results are in the present units; the schema declares 'units' but the dispatch ignores it (see notes).",
    "csi_add_load_pattern": "self_weight is a dimensionless multiplier; no units involved.",
    "csi_set_point_restraint": "no quantities.",
}
# Edit-kind relevance tags used by the report (hand-curated; the report holds the reasoning).
CSI_CYCLE_STEPS = {
    "csi_status": [1], "csi_launch": [2], "csi_open_model": [2], "csi_save_model": [2, 7, 10, 16],
    "csi_model_info": [3, 9], "csi_list_frames": [3, 9], "csi_list_areas": [3, 9], "csi_list_points": [3],
    "csi_list_frame_sections": [3], "csi_list_area_sections": [3], "csi_list_materials": [3],
    "csi_list_load_patterns": [3], "csi_list_load_cases": [3], "csi_list_load_combos": [3],
    "csi_frame_details": [3, 9], "csi_get_assigned_loads": [3, 9], "csi_db_table_read": [3, 9],
    "csi_assign_frame_section": [8], "csi_assign_area_section": [8], "csi_define_frame_section": [8],
    "csi_define_area_section": [8], "csi_define_wall_section": [8], "csi_define_material": [8],
    "csi_set_frame_load_distributed": [8], "csi_set_area_load_uniform": [8],
    "csi_set_frame_load_point": [8], "csi_add_load_pattern": [8], "csi_add_load_combo": [8],
    "csi_delete_load_combo": [8], "csi_define_load_case": [8], "csi_set_point_restraint": [8],
    "csi_run_analysis": [11], "csi_analysis_status": [11, 13], "csi_design_run": [12],
    "csi_design_results": [13], "csi_results_story_drifts": [13], "csi_results_base_reactions": [13],
    "csi_results_joint_reactions": [13], "csi_results_frame_forces": [13],
    "csi_results_joint_displacements": [13], "csi_results_modal_periods": [13],
}


def classify_csi(name: str, kind: str) -> tuple[str, str]:
    if name in CSI_ESCAPE:
        return "escape-hatch", next(k for k, v in CSI_TOOLSET.items() if name in v)
    toolset = next((k for k, v in CSI_TOOLSET.items() if name in v), None)
    if name in CSI_SESSION:
        return "session", toolset or "session"
    if name in CSI_FILE:
        return "file", toolset or "file"
    if name in CSI_ANALYSIS:
        return "analysis", toolset or "analysis"
    if name in CSI_DESIGN:
        return "design", toolset or "design"
    if kind in ("Meta", "Read"):
        return "read", toolset or ("model_read" if name.startswith(("csi_list_", "csi_model", "csi_point", "csi_frame", "csi_get")) else "model_read")
    if name == "csi_unlock_model":
        return "write", "model_edit"
    return "write", toolset or "model_edit"


# ----------------------------------------------------------------------------------------------
# CSI
# ----------------------------------------------------------------------------------------------


def analyse_csi_dispatch(service_src: str) -> dict[str, dict]:
    """Which tools apply the 'units' argument, from the CsiToolService.ExecuteCore switch."""
    start = service_src.index("return name switch")
    end = service_src.index("_ => throw new CsiToolException", start)
    body = service_src[start:end]
    entries: dict[str, str] = {}
    cur = None
    for ln in body.splitlines():
        m = re.match(r'\s+"(csi_[a-z_]+)"\s*=>', ln)
        if m:
            cur = m.group(1)
            entries[cur] = ln
        elif cur:
            entries[cur] += "\n" + ln
    helper_units = {"Results(", "FrameDetails(", "FrameJointForces(", "DbTablesApply(", "NewModel("}
    # verify the helpers really scope units (guards the assumption above against source drift)
    for helper in ("Results", "FrameDetails", "FrameJointForces", "DbTablesApply", "NewModel"):
        m = re.search(r"private JsonObject %s\(.*?\n    }\n" % helper, service_src, re.S)
        if not m or 'WithUnits(args["units"]' not in m.group(0):
            raise SystemExit(f"extract.py: helper {helper} no longer scopes units; update the analysis")
    out: dict[str, dict] = {}
    for name, text in entries.items():
        if 'WithUnits(args["units"]' in text or "units: true" in text or any(re.search(r"(?<![A-Za-z])" + re.escape(h), text) for h in helper_units):
            out[name] = {"mechanism": "scoped_set_restore", "line_hint": text.splitlines()[0].strip()[:60]}
        elif "ExportJoint(" in text:
            out[name] = {"mechanism": "fixed_internal_scope", "units": "kN_m_C"}
        else:
            out[name] = {"mechanism": "none"}
    return out


def csi_inventory(root: Path, commit: str) -> dict:
    path = root / "02_Engines/Sasaah.Csi.Engine/CsiToolCatalog.cs"
    src = path.read_text(encoding="utf-8")
    toks = tokenize(src)
    consts = collect_consts(toks)

    def locate_template(fn: str) -> Tok:
        for i, t in enumerate(toks):
            if t.kind == "ID" and t.val == fn and i > 0 and toks[i - 1].val == "string":
                for u in toks[i:]:
                    if u.kind == "STR" and u.dollars == 2:
                        return u
        raise SystemExit(f"{fn} template not found")

    with_target_tpl = locate_template("WithTarget")
    assert 'var inner = string.IsNullOrWhiteSpace(props) ? string.Empty : props + ",";' in src

    def with_target(props: str) -> str:
        inner = "" if not props.strip() else props + ","
        return re.sub(r"\{\{(inner|TargetProp)\}\}", lambda m: {"inner": inner, "TargetProp": consts["TargetProp"]}[m.group(1)], with_target_tpl.val)

    ev = Evaluator(consts, {"WithTarget": with_target})
    service_src = (root / "02_Engines/Sasaah.Csi.Engine/CsiToolService.cs").read_text(encoding="utf-8")
    units = analyse_csi_dispatch(service_src)
    dry_run_tools = set(re.findall(r'"(csi_[a-z_]+)"', service_src[service_src.index("DryRunTools = new"): service_src.index("private static bool IsDryRun")]))
    # attached-write blocks and always-rejected-on-bridge sets, read from CsiBridgePolicy.cs
    policy = (root / "02_Engines/Sasaah.Csi.Engine/CsiBridgePolicy.cs").read_text(encoding="utf-8")
    always_rejected = set(re.findall(r'"(csi_[a-z_]+)"', policy[policy.index("AlwaysRejected = new"): policy.index("AttachedWriteBlocked = new")]))
    attached_blocked = set(re.findall(r'"(csi_[a-z_]+)"', policy[policy.index("AttachedWriteBlocked = new"): policy.index("/// <summary>True when a write")]))
    generic = set(re.findall(r'"(csi_[a-z_]+)"', src[src.index("IsGenericInvokeTool"): src.index("public static IReadOnlyList<CsiToolDef> Visible")]))
    confirm_tools = set()

    tools = []
    for i, t in enumerate(toks):
        if not (t.kind == "ID" and t.val == "new" and i + 2 < len(toks) and toks[i + 1].val == "(" and toks[i + 2].kind == "STR" and toks[i + 2].val.startswith("csi_")):
            continue
        args, _ = split_args(toks, i + 1)
        name = eval_tokens(ev, args[0])
        desc = eval_tokens(ev, args[1])
        schema_text = eval_tokens(ev, args[2])
        kind = args[3][0].val.split(".")[-1]
        schema = json.loads(schema_text)
        cls, toolset = classify_csi(name, kind)
        props = schema_props(schema)
        has_units_param = "units" in props
        u = units.get(name, {"mechanism": "none"})
        applied = u["mechanism"] in ("scoped_set_restore", "fixed_internal_scope")
        notes: list[str] = []
        if has_units_param and not applied:
            notes.append("Schema declares a 'units' property but the dispatch in CsiToolService.cs does not apply it (declared, ignored): results/values are in the model's present units.")
        if name in CSI_UNSCOPED_QUANTITIES and CSI_UNSCOPED_QUANTITIES[name] not in notes:
            notes.append("Units: " + CSI_UNSCOPED_QUANTITIES[name])
        escape = name in CSI_ESCAPE
        exclusion = CSI_ESCAPE.get(name, "")
        if name in ("csi_define_material", "csi_define_frame_section", "csi_define_area_section", "csi_define_load_case"):
            notes.append("Untyped 'spec' object with a free 'method' member name on a fixed owner (PropMaterial/PropFrame/PropArea/LoadCases) via CsiModel.LateSpec: partly generic. Allow only with the adapter pinning 'method' to a fixed list and validating spec keys (owner-queue decision, report section 8).")
        if name == "csi_delete_object":
            notes.append("Generic over object_type (point|frame|area|link|solid) but typed to Delete; on the always-ask list (delete). Not needed by the edit cycle.")
        if name == "csi_export_joint":
            notes.append("Classified read by the server but writes a bundle file at out_path; switches present units to kN_m_C internally (CsiModel.cs ExportJoint).")
        if name == "csi_run_analysis":
            notes.append("Synchronous: CsiModel.RunAnalysis blocks the single STA worker until Analyze.RunAnalysis returns; result {started:true} is returned only after it finishes. Does not save and does not detect dialogs (baseline REPORT section 5.1).")
        if name == "csi_analysis_status":
            notes.append("Returns raw per-case status_code integers (meaning not decoded by the server). On a COM target it queues on the same STA worker as a running analysis, so it cannot report progress of a call in flight (needs local test).")
        if name == "csi_design_run":
            notes.append("Synchronous StartDesign for steel or concrete; aluminum/coldformed report unsupported_by_version. EnsureNotLocked exempts it (analysis results needed).")
        timeout = {
            "default_seconds": 120,
            "source": "04_Deployments/Sasaah.Mcp.Csi.Server/CsiServerConfig.cs:18 and 02_Engines/Sasaah.Csi.Engine/CsiModels.cs:80",
            "option": "--call-timeout-sec / SASAAH_CSI_CALL_TIMEOUT_SEC",
            "declared_per_tool": False,
            "applies_to": "the whole COM call (ComThread.Invoke) of the tool; no per-tool value exists",
        }
        if name == "csi_run_script":
            timeout["script_timeout_option"] = "--script-timeout-sec is parsed (CsiServerConfig.cs:20) but never passed to the engine options; the script runs under the call timeout"
        if name in ("csi_status", "csi_attach", "csi_detach", "csi_launch", "csi_exit"):
            timeout["applies_to"] = "session/launch calls use the same call timeout (CsiSession.cs Attach/Launch/ExitLaunchedInstance)"
        reg = {
            "name": name,
            "description": desc,
            "toolset": toolset,
            "input_schema": schema,
            "declared_annotations": {
                "readOnlyHint": kind in ("Meta", "Read"),
                "destructiveHint": kind in ("Destructive", "Code"),
                "idempotentHint": kind in ("Meta", "Read"),
                "openWorldHint": False,
                "derived_from": "Program.cs:71-77 (annotations are computed from the catalog kind; there is no per-tool annotation)",
            },
            "server_kind": kind,
            "classification": cls,
            "changes_host_units": {
                "mechanism": u["mechanism"],
                "units_param_declared": has_units_param,
                "applied": applied,
                "fixed_units": u.get("units"),
                "restore_checked": False if applied else None,
                "restore_note": "Restore is SetPresentUnits(previous) in a finally block; the return code is not checked, only exceptions are logged to stderr, and nothing re-reads the units (CsiModel.cs:51-70)." if applied else None,
                "quantities_follow_present_units": name in CSI_UNSCOPED_QUANTITIES or (has_units_param and not applied),
            },
            "confirm_required": bool(re.search(r"confirm", json.dumps(props))) or kind == "Destructive",
            "dry_run": name in dry_run_tools,
            "hidden_by": {
                "read_only": kind in ("Write", "Destructive", "Code"),
                "disable_script": kind == "Code",
                "needs_enable_generic_invoke": name in generic,
            },
            "bridge_target_policy": ("always rejected on a bridge target (CsiBridgePolicy.cs)" if name in always_rejected else ("refused on an attached target unless --allow-attached-writes" if name in attached_blocked else None)),
            "timeout": timeout,
            "cycle_steps": CSI_CYCLE_STEPS.get(name, []),
            "source": {"file": rel(root, path), "line": t.line},
            "excluded_from_allowlist": escape,
            "exclusion_reason": exclusion,
            "notes": notes,
        }
        tools.append(reg)
    server = {
        "executable": "sasaah-csi-mcp (AssemblyName in 04_Deployments/Sasaah.Mcp.Csi.Server/Sasaah.Mcp.Csi.Server.csproj)",
        "transport": "stdio, JSON-RPC (Program.cs:26, StdioMcpServerHost.cs)",
        "mcp_sdk": "ModelContextProtocol 1.1.0 (csproj)",
        "start_options": {
            "--read-only": "hides Write, Destructive and Code tools (Visible())",
            "--enable-script / SASAAH_CSI_ENABLE_SCRIPT": "csi_run_script is opt-in; DisableScript defaults to true (CsiServerConfig.cs:14)",
            "--disable-script / SASAAH_CSI_DISABLE_SCRIPT": "forces scripts off",
            "--enable-generic-invoke": "shows csi_invoke and csi_object_* (default off)",
            "--allow-attached-writes": "allows deletes and mutating invokes on attached/bridge targets",
            "--call-timeout-sec": "default 120 (CsiServerConfig.cs:18)",
            "--script-timeout-sec": "default 120, parsed but not wired to the engine",
            "--audit-log": "JSONL audit of Write/Destructive/Code calls (CsiAuditJournal); default %LOCALAPPDATA%/Sasaah/csi-mcp-audit.jsonl",
        },
        "version_reporting": "No server version, build id or tool-list hash is reported: Program.cs sets no ServerInfo, csi_status has no version field, and Directory.Build.props pins Version 0.1.0 for every build.",
        "tool_count": len(tools),
    }
    return {
        "inventory": "sasaah-csi-mcp",
        "sasaah_commit": commit,
        "provenance": STATIC_NOTE,
        "server": server,
        "tools": tools,
    }


# ----------------------------------------------------------------------------------------------
# Idea
# ----------------------------------------------------------------------------------------------

IDEA_ESCAPE = {"idea_run_script": "Compiles and runs C# against the current project (kind Code); DisableScript defaults to FALSE for this server (IdeaModels.cs:435)."}
IDEA_SESSION = {"idea_status", "idea_create_project", "idea_create_project_from_template", "idea_open_project", "idea_close_project"}
IDEA_FILE = {
    "idea_save_project", "idea_export_iom", "idea_import_iom", "idea_export_report",
    "idea_native_export_template", "idea_native_apply_template", "idea_native_apply_simple_template",
    "idea_native_delete_operations", "idea_native_create_from_iom", "idea_native_export_iom",
    "idea_native_set_design_subcode", "idea_native_fix_library_links", "idea_native_create_from_joint",
    "idea_native_link", "idea_native_sync_from_joint",
}
IDEA_ANALYSIS = {"idea_calculate", "idea_native_calculate"}


def classify_idea(name: str, kind: str) -> tuple[str, str]:
    if name in IDEA_ESCAPE:
        return "escape-hatch", "script"
    if name in IDEA_ANALYSIS:
        return "analysis", "analysis"
    if name in IDEA_SESSION:
        return "session", "session"
    if name in IDEA_FILE:
        return "file", "file"
    if kind in ("Meta", "Read"):
        return "read", "native" if name.startswith("idea_native_") else "model_read"
    return "write", "native" if name.startswith("idea_native_") else "model_edit"


def idea_inventory(root: Path, commit: str) -> dict:
    path = root / "02_Engines/Sasaah.Idea.Engine/IdeaToolCatalog.cs"
    src = path.read_text(encoding="utf-8")
    toks = tokenize(src)
    consts = collect_consts(toks)
    tpl = None
    for i, t in enumerate(toks):
        if t.kind == "ID" and t.val == "Plain" and toks[i - 1].val == "string":
            tpl = next(u for u in toks[i:] if u.kind == "STR" and u.dollars == 2)
            break
    assert tpl is not None
    assert 'var inner = string.IsNullOrWhiteSpace(props) ? string.Empty : props;' in src

    def plain(props: str) -> str:
        inner = "" if not props.strip() else props
        return re.sub(r"\{\{inner\}\}", lambda m: inner, tpl.val)

    ev = Evaluator(consts, {"Plain": plain})
    tools = []
    for i, t in enumerate(toks):
        if not (t.kind == "ID" and t.val == "new" and i + 2 < len(toks) and toks[i + 1].val == "(" and toks[i + 2].kind == "STR" and toks[i + 2].val.startswith("idea_")):
            continue
        args, _ = split_args(toks, i + 1)
        name = eval_tokens(ev, args[0])
        desc = eval_tokens(ev, args[1])
        schema = json.loads(eval_tokens(ev, args[2]))
        kind = args[3][0].val.split(".")[-1]
        cls, toolset = classify_idea(name, kind)
        notes = []
        if name in IDEA_ESCAPE:
            pass
        if kind in ("Read", "Meta") and "confirm" in schema_props(schema):
            notes.append("Declared read-only (ReadOnlyHint true) but the schema has a confirm gate and the description says some modes write the file: the annotation is inaccurate; the adapter must classify it as write.")
        if "overwrit" in desc.lower() or "out_path" in json.dumps(schema):
            notes.append("Writes or overwrites a file on disk (path/out_path argument); the harness works on copies.")
        reg = {
            "name": name,
            "description": desc,
            "toolset": toolset,
            "input_schema": schema,
            "declared_annotations": {
                "readOnlyHint": kind in ("Meta", "Read"),
                "destructiveHint": kind in ("Destructive", "Code"),
                "idempotentHint": kind in ("Meta", "Read"),
                "openWorldHint": False,
                "derived_from": "04_Deployments/Sasaah.Mcp.Idea.Server/Program.cs:72-77 (computed from the catalog kind)",
            },
            "server_kind": kind,
            "classification": cls,
            "changes_host_units": {
                "mechanism": "none",
                "units_param_declared": "units" in schema_props(schema),
                "applied": False,
                "note": "No unit switching: field names carry the unit (_mm, _deg); load effects are N, Vy, Vz, Mx, My, Mz as declared (idea_set_loads) with no unit label in the schema.",
            },
            "confirm_required": "confirm" in schema_props(schema),
            "timeout": {
                "default_seconds": 120,
                "source": "04_Deployments/Sasaah.Mcp.Idea.Server/IdeaServerConfig.cs:13 and 02_Engines/Sasaah.Idea.Engine/IdeaModels.cs:436",
                "option": "--call-timeout-sec / SASAAH_IDEA_CALL_TIMEOUT_SEC",
                "declared_per_tool": False,
                "applies_to": "IdeaSession.Invoke (Task.Run + Wait; the work is not cancelled on timeout, IdeaSession.cs:84-103), REST client HttpClient timeout, hidden-calc process timeout",
            },
            "source": {"file": rel(root, path), "line": t.line},
            "excluded_from_allowlist": name in IDEA_ESCAPE,
            "exclusion_reason": IDEA_ESCAPE.get(name, ""),
            "notes": notes,
        }
        tools.append(reg)
    server = {
        "executable": "sasaah-idea-mcp (AssemblyName in 04_Deployments/Sasaah.Mcp.Idea.Server/Sasaah.Mcp.Idea.Server.csproj)",
        "transport": "stdio, JSON-RPC",
        "mcp_sdk": "ModelContextProtocol 1.1.0 (csproj)",
        "start_options": {
            "--read-only": "hides Write, Destructive and Code tools",
            "--disable-script": "hides idea_run_script; the DEFAULT is that scripts are enabled (IdeaModels.cs:435)",
            "--call-timeout-sec": "default 120",
            "--idea-dir / --default-project / --service-url": "install dir, project, REST service URL (default http://localhost:5000 in IdeaSession.cs:41)",
        },
        "version_reporting": "No server version or build id; idea_status reports installed IDEA versions and REST service state only. Directory.Build.props pins Version 0.1.0.",
        "tool_count": len(tools),
    }
    return {"inventory": "sasaah-idea-mcp", "sasaah_commit": commit, "provenance": STATIC_NOTE, "server": server, "tools": tools}


# ----------------------------------------------------------------------------------------------
# Revit
# ----------------------------------------------------------------------------------------------

REVIT_ESCAPE = {
    "compile_and_run": "Compiles and runs C# inside Revit (kind code); also served as the alias revit_send_code_to_revit.",
    "dev_hot_run": "Hot-loads an assembly and runs an arbitrary command or static method (kind code).",
    "dev_hot_unload": "Part of the hot-load family (kind code); unloads kept sessions.",
    "run_baked_tool": "Runs a baked (generated) tool by name with free params (kind code).",
}
REVIT_COMPOSITE = {
    "batch_execute": "Forwards up to 20 other catalog tools in one request: an allowlist must also cover its sub-commands, so keep it off the allowlist (recommended).",
    "run_synapse_command": "Runs any loaded Revit IExternalCommand class by name (reflection over all loaded assemblies, SynapseCommandHandler.cs): arbitrary command dispatch; keep off the allowlist (recommended).",
    "set_parameter": "Sets a parameter by display name to a string value (name-addressed, language-dependent): not an escape hatch, but violates the target rule of 07 section 2 (parameters by id or GUID).",
}


def classify_revit(name: str, kind: str, group: str) -> tuple[str, str]:
    if name in REVIT_ESCAPE:
        return "escape-hatch", group
    if kind == "control":
        return "session", group
    if group == "export":
        return ("read" if kind == "read" else "file"), group
    if name in ("open_model", "list_recent_models", "get_model_metadata", "activate_view", "show_message", "overwrite_model"):
        return ("file" if name in ("open_model", "overwrite_model") else "session" if name in ("activate_view", "show_message") else "read"), group
    if kind == "read":
        return "read", group
    return "write", group


REVIT_STRUCT_MAP = {
    # design/docs/architecture/07 section 8 intended tools -> Sasaah catalog names (author's mapping)
    "list_documents": ["get_model_metadata", "list_recent_models"],
    "list_levels": ["list_levels"],
    "list_grids": ["list_grids"],
    "list_structural_columns": ["list_elements", "ai_element_filter"],
    "list_structural_framing": ["list_elements", "ai_element_filter"],
    "list_walls": ["list_walls"],
    "list_floors": ["list_elements"],
    "list_foundations": ["list_elements"],
    "list_family_types": ["get_available_family_types", "list_family_types_in_family", "list_loaded_families"],
    "get_element_parameters": ["get_element_parameters", "get_type_parameters"],
    "get_element_geometry": ["get_element_geometry"],
    "create_family_type": ["duplicate_family_type"],
    "set_family_type_parameters": ["set_type_parameter_values"],
    "create_levels": ["create_level"],
    "create_grids": ["create_grid"],
    "add_structural_columns": ["create_structural_column"],
    "add_structural_framing": ["create_structural_beam"],
    "add_walls": ["create_structural_wall", "create_wall"],
    "add_floors": ["create_surface_based_element"],
    "add_foundations": ["create_foundation_isolated", "create_foundation_wall"],
    "set_element_type": ["change_element_type"],
    "set_element_parameters": ["set_element_parameter_values", "set_parameter_value_by_guid"],
    "move_elements": [],
    "delete_elements": ["delete_element"],
    "open_document": ["open_model"],
    "save_document": [],
    "save_document_as": [],
    "list_analytical_members": [],
    "get_analytical_model": [],
}


def eval_revit_arg(ev: Evaluator, arg: list[Tok]):
    if len(arg) == 1 and arg[0].kind == "ID" and arg[0].val in ("true", "false"):
        return arg[0].val == "true"
    return eval_tokens(ev, arg)


def revit_inventory(root: Path, commit: str) -> dict:
    cat_dir = root / "02_Engines/Sasaah.Mcp.Bridge.Engine/Catalog"
    base_src = (cat_dir / "ToolCatalog.cs").read_text(encoding="utf-8")
    btoks = tokenize(base_src)
    consts: dict[str, str] = {}
    for i, t in enumerate(btoks):
        if t.kind == "ID" and t.val == "EmptySchema":
            consts["EmptySchema"] = btoks[i + 2].val
    ev = Evaluator(consts, {})
    tools = []
    seen_files = []
    for f in sorted(cat_dir.glob("ToolCatalog.*.cs")):
        toks = tokenize(f.read_text(encoding="utf-8"))
        seen_files.append(f.name)
        for i, t in enumerate(toks):
            if not (t.kind == "ID" and t.val == "Tool" and i + 2 < len(toks) and toks[i + 1].val == "(" and toks[i + 2].kind == "STR"):
                continue
            args, _ = split_args(toks, i + 1)
            name, kind, group, desc = (eval_tokens(ev, a) for a in args[:4])
            schema_text = eval_tokens(ev, args[4])
            schema = json.loads(schema_text)
            opts = {"idempotent": True, "writesFiles": False, "allowInBatch": True, "requiresConfirmation": False, "reserved": False}
            order = ["idempotent", "writesFiles", "allowInBatch", "requiresConfirmation", "reserved", "rvtMcpName"]
            pos = 0
            for a in args[5:]:
                if len(a) >= 3 and a[0].kind == "ID" and a[1].val == ":":
                    opts[a[0].val] = eval_revit_arg(ev, a[2:])
                else:
                    opts[order[pos]] = eval_revit_arg(ev, a)
                    pos += 1
            cls, toolset = classify_revit(name, kind, group)
            read_only = kind in ("read", "control")
            destructive = kind == "destructive"
            served = {
                "readOnlyHint": read_only,
                "destructiveHint": destructive or kind in ("destructive", "code"),
                "idempotentHint": bool(opts["idempotent"]),
                "openWorldHint": False,
            }
            notes = []
            if kind == "control" and name in ("shutdown_bridge", "authenticate", "prepare_destructive"):
                notes.append("Served read-only (kind control => read_only annotation) although the tool changes bridge state; control tools are always enabled by the bridge ToolsetFilter and mapped to revit_* by the MCP server.")
            if name in REVIT_COMPOSITE:
                notes.append(REVIT_COMPOSITE[name])
            if opts["requiresConfirmation"]:
                notes.append("Requires a confirmation token (prepare_destructive) which the MCP server obtains automatically for destructive-hint tools (Program.cs:157-162): the token is not a human confirmation.")
            if opts["writesFiles"]:
                notes.append("Writes files (writes_files annotation).")
            if "overwrite_model" == name:
                notes.append("Reserved: no handler is registered (description says so).")
            escape = name in REVIT_ESCAPE
            reg = {
                "name": name,
                "mcp_name": "revit_" + name,
                "description": desc,
                "toolset": toolset,
                "input_schema": schema,
                "declared_annotations": {
                    "bridge_catalog": {"read_only": read_only, "destructive": destructive, "idempotent": bool(opts["idempotent"]), "writes_files": bool(opts["writesFiles"])},
                    "served_by_mcp_server": served,
                    "derived_from": "ToolCatalog.cs Tool() and 04_Deployments/Sasaah.Mcp.Revit.Server/Program.cs:196-205",
                },
                "server_kind": kind,
                "classification": cls,
                "changes_host_units": {
                    "mechanism": "none",
                    "note": "Revit units are fixed by the tool schema: lengths in mm (x_mm, height_mm, 'numeric values in mm' in descriptions), angles in degrees, forces kN and kNm where stated; nothing switches a host unit setting. Internal Revit feet/radians are converted inside the handlers (not read).",
                },
                "confirm_required": bool(opts["requiresConfirmation"]),
                "allow_in_batch": bool(opts["allowInBatch"]),
                "reserved": bool(opts["reserved"]),
                "timeout": {
                    "default_ms": 120000,
                    "source": "04_Deployments/Sasaah.Mcp.Revit.Server/ServerConfig.cs:8 (--bridge-timeout-ms); the bridge main-thread queue defaults to 60000 ms when a request carries none (MainThreadRequestQueue.cs:25)",
                    "declared_per_tool": False,
                    "note": "A few tools take their own timeout argument (dev_hot_run.timeout_ms).",
                },
                "source": {"file": rel(root, f), "line": t.line},
                "excluded_from_allowlist": escape,
                "exclusion_reason": REVIT_ESCAPE.get(name, ""),
                "recommend_exclusion": name in REVIT_COMPOSITE and name != "set_parameter",
                "notes": notes,
            }
            tools.append(reg)
    # tools defined locally in the MCP server (not in the bridge catalog)
    prog = root / "04_Deployments/Sasaah.Mcp.Revit.Server/Program.cs"
    ptoks = tokenize(prog.read_text(encoding="utf-8"))
    schema_vars: dict[str, dict] = {}
    for i, t in enumerate(ptoks):
        if t.kind == "ID" and t.val == "JsonDocument.Parse" and ptoks[i - 1].val == "=" and ptoks[i + 2].kind == "STR":
            schema_vars[ptoks[i - 2].val] = json.loads(ptoks[i + 2].val)
    local = []
    for i, t in enumerate(ptoks):
        if t.kind == "ID" and t.val == "new" and ptoks[i + 1].val == "Tool" and ptoks[i + 2].val == "{":
            j, depth, fields, key = i + 3, 1, {}, None
            cur: list[Tok] = []
            while depth:
                u = ptoks[j]
                if u.kind == "P" and u.val == "{":
                    depth += 1
                elif u.kind == "P" and u.val == "}":
                    depth -= 1
                    if depth == 0:
                        break
                if depth == 1 and u.kind == "P" and u.val == ",":
                    if key:
                        fields[key] = cur
                    key, cur = None, []
                elif depth == 1 and u.kind == "P" and u.val == "=" and key is None:
                    key = cur[-1].val
                    cur = []
                else:
                    cur.append(u)
                j += 1
            if key:
                fields[key] = cur
            if len(fields.get("Name", [])) != 1 or fields["Name"][0].kind != "STR":
                continue
            nm = fields["Name"][0].val
            if not nm.startswith("revit_"):
                continue
            schema_var = next((x.val.split(".")[0] for x in fields.get("InputSchema", []) if x.kind == "ID" and x.val.split(".")[0] in schema_vars), None)
            ann_toks = fields.get("Annotations", [])
            ann = {}
            for k in range(len(ann_toks) - 2):
                if ann_toks[k].kind == "ID" and ann_toks[k].val.endswith("Hint") and ann_toks[k + 1].val == "=":
                    ann[ann_toks[k].val] = ann_toks[k + 2].val == "true"
            descr_tok = fields.get("Description", [None])[0]
            local.append((nm, descr_tok.val if descr_tok is not None and descr_tok.kind == "STR" else "(same description as compile_and_run, taken from the bridge at run time)", schema_vars.get(schema_var), ann, t.line))
    for nm, d, sch, ann, line in local:
        bare = nm[len("revit_"):]
        escape = nm == "revit_send_code_to_revit"
        cond = {
            "revit_get_change_records": "listed unless --disable-change-history",
            "revit_record_change": "listed unless --disable-change-history",
            "revit_list_bake_suggestions": "listed only with --enable-adaptive-bake",
            "revit_accept_bake_suggestion": "listed only with --enable-adaptive-bake; writes baked tool files",
            "revit_dismiss_bake_suggestion": "listed only with --enable-adaptive-bake",
            "revit_send_code_to_revit": "alias of compile_and_run, listed unless --disable-send-code or --read-only",
        }.get(nm, "always listed")
        is_bake = "bake" in nm
        cls = "escape-hatch" if escape else ("session" if nm in ("revit_connection_status", "revit_list_available_targets", "revit_get_current_target", "revit_switch_target") else ("write" if is_bake or nm == "revit_record_change" else "read"))
        tools.append({
            "name": nm,
            "mcp_name": nm,
            "description": d,
            "toolset": "mcp_server_local",
            "input_schema": sch,
            "declared_annotations": {"served_by_mcp_server": ann, "derived_from": "04_Deployments/Sasaah.Mcp.Revit.Server/Program.cs (LocalTools/MapTools)"},
            "server_kind": "local",
            "classification": cls,
            "changes_host_units": {"mechanism": "none"},
            "confirm_required": False,
            "timeout": {"default_ms": 120000, "source": "ServerConfig.cs:8", "declared_per_tool": False, "note": "bridge-forwarding local tools use the same bridge timeout; pure-local ones do not call Revit"},
            "source": {"file": rel(root, prog), "line": line},
            "excluded_from_allowlist": escape or is_bake,
            "exclusion_reason": REVIT_ESCAPE["compile_and_run"] if escape else ("Tool-baking family: creates generated tools; not needed" if is_bake else ""),
            "listed_when": cond,
            "notes": ["Defined in the MCP server, not in the bridge catalog."]
            + (["Its declared annotation is ReadOnlyHint=true although it writes a persistent record (Program.cs:266)."] if nm == "revit_record_change" else [])
            + (["revit_switch_target is annotated read-only but changes the active bridge target (Program.cs:261)."] if nm == "revit_switch_target" else []),
        })
    served = {}
    for x in tools:
        served.setdefault(x["mcp_name"], []).append(x)
    for mcp_name, group_ in served.items():
        if len(group_) > 1:
            for x in group_:
                x["notes"].append(f"{mcp_name} is listed twice in tools/list (a local tool and the bridge-catalog tool of the same name, Program.cs:89); calls are answered by the local implementation first (Program.cs:121-122).")
    mapping = {
        k: {"candidates": v, "present": [c for c in v if any(t["name"] == c for t in tools)]} for k, v in REVIT_STRUCT_MAP.items()
    }
    server = {
        "executable": "sasaah-revit-mcp (04_Deployments/Sasaah.Mcp.Revit.Server); talks to the Revit add-in bridge over a named pipe (BridgeClient.cs)",
        "transport": "stdio MCP to the client; named pipe sasaah.revit.bridge.v1 to Revit (ServerConfig.cs:7)",
        "tools_source": "tools/list is built at request time from the bridge's list_tools reply (Program.cs:71-77): the bridge catalog filtered by its ToolsetFilter (default toolsets read, write, control; destructive and code only when enabled in the Revit user settings, ToolsetFilter.cs) and then by the MCP server's own filters (--toolsets default all, --read-only, --disable-send-code)",
        "version_reporting": "The bridge list_tools reply carries catalog_version, the first 16 hex characters of SHA-256 over the concatenation of (name, newline, input-schema JSON, newline) for every catalog tool (ListToolsHandler.cs:58-62), surfaced by revit_connection_status (Program.cs:141) and used for notifications/tools/list_changed. It hashes the whole catalog, not the filtered list. ping returns uptime only (ControlHandlers.cs:18-22); no add-in or server build id.",
        "start_options": {
            "--read-only": "drops non-read-only tools",
            "--disable-send-code": "drops compile_and_run and its alias (default: enabled)",
            "--toolsets": "comma list of groups or kinds (default all)",
            "--bridge-timeout-ms": "default 120000",
            "--enable-adaptive-bake / --enable-call-log / --disable-change-history": "see ServerConfig.cs",
        },
        "tool_count": len(tools),
        "bridge_catalog_count": sum(1 for x in tools if x["toolset"] != "mcp_server_local"),
        "design_07_section_8_mapping": mapping,
    }
    return {"inventory": "sasaah-revit-mcp", "sasaah_commit": commit, "provenance": STATIC_NOTE, "server": server, "tools": tools}


# ----------------------------------------------------------------------------------------------
# Command-line tools (tools/dxf-prep, tools/etabs-model)
# ----------------------------------------------------------------------------------------------

PS_TYPES = {"string": "string", "double": "number", "int": "integer", "switch": "boolean", "bool": "boolean"}


def parse_ps_script(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    syn = re.search(r"\.SYNOPSIS\s*\n\s*(.+?)\n\s*\.", text, re.S)
    desc = re.search(r"\.DESCRIPTION\s*\n(.+?)\n\s*\.[A-Z]+", text, re.S)
    m = re.search(r"^(?:\[CmdletBinding\(\)\]\s*\n)?param\((.*?)\n\)\s*\n", text, re.S | re.M)
    props: dict = {}
    required: list[str] = []
    if m:
        body = m.group(1)
        line_start = text[: text.index(body)].count("\n") + 1
        # split declarations on newlines or on ';'-less same-line sequences like '[string]$A = "", [string]$B'
        pending_required = False
        pending_validate = None
        for raw in re.split(r"\n", body):
            ln = raw.strip()
            if not ln:
                continue
            if "Mandatory = $true" in ln:
                pending_required = True
            v = re.search(r"\[ValidateSet\((.*?)\)\]", ln)
            if v:
                pending_validate = [x.strip().strip('"') for x in v.group(1).split(",")]
            for d in re.finditer(r"\[(string|double|int|switch|bool)\]\$(\w+)\s*(?:=\s*(\"[^\"]*\"|'[^']*'|[-\w.]+))?", ln):
                typ, name, default = d.groups()
                p: dict = {"type": PS_TYPES[typ]}
                if default is not None:
                    dv = default.strip("\"'")
                    p["default"] = float(dv) if typ == "double" else (int(dv) if typ == "int" else dv)
                if pending_validate and typ == "string":
                    p["enum"] = pending_validate
                    pending_validate = None
                props[name] = p
                if pending_required:
                    required.append(name)
                    pending_required = False
    schema = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return {
        "synopsis": " ".join(syn.group(1).split()) if syn else "",
        "description": " ".join(desc.group(1).split()) if desc else "",
        "schema": schema,
    }


def cli_inventory(root: Path, commit: str) -> dict:
    tools = []

    def add(rel_path: str, role: str, notes: list[str], *, exit_codes: str, timeout: dict, excluded=False, reason="", schema_override=None, units: str = ""):
        p = root / rel_path
        info = parse_ps_script(p) if p.suffix == ".ps1" else {"synopsis": "", "description": "", "schema": None}
        text = p.read_text(encoding="utf-8")
        if p.suffix == ".py":
            doc = re.match(r'\s*"""(.*?)"""', text, re.S)
            info["description"] = " ".join(doc.group(1).split()) if doc else ""
        # no private data in the inventory: a helper docstring names a private test corpus
        info["description"] = re.sub(r"Hamoud", "<private>", info["description"])
        tools.append({
            "name": rel_path.replace("tools/", "", 1),
            "description": info["synopsis"] or info["description"].split(". ")[0],
            "description_full": info["description"],
            "toolset": rel_path.split("/")[1],
            "input_schema": schema_override if schema_override is not None else info["schema"],
            "input_schema_note": "Converted from the PowerShell param() block: [string]->string, [double]->number, [switch]->boolean, ValidateSet->enum, Mandatory->required." if p.suffix == ".ps1" and schema_override is None else "Positional arguments of a Python helper; not converted.",
            "declared_annotations": None,
            "annotations_note": "Command-line tools declare no MCP annotations.",
            "classification": role,
            "changes_host_units": {"mechanism": "none", "note": units or "No host unit switching in the script itself."},
            "confirm_required": False,
            "timeout": timeout,
            "exit_codes": exit_codes,
            "source": {"file": rel_path, "line": 1},
            "excluded_from_allowlist": excluded,
            "exclusion_reason": reason,
            "notes": notes,
        })

    no_timeout = {"default_seconds": None, "declared_per_tool": False, "note": "No timeout is set by the script; the harness must bound the process (Job Object, process/11 and 11 section 9)."}
    add("tools/dxf-prep/prepare.ps1", "file", [
        "Writes <OutDir>/<stem>.dxf, <stem>.grids.json, preview PNG and prep-report.md; never modifies the input DXF.",
        "Calls the cached DxfPrep CLI (dotnet publish on first use or when sources are newer), a Python validator, AutoCAD accoreconsole (path fixed to AutoCAD 2023 in the script) and a Python preview renderer: needs a Windows machine with AutoCAD (needs local test).",
        "Output geometry is in metres with the lowest-left grid intersection at the origin (docs/dxf-prep/README.md, Origin option).",
        "Exit code is non-zero on any failure (README); the CLI itself uses 0 ok, 1 usage, 2 unreadable input, 3 failed (Program.cs:34-37).",
    ], exit_codes="0 ok; 1 any file failed or no input; CLI: 0/1/2/3", timeout=no_timeout, units="Metres in the output DXF (documented), no host unit setting.")
    add("tools/dxf-prep/inspect.ps1", "read", [
        "Fast classification preview: runs the CLI in --inspect mode, writes <stem>.classify.json and <stem>.classify.png; no output DXF.",
    ], exit_codes="non-zero on failure", timeout=no_timeout)
    add("tools/etabs-model/build.ps1", "analysis", [
        "Generates <out>.e2k, launches its own hidden ETABS instance, saves <out>.EDB, RUNS THE ANALYSIS, verifies the saved model, exits only the instance it launched, writes model-report.md (docs/etabs-model/README.md).",
        "The ETABS session inside the CLI uses CallTimeoutSec 300 (04_Deployments/Sasaah.Etabs.ModelFromDxf.Cli/Program.cs:194) instead of the server default of 120.",
        "Template .e2k is ETABS 22 text in kN/m/C and is read-only; the model units follow the template (documented).",
        "Needs ETABS 22 installed: needs local test. -NoEtabs stops after writing the e2k.",
        "Exit codes of the CLI: 0 ok, 1 failure ('FAIL: ...'), 2 usage (Program.cs:41-65).",
    ], exit_codes="0 ok; 1 failure; 2 usage", timeout={"default_seconds": 300, "source": "04_Deployments/Sasaah.Etabs.ModelFromDxf.Cli/Program.cs:194 (ETABS call timeout inside the CLI); the process itself has no overall timeout", "declared_per_tool": True}, units="Uses the template's units (kN, m, C documented) in a hidden instance it launched; the user's ETABS session is never touched.")
    add("tools/etabs-model/classify-columns.ps1", "write", [
        "Reaction-based column sizing helper: assigns one of three column sizes by declared axial-load thresholds (script header). It embeds engineering thresholds: engineering content, not to be adopted or approved by this build (risk R1); recorded as an owner-queue item.",
        "Not part of the optional DXF start of 18 section 6.",
    ], exit_codes="not read", timeout=no_timeout, excluded=True, reason="Embeds engineering decision thresholds that are not in the design basis; keep out of the allowlist until the owner reviews them.")
    for helper, purpose in [
        ("tools/dxf-prep/validate_etabs_dxf.py", "Validates a prepared ETABS DXF against its grids sidecar; called by prepare.ps1."),
        ("tools/dxf-prep/render_preview.py", "Renders a side-by-side preview PNG; called by prepare.ps1."),
        ("tools/dxf-prep/render_classify.py", "Renders a classification preview PNG; called by inspect.ps1."),
        ("tools/dxf-prep/compare_dxf.py", "Compares two prepared DXFs geometrically; development utility, not called by the scripts."),
        ("tools/dxf-prep/make_variants.py", "Generates robustness test variants of a private test corpus; development utility."),
    ]:
        add(helper, "read", [purpose, "Internal helper, not an adapter tool; schema not extracted (positional arguments)."], exit_codes="not read", timeout=no_timeout)
    add("tools/dxf-prep/check_autocad_open.ps1", "read", ["Opens a DXF with AutoCAD accoreconsole to prove AutoCAD can read it; called by prepare.ps1. Needs AutoCAD (needs local test)."], exit_codes="not read", timeout=no_timeout)
    server = {
        "executable": "PowerShell wrappers (pwsh -File ...) over published .NET command-line programs in 04_Deployments/Sasaah.Etabs.DxfPrep.Cli and Sasaah.Etabs.ModelFromDxf.Cli",
        "transport": "process: command-line arguments in, files and console text out, exit code",
        "version_reporting": "None. The wrappers rebuild the cached CLI when sources are newer than the cached exe (build.ps1 / prepare.ps1), so the behavior follows the working tree, not a pinned build. The adapter must pin the Sasaah commit and hash the cached exe.",
        "tool_count": len(tools),
    }
    return {"inventory": "sasaah-cli-tools", "sasaah_commit": commit, "provenance": STATIC_NOTE, "server": server, "tools": tools}


# ----------------------------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sasaah", required=True, type=Path, help="path to the (read-only) Sasaah checkout")
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "inventory")
    ap.add_argument("--allow-other-commit", action="store_true", help="do not stop when the checkout is not the pinned commit")
    a = ap.parse_args()
    root = a.sasaah.resolve()
    commit = sasaah_commit(root)
    if commit != EXPECTED_COMMIT and not a.allow_other_commit:
        print(f"extract.py: Sasaah is at {commit}, expected {EXPECTED_COMMIT} (use --allow-other-commit)", file=sys.stderr)
        return 2
    for fn, name in [(csi_inventory, "sasaah-csi-mcp.json"), (revit_inventory, "sasaah-revit-mcp.json"), (idea_inventory, "sasaah-idea-mcp.json"), (cli_inventory, "sasaah-cli-tools.json")]:
        doc = fn(root, commit)
        write_json(a.out / name, doc)
        print(f"{name}: {len(doc['tools'])} tools")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
