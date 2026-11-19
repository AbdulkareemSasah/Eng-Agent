"""Allowlist data, descriptors, escape-hatch refusal and release marks.

Plan 0002 T6 and T20; spec 0002 AC16, AC38, AC41 and AC42.
"""

import json
from typing import Any

import pytest

from eng_harness.adapters import Allowlist, AllowlistError, ToolDescriptor, load_allowlist
from eng_harness.adapters.csi import csi_allowlist

COMMIT = "a" * 40
SHA = "b" * 64
HEADER = (
    f'adapter = "test-adapter"\nsasaah_commit = "{COMMIT}"\nalso_tested_commits = []\n'
    f'fingerprint = {{ ETABS = "{SHA}" }}\nfingerprint_source = "s12-inventory"\n'
)
REQUIRED = ("name", "kind", "timeout_class", "effect", "action", "args_model", "units", "confirm", "products")


def _value(item: object) -> str:
    return "[" + ", ".join(_value(i) for i in item) + "]" if isinstance(item, list) else json.dumps(item)


def _tool(**over: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "name": "csi_list_frames",
        "kind": "read",
        "timeout_class": "call",
        "effect": "read",
        "action": "plain",
        "args_model": "ListFramesArgs",
        "result_kind": "model.frame_placements/1",
        "units": "token",
        "confirm": "never",
        "products": ["ETABS"],
    }
    fields.update(over)
    return {key: value for key, value in fields.items() if value is not None}


def _text(*tools: dict[str, Any], header: str = HEADER) -> str:
    rows = ",\n".join("{ " + ", ".join(f"{k} = {_value(v)}" for k, v in t.items()) + " }" for t in tools)
    return f"{header}tool = [\n{rows}\n]\n"


def _load(*tools: dict[str, Any], header: str = HEADER, route: str | None = None) -> Allowlist:
    text = _text(*tools, header=header)
    if route is None:
        return load_allowlist(text, "test.toml")
    return load_allowlist(text, "test.toml", route=route)


def _unit(tool: str, field: str, status: str, unit: str | None = None) -> str:
    lines = ["[[unit]]", f'tool = "{tool}"', f'field = "{field}"', f'unit_status = "{status}"']
    if unit is not None:
        lines.append(f'unit = "{unit}"')
    return "\n".join(lines) + "\n"


def test_entries_complete() -> None:
    allowlist = _load(
        _tool(),
        _tool(
            name="csi_assign_frame_section",
            kind="write",
            effect="write",
            readback="frame_section",
            args_model="AssignFrameSectionArgs",
            units="none",
        ),
    )
    read, write = allowlist.tools
    assert isinstance(read, ToolDescriptor)
    assert (read.name, read.kind, read.timeout_class, read.effect, read.action) == (
        "csi_list_frames",
        "read",
        "call",
        "read",
        "plain",
    )
    assert (read.args_model, read.result_kind, read.units, read.confirm) == (
        "ListFramesArgs",
        "model.frame_placements/1",
        "token",
        "never",
    )
    assert (read.products, read.readback, read.release, read.release_record) == (("ETABS",), None, "released", None)
    assert write.readback == "frame_section"
    assert (allowlist.adapter, allowlist.sasaah_commit, allowlist.also_tested_commits) == ("test-adapter", COMMIT, ())
    assert (allowlist.tool_fingerprint, allowlist.fingerprint_source) == (SHA, "s12-inventory")
    assert allowlist.descriptor("csi_list_frames") is read


def test_descriptor_of_unlisted_tool_raises() -> None:
    with pytest.raises(KeyError, match="csi_nothing"):
        _load(_tool()).descriptor("csi_nothing")


@pytest.mark.parametrize("missing", REQUIRED)
def test_missing_field_refused(missing: str) -> None:
    with pytest.raises(AllowlistError, match=missing):
        _load(_tool(**{missing: None}))


@pytest.mark.parametrize(
    "over",
    [
        {"kind": "script"},
        {"timeout_class": "fast"},
        {"effect": "modify"},
        {"action": "run"},
        {"units": "metric"},
        {"confirm": "always"},
        {"products": []},
        {"args_model": "list_frames_args"},
        {"surprise": 1},
    ],
)
def test_invalid_values_refused(over: dict[str, Any]) -> None:
    with pytest.raises(AllowlistError, match="csi_list_frames|" + next(iter(over))):
        _load(_tool(**over))


def test_write_needs_a_readback_helper() -> None:
    with pytest.raises(AllowlistError, match="readback"):
        _load(_tool(name="csi_add_load_pattern", kind="write", effect="write"))


