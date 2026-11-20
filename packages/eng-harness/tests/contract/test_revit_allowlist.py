"""Contract tests of the Revit fake schemas and allowlist (plan 0011 T2, T3; spec 0011 AC2, AC30)."""

import json
from pathlib import Path
from typing import Any

from helpers import load_json_dict, load_repo_json

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
INVENTORY = REPO_ROOT / "spikes" / "S-12-sasaah-tool-inventory" / "inventory" / "sasaah-revit-mcp.json"
SCHEMAS = PACKAGE_ROOT / "tests" / "fakes" / "sasaah_revit" / "schemas.json"

# Spec 0011 section 4.4 table: the 21 allowlisted MCP names (plan 0011 T2, T3).
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
_WRITE_TOOLS = frozenset(
    {
        "revit_open_model",
        "revit_duplicate_family_type",
        "revit_set_type_parameter_values",
        "revit_set_element_parameter_values",
        "revit_set_parameter_value_by_guid",
        "revit_change_element_type",
    }
)
_READ_ROLE_TOOLS = ALLOWLISTED_TOOLS - _WRITE_TOOLS


def _mcp_name(tool: dict[str, Any]) -> str:
    """The MCP tool name the server lists (inventory `mcp_name`, else `name`)."""
    name = tool.get("mcp_name") or tool["name"]
    assert isinstance(name, str)
    return name


def _inventory() -> dict[str, Any]:
    """The S-12 inventory at the repository root, outside this package."""
    return load_repo_json(
        INVENTORY,
        reason="the S-12 inventory is outside the package copy that the mutation step runs (B-369); expires 2026-12-31",
    )


def test_fake_schemas_match_inventory() -> None:
    """AC30: the fake's tools equal the inventory schemas for every allowlisted tool."""
    inventory = _inventory()
    fake = load_json_dict(SCHEMAS)
    expected_schemas = {
        _mcp_name(tool): tool["input_schema"] for tool in inventory["tools"] if _mcp_name(tool) in ALLOWLISTED_TOOLS
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


def test_fake_process_schemas_match_inventory(tmp_path: Path) -> None:
    """AC30: the running Revit fake process serves the inventory schemas for the allowlisted tools."""
    from fakes.sasaah_revit.test_server import Rpc

    inventory = _inventory()
    expected = {
        _mcp_name(tool): tool["input_schema"] for tool in inventory["tools"] if _mcp_name(tool) in ALLOWLISTED_TOOLS
    }
    control = tmp_path / "control.json"
    control.write_text(json.dumps({"faults": [], "seed": {}}), encoding="utf-8")
    rpc = Rpc(control)
    try:
        listed = rpc.request("tools/list", {})["tools"]
        actual = {tool["name"]: tool["inputSchema"] for tool in listed}
        assert len(listed) == len(actual)
        assert set(actual) == ALLOWLISTED_TOOLS
        assert actual == expected
    finally:
        rpc.close()


def test_against_inventory() -> None:
    """AC2: the allowlist names only inventory tools of the pinned build; none excluded or escape-hatch."""
    from eng_harness.adapters.revit import revit_allowlist

    inventory = _inventory()
    by_name = {_mcp_name(tool): tool for tool in inventory["tools"]}
    allowlist = revit_allowlist()
    assert allowlist.sasaah_commit == inventory["sasaah_commit"]
    assert allowlist.fingerprint_source == "s12-inventory"
    assert set(allowlist.tool_names) == ALLOWLISTED_TOOLS
    for tool in allowlist.tools:
        item = by_name[tool.name]  # KeyError: a tool absent from the pinned build
        assert not item["excluded_from_allowlist"], tool.name
        assert item["classification"] != "escape-hatch", tool.name
        expected_kind = "session" if item["classification"] == "file" else item["classification"]
        assert tool.kind == expected_kind, tool.name
        if item["server_kind"] == "read":
            assert tool.effect == "read", tool.name
        if item["server_kind"] in ("write", "destructive"):
            assert tool.effect == "write", tool.name
        assert tool.units == "none", tool.name
        if tool.name in _WRITE_TOOLS:
            assert tool.confirm == "host_dialog", tool.name
            assert "write" in tool.products
            assert "read" not in tool.products
        else:
            assert tool.confirm == "never", tool.name
            assert set(tool.products) == {"read", "write"}


def test_fingerprints_from_inventory() -> None:
    """AC2: the two role fingerprints computed from the S-12 inventory equal the pinned header values."""
    from eng_harness.adapters.revit import revit_allowlist
    from eng_harness.servers._buildcheck import tool_list_fingerprint

    allowlist = revit_allowlist()
    assert allowlist.fingerprint_source == "s12-inventory"
    inventory = _inventory()
    by_name = {_mcp_name(tool): tool for tool in inventory["tools"]}
    read = allowlist.for_product("read")
    write = allowlist.for_product("write")
    assert set(read.tool_names) == _READ_ROLE_TOOLS
    assert set(write.tool_names) == ALLOWLISTED_TOOLS
    read_schemas = {name: by_name[name]["input_schema"] for name in read.tool_names}
    write_schemas = {name: by_name[name]["input_schema"] for name in write.tool_names}
    assert set(read_schemas) == _READ_ROLE_TOOLS
    assert set(write_schemas) == ALLOWLISTED_TOOLS
    assert tool_list_fingerprint(read_schemas) == allowlist.fingerprint["read"] == read.tool_fingerprint
    assert tool_list_fingerprint(write_schemas) == allowlist.fingerprint["write"] == write.tool_fingerprint
