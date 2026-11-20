"""Unit tests of the Revit allowlist data and argument models (plan 0011 T3; spec 0011 AC2, section 4.4)."""

from __future__ import annotations

import tomllib
from importlib.resources import files

import pytest
from eng_contract.errors import ContractError, ErrorCode

from eng_harness.adapters._allowlist import AllowlistError, load_allowlist

# Spec 0011 section 4.4: the 21 allowlisted MCP names.
_ALLOWLISTED = frozenset(
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
_READ_ROLE_TOOLS = _ALLOWLISTED - _WRITE_TOOLS
# Spec 0011 section 4.4 deny list (exact MCP names).
_DENY_MCP = (
    "revit_send_code_to_revit",
    "revit_compile_and_run",
    "revit_dev_hot_run",
    "revit_dev_hot_unload",
    "revit_dev_hot_sessions",
    "revit_run_baked_tool",
    "revit_list_baked_tools",
    "revit_list_bake_suggestions",
    "revit_accept_bake_suggestion",
    "revit_dismiss_bake_suggestion",
    "revit_batch_execute",
    "revit_run_synapse_command",
    "revit_shutdown_bridge",
    "revit_authenticate",
    "revit_prepare_destructive",
    "revit_switch_target",
    "revit_get_change_records",
    "revit_record_change",
)
_ENTRY_FIELDS = (
    "name",
    "kind",
    "timeout_class",
    "effect",
    "action",
    "args_model",
    "result_kind",
    "units",
    "confirm",
    "readback",
    "products",
)


def test_entries_complete() -> None:
    """AC2: the packaged allowlist has the 21 section 4.4 entries with attended writes and role products."""
    from eng_harness.adapters.revit import _tools as revit_tools
    from eng_harness.adapters.revit import revit_allowlist

    full = revit_allowlist()
    assert full.adapter == "sasaah-revit-mcp"
    assert full.fingerprint_source == "s12-inventory"
    assert set(full.fingerprint) == {"read", "write"}
    assert set(full.tool_names) == _ALLOWLISTED
    assert {tool.name for tool in full.tools} == _ALLOWLISTED
    assert len(full.tools) == 21

    read = full.for_product("read")
    write = full.for_product("write")
    assert read.tool_names == _READ_ROLE_TOOLS
    assert {tool.name for tool in read.tools} == _READ_ROLE_TOOLS
    assert write.tool_names == _ALLOWLISTED
    assert {tool.name for tool in write.tools} == _ALLOWLISTED

    for tool in full.tools:
        for field in _ENTRY_FIELDS:
            assert hasattr(tool, field), field
        assert tool.units == "none"
        assert "read" in tool.products or "write" in tool.products
        if tool.name in _WRITE_TOOLS:
            assert tool.effect == "write"
            assert tool.timeout_class == "attended"
            assert tool.confirm == "host_dialog"
            assert tool.readback is not None
            assert tool.products == ("write",)
        else:
            assert tool.effect == "read"
            assert tool.confirm == "never"
            assert tool.readback is None
            assert set(tool.products) == {"read", "write"}
            assert tool.timeout_class in {"session", "call"}

    open_model = full.descriptor("revit_open_model")
    assert (open_model.kind, open_model.action, open_model.args_model, open_model.result_kind) == (
        "session",
        "open",
        "OpenModelArgs",
        "harness.revit_status/1",
    )
    assert open_model.readback == "revit_get_model_metadata"

    duplicate = full.descriptor("revit_duplicate_family_type")
    assert (duplicate.kind, duplicate.args_model, duplicate.result_kind) == (
        "write",
        "DuplicateFamilyTypeArgs",
        "harness.revit_write_result/1",
    )

    set_type = full.descriptor("revit_set_type_parameter_values")
    assert set_type.args_model == "SetTypeParameterValuesArgs"
    assert set_type.readback == "revit_get_type_parameters"

    # Argument models named by the allowlist exist and declare valueType / expected_instances / lengths.
    assert "value_type" in revit_tools.SetElementParameterValuesArgs.model_fields
    assert "value_type" in revit_tools.SetTypeParameterValuesArgs.model_fields
    assert "value_type" in revit_tools.SetParameterValueByGuidArgs.model_fields
    assert "expected_instances" in revit_tools.SetTypeParameterValuesArgs.model_fields
    assert "unit" in revit_tools.SetParameterValueByGuidArgs.model_fields  # length unit for GUID writes

    for tool in full.tools:
        assert hasattr(revit_tools, tool.args_model), f"{tool.name}: missing {tool.args_model}"


def test_escape_hatches_refused() -> None:
    """AC2: deny-list names, markers and auto valueType are refused; packaged list has none of them."""
    from eng_harness.adapters.revit import _tools as revit_tools
    from eng_harness.adapters.revit import revit_allowlist

    packaged = revit_allowlist()
    names = packaged.tool_names
    assert names.isdisjoint(_DENY_MCP)
    for name in names:
        assert not any(marker in name for marker in ("script", "invoke", "eval", "tables_apply"))

    header = (
        'adapter = "sasaah-revit-mcp"\n'
        'sasaah_commit = "61da80f61a6562c8e3553168056bc107e3f93013"\n'
        "also_tested_commits = []\n"
        f'fingerprint = {{ read = "{"a" * 64}", write = "{"b" * 64}" }}\n'
        'fingerprint_source = "s12-inventory"\n'
    )
    base_tool = (
        '{ name = "revit_list_levels", kind = "read", timeout_class = "call", effect = "read", '
        'action = "plain", args_model = "ListLevelsArgs", result_kind = "harness.revit_levels/1", '
        'units = "none", confirm = "never", products = ["read", "write"] }'
    )
    denied_fields = (
        'timeout_class = "call", effect = "read", action = "plain", args_model = "StatusArgs", '
        'units = "none", confirm = "never", products = ["read", "write"] }'
    )
    for denied in _DENY_MCP:
        text = f'{header}tool = [\n  {base_tool},\n  {{ name = "{denied}", kind = "read", {denied_fields},\n]\n'
        with pytest.raises(AllowlistError, match=denied):
            load_allowlist(text, "revit-escape.toml")

    for marker_name in ("revit_run_script", "revit_eval_formula", "revit_invoke_api", "revit_tables_apply"):
        text = f'{header}tool = [\n  {base_tool},\n  {{ name = "{marker_name}", kind = "read", {denied_fields},\n]\n'
        with pytest.raises(AllowlistError, match=marker_name):
            load_allowlist(text, "revit-marker.toml")

    # valueType is never auto (spec 0011 AC8); lengths use an explicit unit on GUID writes.
    with pytest.raises(ContractError) as auto:
        revit_tools.build_set_element_parameter_values_args(
            element_ids=[1],
            parameter_name="b",
            value="300",
            value_type="auto",
        )
    assert auto.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert auto.value.detail.field == "valueType"

    with pytest.raises(ContractError) as guid_auto:
        revit_tools.build_set_parameter_value_by_guid_args(
            element_ids=[1],
            guid="00000000-0000-0000-0000-000000000001",
            value="300",
            value_type="double",
            unit="auto",
            target="instance",
        )
    assert guid_auto.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert guid_auto.value.detail.field == "unit"

    sent = revit_tools.build_set_type_parameter_values_args(
        type_ids=[10],
        parameter_name="b",
        value="400",
        value_type="double",
        expected_instances=[1, 2],
    )
    assert "expected_instances" not in sent  # adapter-only; not a host argument
    assert sent["valueType"] == "double"
    assert sent["typeIds"] == [10]

    # Packaged TOML parses and never lists a denied name even before the loader deny check.
    raw = tomllib.loads(files("eng_harness.adapters.revit").joinpath("_allowlist.toml").read_text(encoding="utf-8"))
    listed = {entry["name"] for entry in raw["tool"]}
    assert listed == _ALLOWLISTED
    assert listed.isdisjoint(_DENY_MCP)