def test_duplicate_names_refused() -> None:
    with pytest.raises(AllowlistError, match="csi_list_frames"):
        _load(_tool(), _tool())


@pytest.mark.parametrize(
    "header",
    [
        HEADER.replace(COMMIT, "short"),
        HEADER.replace(SHA, "c" * 63),
        HEADER.replace("s12-inventory", "guess"),
        HEADER.replace("also_tested_commits = []", 'also_tested_commits = ["zz"]'),
        HEADER.replace('adapter = "test-adapter"\n', ""),
        HEADER + "routes = []\n",
    ],
)
def test_header_validated(header: str) -> None:
    with pytest.raises(AllowlistError):
        _load(_tool(), header=header)


def test_not_toml_refused() -> None:
    with pytest.raises(AllowlistError, match=r"test\.toml"):
        load_allowlist("tool = [", "test.toml")


ESCAPE_HATCH_NAMES = (
    "csi_run_script",
    "csi_db_tables_apply",
    "csi_invoke",
    "csi_object_add",
    "csi_object_delete",
    "csi_object_set",
    "csi_object_get",
    "idea_run_script",
    "compile_and_run",
    "revit_send_code_to_revit",
    "dev_hot_run",
    "dev_hot_unload",
    "run_baked_tool",
    "batch_execute",
    "run_synapse_command",
    "revit_accept_bake_suggestion",
    "revit_dismiss_bake_suggestion",
    "revit_list_bake_suggestions",
)


@pytest.mark.parametrize("name", ESCAPE_HATCH_NAMES)
def test_escape_hatches_refused(name: str) -> None:
    with pytest.raises(AllowlistError, match=name):
        _load(_tool(name=name))


@pytest.mark.parametrize("name", ["x_script_y", "x_invoke_y", "x_eval_y", "x_tables_apply", "csi_list_scripts"])
def test_escape_hatch_patterns_refused(name: str) -> None:
    with pytest.raises(AllowlistError, match=name):
        _load(_tool(name=name))


def test_packaged_allowlist_has_no_escape_hatch() -> None:
    names = {tool.name for tool in csi_allowlist().tools}
    assert names
    assert names.isdisjoint(ESCAPE_HATCH_NAMES)
    assert not [n for n in names if any(m in n for m in ("script", "invoke", "eval", "tables_apply"))]


def test_release_marks() -> None:
    plain = _tool()
    marked = _tool(
        name="csi_add_load_pattern",
        kind="write",
        effect="write",
        readback="load_pattern",
        release="unreleased",
        release_record="docs/gaps/csi-add-load-pattern.md",
    )
    assert _load(plain).unreleased_tools() == {}
    allowlist = _load(plain, marked)
    assert allowlist.unreleased_tools() == {"csi_add_load_pattern": "docs/gaps/csi-add-load-pattern.md"}
    assert allowlist.descriptor("csi_list_frames").release == "released"


@pytest.mark.parametrize(
    "over",
    [
        {"release": "unreleased"},
        {"release": "unreleased", "release_record": ""},
        {"release": "released", "release_record": "docs/gaps/x.md"},
        {"release_record": "docs/gaps/x.md"},
        {"release": "draft", "release_record": "docs/gaps/x.md"},
        {"release": "unreleased", "release_record": "/records/x.md"},
        {"release": "unreleased", "release_record": "C:/x.md"},
        {"release": "unreleased", "release_record": "../x.md"},
    ],
)
def test_release_marks_refused(over: dict[str, Any]) -> None:
    with pytest.raises(AllowlistError, match="release"):
        _load(_tool(**over))


def test_packaged_allowlist_has_no_unreleased_tool() -> None:
    allowlist = csi_allowlist()
    assert allowlist.adapter == "sasaah-csi-mcp"
    assert allowlist.unreleased_tools() == {}


ROUTES = HEADER + 'routes = ["native", "rest"]\n'


def test_routes_declared() -> None:
    """AC41: a header that declares routes requires every entry's routes to be a non-empty subset of them."""
    native = _tool(name="read_native", routes=["native"])
    both = _tool(name="read_both", routes=["native", "rest"])
    rest = _tool(name="read_rest", routes=["rest"])
    by_rest = _load(native, both, rest, header=ROUTES, route="rest")
    by_native = _load(native, both, rest, header=ROUTES, route="native")
    assert by_rest.routes == by_native.routes == ("native", "rest")
    assert {tool.name: tool.routes for tool in (*by_rest.tools, *by_native.tools)} == {
        "read_native": ("native",),
        "read_both": ("native", "rest"),
        "read_rest": ("rest",),
    }
    refused = (
        _tool(name="read_native"),
        _tool(name="read_native", routes=[]),
        _tool(name="read_native", routes=["other"]),
        _tool(name="read_native", routes=["native", "other"]),
    )
    for tool in refused:
        with pytest.raises(AllowlistError, match="routes"):
            _load(tool, header=ROUTES, route="native")
    with pytest.raises(AllowlistError, match="routes"):
        _load(_tool(routes=["native"]))
    with pytest.raises(AllowlistError, match="routes"):
        _load(_tool(), header=HEADER + "routes = []\n", route="native")


