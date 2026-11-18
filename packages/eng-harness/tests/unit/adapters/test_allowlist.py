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
    f'tool_fingerprint = "{SHA}"\nfingerprint_source = "s12-inventory"\n'
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
