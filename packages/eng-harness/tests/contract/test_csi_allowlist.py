"""Contract tests of the CSI allowlist side (plan 0002 T4; spec 0002 AC35)."""

import json
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
INVENTORY = REPO_ROOT / "spikes" / "S-12-sasaah-tool-inventory" / "inventory" / "sasaah-csi-mcp.json"
SCHEMAS = PACKAGE_ROOT / "tests" / "fakes" / "sasaah_csi" / "schemas.json"


def _load(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        data = json.load(handle)
    assert isinstance(data, dict)
    return data


def test_fake_schemas_match_inventory() -> None:
    """AC35: the fake's tools are the inventory's non-excluded tools with equal input schemas."""
    inventory = _load(INVENTORY)
    fake = _load(SCHEMAS)
    expected = {t["name"]: t["input_schema"] for t in inventory["tools"] if not t["excluded_from_allowlist"]}
    actual = {t["name"]: t["input_schema"] for t in fake["tools"]}
    assert fake["sasaah_commit"] == inventory["sasaah_commit"]
    assert len(fake["tools"]) == len(actual)
    assert actual == expected


def test_fake_has_no_escape_hatch() -> None:
    """No excluded tool (script, invoke, table write, generic object access) is in the fake's tool list."""
    inventory = _load(INVENTORY)
    excluded = {t["name"] for t in inventory["tools"] if t["excluded_from_allowlist"]}
    names = {t["name"] for t in _load(SCHEMAS)["tools"]}
    assert excluded
    assert names.isdisjoint(excluded)


def test_fake_server_kinds_match_inventory() -> None:
    """The fake classifies each tool by the inventory's server_kind, so its write set cannot drift."""
    inventory = _load(INVENTORY)
    expected = {t["name"]: t["server_kind"] for t in inventory["tools"] if not t["excluded_from_allowlist"]}
    actual = {t["name"]: t.get("server_kind") for t in _load(SCHEMAS)["tools"]}
    assert actual == expected