def test_route_filter() -> None:
    """AC41: one route is served; another route is refused; a route on an allowlist with none is a load error."""
    native = _tool(name="read_native", routes=["native"])
    both = _tool(name="read_both", routes=["native", "rest"])
    rest = _tool(name="read_rest", routes=["rest"])
    loaded = _load(native, both, rest, header=ROUTES, route="native")
    assert [tool.name for tool in loaded.tools] == ["read_native", "read_both"]
    assert loaded.tool_names == frozenset({"read_native", "read_both", "read_rest"})
    assert loaded.build_expectation().tool_names == loaded.tool_names
    assert loaded.descriptor("read_native").name == "read_native"
    with pytest.raises(KeyError, match="read_rest"):
        loaded.descriptor("read_rest")
    with pytest.raises(AllowlistError, match="route"):
        _load(native, both, rest, header=ROUTES)
    with pytest.raises(AllowlistError, match="route"):
        _load(native, both, rest, header=ROUTES, route="other")
    with pytest.raises(AllowlistError, match="route"):
        _load(_tool(), route="native")


def test_unit_header_entries() -> None:
    """AC42: [[unit]] entries are on Allowlist.units and on the descriptor of an allowlisted tool."""
    tables = (
        _unit("csi_list_frames", "length", "declared", "mm")
        + _unit("csi_list_frames", "force", "confirmed", "kN")
        + _unit("csi_list_frames", "note", "missing")
    )
    loaded = load_allowlist(_text(_tool()) + tables, "test.toml")
    assert [(item.tool, item.field, item.unit, item.unit_status) for item in loaded.units] == [
        ("csi_list_frames", "length", "mm", "declared"),
        ("csi_list_frames", "force", "kN", "confirmed"),
        ("csi_list_frames", "note", None, "missing"),
    ]
    assert loaded.descriptor("csi_list_frames").unit_header == loaded.units
    bad = (
        _unit("csi_list_frames", "length", "guessed", "mm"),
        _unit("csi_list_frames", "length", "missing", "mm"),
        _unit("csi_list_frames", "length", "declared"),
        _unit("csi_list_frames", "length", "confirmed"),
        _unit("not_a_tool", "length", "declared", "mm"),
        _unit("not_a_tool", "length", "confirmed", "kN"),
        _unit("idea_run_script", "body", "missing"),
        _unit("host_script_tool", "body", "missing"),
    )
    for table in bad:
        with pytest.raises(AllowlistError):
            load_allowlist(_text(_tool()) + table, "test.toml")
    with pytest.raises(AllowlistError, match="unit_header"):
        _load(_tool(unit_header=[]))


def test_unit_header_missing_on_unserved_tool() -> None:
    """AC42: status missing may name a tool the allowlist does not serve; it is on no descriptor."""
    loaded = load_allowlist(_text(_tool()) + _unit("host_set_loads", "force", "missing"), "test.toml")
    assert [(item.tool, item.field, item.unit, item.unit_status) for item in loaded.units] == [
        ("host_set_loads", "force", None, "missing"),
    ]
    assert loaded.descriptor("csi_list_frames").unit_header == ()
    assert [tool.name for tool in loaded.tools] == ["csi_list_frames"]
    assert loaded.tool_names == frozenset({"csi_list_frames"})
    with pytest.raises(KeyError, match="host_set_loads"):
        loaded.descriptor("host_set_loads")


HEADER_PRODUCTS = (
    f'adapter = "test-adapter"\nsasaah_commit = "{COMMIT}"\nalso_tested_commits = []\n'
    f'fingerprint = {{ ETABS = "{SHA}", SAFE = "{"c" * 64}" }}\nfingerprint_source = "s12-inventory"\n'
)


