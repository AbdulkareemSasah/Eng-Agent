#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Validates the S-12 inventory JSON files (CI runs every spikes/*/check.py).

Checks: files parse; the Sasaah commit and the "static reading, needs local test" statement are recorded;
required fields exist on every tool; no duplicate names; classifications are known; every escape hatch
(tools that run scripts, evaluate code, invoke arbitrary API calls or write tables) is classified
"escape-hatch" and excluded from the allowlist, with a reason; no tool of kind Code escapes the mark.
Standard library only. Exit code 0 on success, 1 on any failure.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PINNED_COMMIT = "61da80f61a6562c8e3553168056bc107e3f93013"
CLASSES = {"read", "write", "analysis", "design", "session", "file", "escape-hatch"}
FILES = {
    "sasaah-csi-mcp.json": "sasaah-csi-mcp",
    "sasaah-revit-mcp.json": "sasaah-revit-mcp",
    "sasaah-idea-mcp.json": "sasaah-idea-mcp",
    "sasaah-cli-tools.json": "sasaah-cli-tools",
}
REQUIRED = [
    "name", "description", "toolset", "input_schema", "declared_annotations", "classification",
    "changes_host_units", "timeout", "source", "excluded_from_allowlist", "exclusion_reason", "notes",
]
# Names that must always be marked as escape hatches wherever they appear.
MUST_BE_ESCAPE = {
    "csi_run_script", "csi_db_tables_apply", "csi_invoke", "csi_object_add", "csi_object_delete",
    "csi_object_set", "csi_object_get", "idea_run_script", "compile_and_run", "dev_hot_run",
    "dev_hot_unload", "run_baked_tool", "revit_send_code_to_revit",
}
ESCAPE_PATTERN = re.compile(r"(run_script|invoke|compile_and_run|send_code|db_tables_apply|hot_run|hot_unload|run_baked)")
EXPECTED_COUNTS = {"sasaah-csi-mcp": ("tools", 83), "sasaah-revit-mcp": ("bridge", 248)}  # stated by ADR-0024 and the catalogs


def check_file(path: Path, inventory: str, errors: list[str]) -> None:
    def err(msg: str) -> None:
        errors.append(f"{path.name}: {msg}")

    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        err(f"cannot parse: {exc}")
        return
    if doc.get("inventory") != inventory:
        err(f"inventory is {doc.get('inventory')!r}, expected {inventory!r}")
    commit = doc.get("sasaah_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        err("sasaah_commit must be a 40-hex commit id")
    prov = doc.get("provenance", "")
    if "static reading" not in prov or "needs local test" not in prov or "tools/list" not in prov:
        err("provenance must state static reading, comparison with the live tools/list, and 'needs local test'")
    if not isinstance(doc.get("server"), dict) or "version_reporting" not in doc["server"]:
        err("server.version_reporting is required (state the finding or the gap)")
    tools = doc.get("tools")
    if not isinstance(tools, list) or not tools:
        err("tools must be a non-empty list")
        return
    seen: dict[str, int] = {}
    mcp_seen: dict[str, list[dict]] = {}
    for idx, t in enumerate(tools):
        label = f"tools[{idx}] {t.get('name', '?')}"
        for key in REQUIRED:
            if key not in t:
                err(f"{label}: missing field {key!r}")
        name = t.get("name")
        if not isinstance(name, str) or not name:
            err(f"{label}: name must be a non-empty string")
            continue
        seen[name] = seen.get(name, 0) + 1
        mcp_seen.setdefault(t.get("mcp_name", name), []).append(t)
        cls = t.get("classification")
        if cls not in CLASSES:
            err(f"{label}: classification {cls!r} not in {sorted(CLASSES)}")
        sch = t.get("input_schema")
        if sch is not None and not (isinstance(sch, dict) and (sch.get("type") == "object" or "properties" in sch)):
            err(f"{label}: input_schema must be a JSON Schema object or null")
        if sch is None and not any("schema not extracted" in n or "not converted" in str(t.get("input_schema_note", "")) for n in t.get("notes", [])) and "not converted" not in str(t.get("input_schema_note", "")):
            err(f"{label}: null input_schema needs a note that says why")
        if not isinstance(t.get("changes_host_units"), dict) or "mechanism" not in t["changes_host_units"]:
            err(f"{label}: changes_host_units.mechanism is required")
        if not isinstance(t.get("timeout"), dict):
            err(f"{label}: timeout must be an object")
        src = t.get("source", {})
        if not (isinstance(src, dict) and isinstance(src.get("file"), str) and isinstance(src.get("line"), int) and src["line"] > 0):
            err(f"{label}: source needs file and a positive line")
        if not isinstance(t.get("notes"), list):
            err(f"{label}: notes must be a list")
        if not isinstance(t.get("excluded_from_allowlist"), bool):
            err(f"{label}: excluded_from_allowlist must be true or false")
        # escape hatches
        escape_by_name = name in MUST_BE_ESCAPE or bool(ESCAPE_PATTERN.search(name))
        if escape_by_name and cls != "escape-hatch":
            err(f"{label}: looks like an escape hatch but is classified {cls!r}")
        if str(t.get("server_kind", "")).lower() == "code" and cls != "escape-hatch":
            err(f"{label}: kind Code must be classified escape-hatch")
        if cls == "escape-hatch":
            if t.get("excluded_from_allowlist") is not True:
                err(f"{label}: escape hatch must have excluded_from_allowlist true")
            if not t.get("exclusion_reason"):
                err(f"{label}: escape hatch needs an exclusion_reason")
        elif t.get("excluded_from_allowlist") is True and not t.get("exclusion_reason"):
            err(f"{label}: excluded tool needs an exclusion_reason")
    for name, count in seen.items():
        if count > 1:
            err(f"duplicate tool name {name!r} ({count} entries)")
    for mcp_name, group in mcp_seen.items():
        if len(group) > 1 and not all(any("listed twice" in n for n in g["notes"]) for g in group):
            err(f"{mcp_name!r} is served more than once and the entries do not say so")
    if commit == PINNED_COMMIT and inventory in EXPECTED_COUNTS:
        kind, expected = EXPECTED_COUNTS[inventory]
        actual = len(tools) if kind == "tools" else sum(1 for t in tools if t.get("toolset") != "mcp_server_local")
        if actual != expected:
            err(f"expected {expected} {kind} at the pinned commit, found {actual}")
    stated = doc["server"].get("tool_count")
    if stated != len(tools):
        err(f"server.tool_count {stated} differs from {len(tools)} tools")


def main() -> int:
    base = Path(__file__).resolve().parent / "inventory"
    errors: list[str] = []
    for fname, inv in FILES.items():
        p = base / fname
        if not p.exists():
            errors.append(f"{fname}: missing")
            continue
        check_file(p, inv, errors)
    if errors:
        print("S-12 inventory check FAILED:")
        for e in errors:
            print("  -", e)
        return 1
    print("S-12 inventory check passed:", ", ".join(FILES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
