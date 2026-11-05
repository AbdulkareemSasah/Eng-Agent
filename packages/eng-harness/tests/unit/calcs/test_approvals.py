"""approvals.yaml schema, loader and status resolution (plan 0003 T3; spec 0003 AC8, AC9, 4.5)."""

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest
from eng_contract.kinds import NEUTRAL_KINDS

from eng_harness._calc import _approvals
from eng_harness._calc._approvals import ApprovalsError, check_approvals, load_approvals, resolve_status
from eng_harness.calc import CalcRegistry, CalcStatus

_FIXTURES = Path(__file__).resolve().parents[2] / "data" / "calcs" / "fixture_calcs.py"
CALC_ID = "harness.fixture_sum"
OTHER_HASH = "cd" * 32
APPROVAL = """\
  - calc_id: harness.fixture_sum
    version: 3
    content_sha256: {digest}
    approver: owner
    date: 2026-01-31
    verification_record: docs/verification/calcs/harness.fixture_sum.md
    pull_request: 12
"""
WITHDRAWN = """\
  - calc_id: harness.fixture_sum
    version: 3
    content_sha256: {digest}
    date: 2026-02-01
    reason: Wrong clause
    advisory: Rerun every result of this calc
"""


@pytest.fixture(scope="module")
def fixtures() -> ModuleType:
    """The fixture calc module, loaded by path (it is test data, not a package)."""
    spec = importlib.util.spec_from_file_location("fixture_calcs", _FIXTURES)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["fixture_calcs"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def registry(fixtures: ModuleType) -> CalcRegistry:
    """A registry with the one fixture calc."""
    kinds = NEUTRAL_KINDS.extend({fixtures.OUTPUT_KIND: fixtures.FixtureOut})
    return CalcRegistry(kinds, [fixtures.fixture_sum])


def _block(text: str) -> str:
    return f" {text}\n" if text.startswith("[") else f"\n{text}"


def _write(tmp_path: Path, approvals: str = "[]", withdrawn: str = "[]", head: str = "schema: 1\n") -> Path:
    path = tmp_path / "approvals.yaml"
    path.write_text(f"{head}approvals:{_block(approvals)}withdrawn:{_block(withdrawn)}", encoding="utf-8")
    return path


def _status(registry: CalcRegistry, tmp_path: Path, approvals: str = "[]", withdrawn: str = "[]") -> CalcStatus:
    loaded = load_approvals(_write(tmp_path, approvals, withdrawn), registry)
    return resolve_status(registry[CALC_ID], registry.content_hash(CALC_ID), loaded)


def test_status_resolution(registry: CalcRegistry, tmp_path: Path) -> None:
    digest = registry.content_hash(CALC_ID)
    good = APPROVAL.format(digest=digest)
    assert registry[CALC_ID].verification == "draft"
    assert _status(registry, tmp_path) is CalcStatus.DRAFT
    assert _status(registry, tmp_path, good) is CalcStatus.APPROVED
    # a different hash or version is no match: the declared verification state applies
    assert _status(registry, tmp_path, APPROVAL.format(digest=OTHER_HASH)) is CalcStatus.DRAFT
    assert _status(registry, tmp_path, good.replace("version: 3", "version: 4")) is CalcStatus.DRAFT
    # a matching withdrawn entry wins over a matching approval, by hash or with "any"
    assert _status(registry, tmp_path, good, WITHDRAWN.format(digest=digest)) is CalcStatus.WITHDRAWN
    assert _status(registry, tmp_path, good, WITHDRAWN.format(digest="any")) is CalcStatus.WITHDRAWN
    assert _status(registry, tmp_path, "[]", WITHDRAWN.format(digest=OTHER_HASH)) is CalcStatus.DRAFT
    # a stale entry is reported, not failed, and the calc falls back to its declared state
    stale = load_approvals(_write(tmp_path, APPROVAL.format(digest=OTHER_HASH)), registry)
    assert [(f.kind, f.calc_id) for f in check_approvals(registry, stale)] == [("stale_approval", CALC_ID)]
    assert check_approvals(registry, load_approvals(_write(tmp_path, good), registry)) == []


def test_verified_declaration_is_kept_without_an_approval(registry: CalcRegistry, tmp_path: Path) -> None:
    loaded = load_approvals(_write(tmp_path), registry)
    definition = replace(registry[CALC_ID], verification="verified")
    assert resolve_status(definition, OTHER_HASH, loaded) is CalcStatus.VERIFIED


def test_file_validation(registry: CalcRegistry, tmp_path: Path) -> None:
    digest = registry.content_hash(CALC_ID)
    good = APPROVAL.format(digest=digest)
    loaded = load_approvals(_write(tmp_path, good, WITHDRAWN.format(digest="any")), registry)
    assert loaded.approvals[0].version == 3
    assert loaded.withdrawn[0].content_sha256 == "any"

    def failure(path: Path) -> tuple[str, str]:
        with pytest.raises(ApprovalsError) as caught:
            load_approvals(path, registry)
        assert caught.value.file == path.name
        return caught.value.reason, caught.value.path

    def bad(text: str, where: str, reason: str = "schema_invalid") -> None:
        assert failure(_write(tmp_path, text)) == (reason, where), text

    for field in ("approver", "date", "verification_record", "pull_request"):  # AC9: a required field is missing
        lines = [ln for ln in good.splitlines(keepends=True) if f" {field}:" not in ln]
        bad("".join(lines), f"approvals[0].{field}")
    bad(good.replace(digest, "xyz"), "approvals[0].content_sha256")
    bad(good.replace("2026-01-31", "2026-13-40"), "approvals[0].date")
    bad(good.replace("2026-01-31", "2026-1-31"), "approvals[0].date")
    bad(good.replace("docs/verification/calcs/", "docs/other/"), "approvals[0].verification_record")
    bad(good.replace("calcs/harness", "calcs/../harness"), "approvals[0].verification_record")
    bad(good + "    note: x\n", "approvals[0].note")
    bad(good + good, "")
    bad(good.replace("version: 3", "version: 0"), "approvals[0].version")
    bad(good.replace("version: 3", "version: 10000"), "approvals[0].version")
    bad(good.replace("pull_request: 12", "pull_request: 0"), "approvals[0].pull_request")
    bad(good.replace("approver: owner", "approver: ''"), "approvals[0].approver")
    bad(good.replace("approver: owner", "approver: '   '"), "approvals[0].approver")
    bad(good.replace("approver: owner", "approver: 123"), "approvals[0].approver")  # strict: no int to str
    bad(good.replace("harness.fixture_sum", "harness.nope"), "approvals[0].calc_id", "unknown_calc")
    assert failure(_write(tmp_path, good + "    approver: other\n"))[0] == "yaml_invalid"  # duplicate key
    # an accepted boundary: version 9999
    assert load_approvals(_write(tmp_path, good.replace("version: 3", "version: 9999")), registry).approvals[0].version
    withdrawn = WITHDRAWN.format(digest="any")

    def bad_withdrawn(text: str, where: str, reason: str = "schema_invalid") -> None:
        assert failure(_write(tmp_path, "[]", text)) == (reason, where), text

    bad_withdrawn(withdrawn.replace(CALC_ID, "harness.x"), "withdrawn[0].calc_id", "unknown_calc")
    bad_withdrawn(WITHDRAWN.format(digest="all"), "withdrawn[0].content_sha256")
    bad_withdrawn(withdrawn.replace("Wrong clause", "'  '"), "withdrawn[0].reason")
    bad_withdrawn(withdrawn.replace("Rerun every result of this calc", "'  '"), "withdrawn[0].advisory")
    bad_withdrawn(withdrawn.replace("Wrong clause", "5"), "withdrawn[0].reason")
    bad_withdrawn(withdrawn.replace("2026-02-01", "2026-2-1"), "withdrawn[0].date")
    # whole-file rules: schema number, extra top-level key, tags, anchors, missing file, wrong root
    assert failure(_write(tmp_path, head="schema: 2\n")) == ("schema_invalid", "schema")
    assert failure(_write(tmp_path, head="schema: 1\nextra: 1\n")) == ("schema_invalid", "extra")
    assert failure(_write(tmp_path, head="")) == ("schema_invalid", "schema")
    assert failure(_write(tmp_path, head="schema: !!int 1\n"))[0] == "yaml_invalid"
    assert failure(_write(tmp_path, head="schema: &a 1\n"))[0] == "yaml_invalid"
    root_list = tmp_path / "list.yaml"
    root_list.write_text("- 1\n", encoding="utf-8")
    assert failure(root_list) == ("schema_invalid", "")
    assert failure(tmp_path / "missing.yaml")[0] == "not_found"
    assert _approvals.APPROVALS_PATH.name == "approvals.yaml"


def test_check_approvals_reports_unregistered_calcs(registry: CalcRegistry, tmp_path: Path) -> None:
    text = APPROVAL.format(digest=OTHER_HASH).replace(CALC_ID, "harness.gone")
    loaded = load_approvals(_write(tmp_path, text), {"harness.gone"})
    assert [(f.kind, f.calc_id) for f in check_approvals(registry, loaded)] == [("unknown_calc", "harness.gone")]


def test_error_message_names_reason_and_path() -> None:
    assert str(ApprovalsError("schema_invalid", "approvals[0].date", "a.yaml")) == (
        "approvals invalid: schema_invalid at approvals[0].date"
    )
    assert str(ApprovalsError("schema_invalid", "")) == "approvals invalid: schema_invalid at <root>"