def test_tool_not_served_for_product() -> None:
    """AC3: loaded for a product, only the entries that list it are served; the others are not on the allowlist."""
    both = _tool(name="csi_list_frames", products=["ETABS", "SAFE"])
    etabs_only = _tool(name="csi_results_story_drifts", products=["ETABS"])
    text = _text(both, etabs_only, header=HEADER_PRODUCTS)
    safe = load_allowlist(text, "test.toml", product="SAFE")
    assert [tool.name for tool in safe.tools] == ["csi_list_frames"]
    assert safe.tool_names == frozenset({"csi_list_frames"})
    with pytest.raises(KeyError, match="csi_results_story_drifts"):
        safe.descriptor("csi_results_story_drifts")
    etabs = load_allowlist(text, "test.toml", product="ETABS")
    assert etabs.tool_names == frozenset({"csi_list_frames", "csi_results_story_drifts"})
    assert (etabs.tool_fingerprint, safe.tool_fingerprint) == (SHA, "c" * 64)
    assert etabs.build_expectation().product == "ETABS"
    assert safe.build_expectation().product == "SAFE"


def test_header_pins_every_listed_product_and_only_those() -> None:
    """Spec 0008 4.1: one fingerprint entry per product, none missing, none without an entry that lists it."""
    with pytest.raises(AllowlistError, match="no entry for product SAFE"):
        _load(_tool(products=["ETABS", "SAFE"]))
    with pytest.raises(AllowlistError, match="product SAFE is listed by no allowlist entry"):
        _load(_tool(), header=HEADER_PRODUCTS)
    with pytest.raises(AllowlistError, match="fingerprint"):  # the single value of spec 0002 is gone
        _load(_tool(), header=HEADER.replace("fingerprint = { ETABS =", "tool_fingerprint = { ETABS ="))
    with pytest.raises(AllowlistError, match="fingerprint"):
        _load(_tool(), header=HEADER.replace(SHA, "b" * 63))
    with pytest.raises(AllowlistError, match="fingerprint"):
        _load(_tool(), header=HEADER.replace("fingerprint = { ETABS = ", "fingerprint = {} #"))


def test_for_product() -> None:
    """The product a load serves: chosen once, repeatable, never switched; unchosen with several is an error."""
    text = _text(
        _tool(name="csi_list_frames", products=["ETABS", "SAFE"]), _tool(name="csi_results_story_drifts"),
        header=HEADER_PRODUCTS,
    )  # fmt: skip
    full = load_allowlist(text, "test.toml")
    assert len(full.tools) == 2
    with pytest.raises(ValueError, match="several products"):
        _ = full.product
    with pytest.raises(ValueError, match="several products"):
        full.build_expectation()
    safe = full.for_product("SAFE")
    assert (safe.product, safe.tool_fingerprint, [t.name for t in safe.tools]) == (
        "SAFE",
        "c" * 64,
        ["csi_list_frames"],
    )
    assert safe.for_product("SAFE") is safe
    with pytest.raises(AllowlistError, match="already loaded for product SAFE, not ETABS"):
        safe.for_product("ETABS")
    with pytest.raises(AllowlistError, match="no fingerprint for product STAAD"):
        full.for_product("STAAD")
    with pytest.raises(AllowlistError, match=r"test.toml: the header pins no fingerprint for product STAAD"):
        load_allowlist(text, "test.toml", product="STAAD")
    assert _load(_tool()).product == "ETABS"  # a header that pins one product needs no choice


def test_product_with_routes() -> None:
    """A route-filtered load still names every entry of the product in the fingerprint's tool set (AC41, AC4)."""
    header = HEADER_PRODUCTS + 'routes = ["native", "rest"]\n'
    both = ["ETABS", "SAFE"]
    text = _text(
        _tool(name="read_native", routes=["native"], products=both),
        _tool(name="read_rest", routes=["rest"], products=both),
        _tool(name="safe_native", routes=["native"], products=["SAFE"]),
        _tool(name="etabs_rest", routes=["rest"]),
        header=header,
    )
    by_route_first = load_allowlist(text, "test.toml", route="native").for_product("SAFE")
    by_both = load_allowlist(text, "test.toml", route="native", product="SAFE")
    for loaded in (by_route_first, by_both):
        assert [tool.name for tool in loaded.tools] == ["read_native", "safe_native"]
        assert loaded.tool_names == frozenset({"read_native", "read_rest", "safe_native"})
        assert loaded.tool_fingerprint == "c" * 64
    etabs = load_allowlist(text, "test.toml", route="native", product="ETABS")
    assert [tool.name for tool in etabs.tools] == ["read_native"]
    assert etabs.tool_names == frozenset({"read_native", "read_rest", "etabs_rest"})


