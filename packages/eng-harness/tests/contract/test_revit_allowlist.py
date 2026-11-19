"""Contract tests of the Revit fake schemas (plan 0011 T2; spec 0011 AC30)."""

import json
import os
from pathlib import Path
from typing import Any

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
INVENTORY = REPO_ROOT / "spikes" / "S-12-sasaah-tool-inventory" / "inventory" / "sasaah-revit-mcp.json"
SCHEMAS = PACKAGE_ROOT / "tests" / "fakes" / "sasaah_revit" / "schemas.json"

# Spec 0011 section 4.4 table: the 21 allowlisted MCP names (plan 0011 T2).
ALLOWLISTED_TOOLS = frozenset(
    {
        "revit_connection_status",
        "revit_ping",
        "revit_get_current_target",
        "revit_list_available_targets",
        "revit_get_model_metadata",
        "revit_list_levels",
        "revit_list_grids",
        "revit_list_elements",
        "revit_get_element_details",
        "revit_get_element_parameters",
        "revit_get_type_parameters",
        "revit_get_available_family_types",
        "revit_list_family_types_in_family",
        "revit_list_worksets",
        "revit_get_model_warnings_summary",
        "revit_open_model",
        "revit_duplicate_family_type",
        "revit_set_type_parameter_values",
        "revit_set_element_parameter_values",
        "revit_set_parameter_value_by_guid",
        "revit_change_element_type",
    }
)


def _load(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        data = json.load(handle)
    assert isinstance(data, dict)
    return data


def _mcp_name(tool: dict[str, Any]) -> str:
    """The MCP tool name the server lists (inventory `mcp_name`, else `name`)."""
    name = tool.get("mcp_name") or tool["name"]
    assert isinstance(name, str)
    return name


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
    """AC30: the fake's tools equal the inventory schemas for every allowlisted tool."""
    inventory = _inventory()
    fake = _load(SCHEMAS)
    expected_schemas = {
        _mcp_name(tool): tool["input_schema"]
        for tool in inventory["tools"]
        if _mcp_name(tool) in ALLOWLISTED_TOOLS
    }
    expected_kinds = {
        _mcp_name(tool): tool["server_kind"] for tool in inventory["tools"] if _mcp_name(tool) in ALLOWLISTED_TOOLS
    }
    actual_schemas = {tool["name"]: tool["input_schema"] for tool in fake["tools"]}
    actual_kinds = {tool["name"]: tool.get("server_kind") for tool in fake["tools"]}
    assert fake["sasaah_commit"] == inventory["sasaah_commit"]
    assert len(fake["tools"]) == len(actual_schemas)
    assert set(actual_schemas) == ALLOWLISTED_TOOLS
    assert actual_schemas == expected_schemas
    assert actual_kinds == expected_kinds
