"""The policy file ``.gate/forbidden.yml`` (spec 4.8, section 5): initial lists and validation."""

from __future__ import annotations

import pytest
from eng_dev_gate.checks.forbidden.engine import parse_config, scan_file
from eng_dev_gate.checks.forbidden.rules_a import RULES_A
from eng_dev_gate.results import UsageError
from support.forbidden import policy
from support.toy import POLICY_TEXT


def test_initial_lists() -> None:
    config = policy()
    assert config.escape_hatch.names == ["csi_run_script", "csi_db_tables_apply"]
    assert config.host_sdk.modules == ["win32com", "pythoncom", "pywintypes", "comtypes", "clr", "System", "Autodesk"]
    assert config.escape_hatch.patterns  # run/execute/evaluate, apply/write tables, forward arbitrary calls


@pytest.mark.parametrize(
    "text",
    [
        "",
        "- a list\n",
        "host_sdk: {modules: [clr]}\n",
        "escape_hatch: {names: [a], patterns: []}\n",
        "escape_hatch: {names: [a], patterns: ['(']}\nhost_sdk: {modules: [clr]}\n",
        "escape_hatch: {names: [a], patterns: []}\nhost_sdk: {modules: [clr]}\nextra: 1\n",
        "escape_hatch: {names: [''], patterns: []}\nhost_sdk: {modules: [clr]}\n",
        "escape_hatch: [unclosed\n",
    ],
)
def test_invalid_policy_is_a_usage_error(text: str) -> None:
    with pytest.raises(UsageError):
        parse_config(text, "forbidden.yml")


def test_policy_is_data_not_code() -> None:
    """The rules read the file: another name list flags that list and no longer the initial one."""
    config = parse_config(POLICY_TEXT.replace("csi_run_script", "other_name", 1), "forbidden.yml")
    data = b"a = 'other_name'\nb = 'csi_run_script'\n"
    findings = scan_file("p.py", "src/p.py", data, config, RULES_A)
    assert [(f.code, f.line) for f in findings] == [("FB001", 1)]


def test_initial_lists_part_2() -> None:
    config = policy()
    assert config.io_modules == [
        "os", "sys", "io", "pathlib", "shutil", "tempfile", "socket", "ssl", "http", "urllib", "subprocess",
        "sqlite3", "time", "datetime", "random", "secrets", "uuid", "requests", "httpx",
    ]  # fmt: skip
    assert config.cited.callables == ["Cited"]
    assert config.rationale.types == ["Rationale"]


@pytest.mark.parametrize("key", ["io_modules", "cited", "rationale"])
def test_policy_cannot_drop_a_rule_list(key: str) -> None:
    kept = [line for line in POLICY_TEXT.splitlines() if not line.startswith(key)]
    assert len(kept) < len(POLICY_TEXT.splitlines())
    with pytest.raises(UsageError):
        parse_config("\n".join(kept), "forbidden.yml")