_SAFE_TOOLS = frozenset(
    {
        "csi_status",
        "csi_launch",
        "csi_attach",
        "csi_exit",
        "csi_open_model",
        "csi_save_model",
        "csi_model_info",
        "csi_list_points",
        "csi_list_areas",
        "csi_list_frames",
        "csi_list_grids",
        "csi_list_area_sections",
        "csi_list_materials",
        "csi_list_load_patterns",
        "csi_list_load_cases",
        "csi_list_load_combos",
        "csi_db_table_read",
        "csi_db_table_fields",
        "csi_set_point_load",
        "csi_add_load_pattern",
        "csi_add_load_combo",
        "csi_delete_load_combo",
        "csi_assign_area_section",
        "csi_run_analysis",
        "csi_analysis_status",
        "csi_results_base_reactions",
        "csi_results_joint_reactions",
    }
)
_NOT_SAFE_TOOLS = (
    "csi_db_tables_apply",
    "csi_delete_object",
    "csi_new_model",
    "csi_new_blank_model",
    "csi_define_wall_section",
    "csi_design_run",
    "csi_design_results",
    "csi_results_story_drifts",
    "csi_list_stories",
    "csi_list_frame_sections",
    "csi_results_frame_forces",
    "csi_assign_frame_section",
    "csi_set_frame_load_distributed",
    "csi_set_area_load_uniform",
    "csi_set_point_restraint",
    "csi_detach",
)


def test_safe_entries_complete() -> None:
    """AC3, AC4: packaged CSI allowlist serves the 27 SAFE entries and keeps ETABS unchanged."""
    full = csi_allowlist()
    safe = full.for_product("SAFE")
    etabs = full.for_product("ETABS")
    assert safe.product == "SAFE"
    assert safe.build_expectation().product == "SAFE"
    assert safe.tool_names == _SAFE_TOOLS
    assert {tool.name for tool in safe.tools} == _SAFE_TOOLS
    for tool in safe.tools:
        assert "SAFE" in tool.products
        if tool.effect == "write":
            assert tool.readback is not None
    for excluded in _NOT_SAFE_TOOLS:
        assert excluded not in safe.tool_names
        with pytest.raises(KeyError, match=excluded):
            safe.descriptor(excluded)

    point_load = safe.descriptor("csi_set_point_load")
    assert (
        point_load.kind,
        point_load.timeout_class,
        point_load.effect,
        point_load.action,
        point_load.args_model,
        point_load.units,
        point_load.confirm,
        point_load.readback,
        point_load.products,
    ) == ("write", "call", "write", "plain", "SetPointLoadArgs", "token", "never", "point_load_table", ("SAFE",))

    base_reactions = safe.descriptor("csi_results_base_reactions")
    assert (
        base_reactions.kind,
        base_reactions.timeout_class,
        base_reactions.effect,
        base_reactions.action,
        base_reactions.args_model,
        base_reactions.result_kind,
        base_reactions.units,
        base_reactions.confirm,
        base_reactions.products,
    ) == (
        "read",
        "call",
        "read",
        "plain",
        "ResultsBaseReactionsArgs",
        "harness.base_reactions/1",
        "token",
        "never",
        ("SAFE",),
    )

    load_cases = safe.descriptor("csi_list_load_cases")
    assert (load_cases.kind, load_cases.effect, load_cases.args_model, load_cases.units, load_cases.products) == (
        "read",
        "read",
        "ListLoadCasesArgs",
        "none",
        ("SAFE",),
    )
    table_fields = safe.descriptor("csi_db_table_fields")
    assert (
        table_fields.kind,
        table_fields.effect,
        table_fields.args_model,
        table_fields.units,
        table_fields.products,
    ) == ("read", "read", "DbTableFieldsArgs", "none", ("SAFE",))

    assert etabs.tool_fingerprint == "67e0f08ace144fdc41f43882b6671c4296899b36bbfb122433ef879c2e2ebdd1"
    for safe_only in ("csi_list_load_cases", "csi_db_table_fields", "csi_set_point_load", "csi_results_base_reactions"):
        assert safe_only not in etabs.tool_names


def test_escape_hatches_refused_for_safe() -> None:
    """AC3: escape hatches are absent from the SAFE allowlist and refused at load for product SAFE."""
    safe = csi_allowlist().for_product("SAFE")
    names = {tool.name for tool in safe.tools}
    assert names
    assert names.isdisjoint(ESCAPE_HATCH_NAMES)
    assert not [n for n in names if any(m in n for m in ("script", "invoke", "eval", "tables_apply"))]
    etabs_entry = _tool(name="csi_list_frames", products=["ETABS"])
    for name in (*ESCAPE_HATCH_NAMES, "x_script_y", "x_invoke_y", "x_eval_y", "x_tables_apply"):
        text = _text(etabs_entry, _tool(name=name, products=["SAFE"]), header=HEADER_PRODUCTS)
        with pytest.raises(AllowlistError, match=name):
            load_allowlist(text, "test.toml", product="SAFE")
