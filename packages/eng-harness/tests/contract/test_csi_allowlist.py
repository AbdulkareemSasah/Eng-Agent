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
        pytest.skip("the S-12 inventory is outside the package copy that the mutation step runs (B-369)")
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
