"""Contract tests of the CSI allowlist side (plan 0002 T4; spec 0002 AC35)."""

import json
import os
from pathlib import Path
from typing import Any

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
INVENTORY = REPO_ROOT / "spikes" / "S-12-sasaah-tool-inventory" / "inventory" / "sasaah-csi-mcp.json"
SCHEMAS = PACKAGE_ROOT / "tests" / "fakes" / "sasaah_csi" / "schemas.json"


def _load(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        data = json.load(handle)
    assert isinstance(data, dict)
    return data


def _inventory() -> dict[str, Any]:
    """The S-12 inventory at the repository root, outside this package.

    The gate's mutation step runs the tests in a copy of the package only, where the inventory does not exist; mutmut
    sets ``MUTANT_UNDER_TEST`` in every one of its runs, and only there a missing inventory skips. In every other run a
    missing inventory fails (B-369).
    """
    if not INVENTORY.is_file() and "MUTANT_UNDER_TEST" in os.environ:
        pytest.skip(
            "the S-12 inventory is outside the package copy that the mutation step runs (B-369); expires 2026-12-31"
        )
    return _load(INVENTORY)


def test_fake_schemas_match_inventory() -> None:
    """AC35: the fake's tools are the inventory's non-excluded tools with equal input schemas."""
    inventory = _inventory()
    fake = _load(SCHEMAS)
    expected = {t["name"]: t["input_schema"] for t in inventory["tools"] if not t["excluded_from_allowlist"]}
    actual = {t["name"]: t["input_schema"] for t in fake["tools"]}
    assert fake["sasaah_commit"] == inventory["sasaah_commit"]
    assert len(fake["tools"]) == len(actual)
    assert actual == expected


def test_fake_has_no_escape_hatch() -> None:
    """No excluded tool (script, invoke, table write, generic object access) is in the fake's tool list."""
    inventory = _inventory()
    excluded = {t["name"] for t in inventory["tools"] if t["excluded_from_allowlist"]}
    names = {t["name"] for t in _load(SCHEMAS)["tools"]}
    assert excluded
    assert names.isdisjoint(excluded)


def test_fake_server_kinds_match_inventory() -> None:
    """The fake classifies each tool by the inventory's server_kind, so its write set cannot drift."""
    inventory = _inventory()
    expected = {t["name"]: t["server_kind"] for t in inventory["tools"] if not t["excluded_from_allowlist"]}
    actual = {t["name"]: t.get("server_kind") for t in _load(SCHEMAS)["tools"]}
    assert actual == expected


def _expected_units(tool: dict[str, Any]) -> str:
    """The `units` handling the inventory's evidence implies (spec 0002 section 4.5.1)."""
    change = tool["changes_host_units"]
    if change["units_param_declared"]:
        return "token" if change["applied"] else "declared_ignored"
    return "present" if change["quantities_follow_present_units"] else "none"


def test_against_inventory() -> None:
    """AC16: the allowlist names only non-excluded inventory tools of the pinned build, and agrees with them."""
    from eng_harness.adapters.csi import csi_allowlist

    inventory = _inventory()
    by_name = {t["name"]: t for t in inventory["tools"]}
    allowlist = csi_allowlist()
    assert allowlist.sasaah_commit == inventory["sasaah_commit"]
    assert allowlist.fingerprint_source == "s12-inventory"
    assert allowlist.tools
    for tool in allowlist.tools:
        item = by_name[tool.name]  # a KeyError is a tool absent from the pinned build
        assert not item["excluded_from_allowlist"], tool.name
        assert item["classification"] != "escape-hatch", tool.name
        assert tool.kind == ("session" if item["classification"] == "file" else item["classification"]), tool.name
        if item["server_kind"] == "Read":
            assert tool.effect == "read", tool.name
        if item["server_kind"] in ("Write", "Destructive"):
            assert tool.effect == "write", tool.name
        assert (tool.confirm != "never") == item["confirm_required"], tool.name
        assert tool.units == _expected_units(item), tool.name
        assert tool.products == ("ETABS",)


def test_allowlist_is_served_by_the_fake() -> None:
    """AC35: every allowlisted tool is in the synthetic fake, which carries the inventory's schemas."""
    from eng_harness.adapters.csi import csi_allowlist

    served = {t["name"] for t in _load(SCHEMAS)["tools"]}
    assert {tool.name for tool in csi_allowlist().tools} <= served


def test_pinned_fingerprint_from_inventory() -> None:
    """AC10: the fingerprint of the allowlisted tools, computed from the S-12 inventory, is the pinned one."""
    from eng_harness.adapters.csi import csi_allowlist
    from eng_harness.servers._buildcheck import tool_list_fingerprint

    allowlist = csi_allowlist()
    assert allowlist.fingerprint_source == "s12-inventory"
    schemas = {t["name"]: t["input_schema"] for t in _inventory()["tools"] if t["name"] in allowlist.tool_names}
    assert set(schemas) == {tool.name for tool in allowlist.tools}
    assert tool_list_fingerprint(schemas) == allowlist.tool_fingerprint
