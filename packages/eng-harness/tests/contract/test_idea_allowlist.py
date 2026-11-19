"""Contract tests of the IDEA fake and allowlist schemas (plan 0014 T2; spec 0014 AC21)."""

from pathlib import Path

from helpers import load_json_dict, load_repo_json

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
INVENTORY = REPO_ROOT / "spikes" / "S-12-sasaah-tool-inventory" / "inventory" / "sasaah-idea-mcp.json"
SCHEMAS = PACKAGE_ROOT / "tests" / "fakes" / "sasaah_idea" / "schemas.json"

SERVED_TOOLS = frozenset(
    {
        "idea_status",
        "idea_open_project",
        "idea_close_project",
        "idea_list_connections",
        "idea_calculate",
        "idea_get_check_results",
        "idea_native_get_loads",
        "idea_native_set_loads",
        "idea_native_calculate",
    }
)
SCRIPT_TOOL = "idea_run_script"


def test_fake_schemas_match_inventory() -> None:
    """AC21: the fake's tool schemas equal the S-12 inventory for the 9 served tools and idea_run_script."""
    inventory = load_repo_json(
        INVENTORY,
        reason="the S-12 inventory is outside the package copy that the mutation step runs (B-369); expires 2026-12-31",
    )
    fake = load_json_dict(SCHEMAS)
    expected_names = SERVED_TOOLS | {SCRIPT_TOOL}
    expected_schemas = {t["name"]: t["input_schema"] for t in inventory["tools"] if t["name"] in expected_names}
    expected_kinds = {t["name"]: t["server_kind"] for t in inventory["tools"] if t["name"] in expected_names}
    actual_schemas = {t["name"]: t["input_schema"] for t in fake["tools"]}
    actual_kinds = {t["name"]: t.get("server_kind") for t in fake["tools"]}
    assert fake["sasaah_commit"] == inventory["sasaah_commit"]
    assert len(fake["tools"]) == len(actual_schemas)
    assert set(actual_schemas) == expected_names
    assert actual_schemas == expected_schemas
    assert actual_kinds == expected_kinds
