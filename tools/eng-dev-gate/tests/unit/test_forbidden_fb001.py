"""FB001 (spec 4.8, AC29): escape-hatch names and patterns, from the committed policy."""

from __future__ import annotations

from eng_dev_gate.report import Severity
from support.forbidden import lines, marked, scan

SOURCE = """\
TOOLS = ["csi_run_script", "csi_list_tools"]  # <-
csi_db_tables_apply(model)  # <-
handler = client.csi_run_script  # <-
from vendor import csi_db_tables_apply as apply_tables  # <-
invoke(csi_run_script=text)  # <-
def accept(csi_run_script): ...  # <-
def run_script(text): ...  # <-
async def Execute_Code(text): ...  # <-
class EvaluateExpression: ...  # <-
def apply_db_tables(rows): ...  # <-
def write_database_table(rows): ...  # <-
def forward_arbitrary_api_call(call): ...  # <-
def run_checks(): ...
def execute_plan(): ...
def write_table_of_contents(): ...
NOTE = "csi_run_script is not allowed"
OTHER = "csi_run_script_docs"
"""


def test_flags_name_and_pattern() -> None:
    findings = scan(SOURCE)
    expected = marked(SOURCE)
    assert lines(findings, "FB001") == expected
    assert {f.code for f in findings} == {"FB001"}
    assert len(findings) == len(expected)  # one finding per construct
    assert {f.severity for f in findings} == {Severity.ERROR}
    assert {f.path for f in findings} == {"pkgs/x/src/pkg/mod.py"}
    assert "csi_run_script" in next(f for f in findings if f.line == 1).message
