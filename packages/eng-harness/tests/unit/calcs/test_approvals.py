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

    def reason(path: Path) -> str:
        with pytest.raises(ApprovalsError) as caught:
            load_approvals(path, registry)
        return caught.value.reason

    for field in ("approver", "date", "verification_record", "pull_request"):  # AC9: a required field is missing
        lines = [ln for ln in good.splitlines(keepends=True) if f" {field}:" not in ln]
        assert reason(_write(tmp_path, "".join(lines))) == "schema_invalid", field
    schema_invalid = {
        "bad hash": good.replace(digest, "xyz"),
        "bad date": good.replace("2026-01-31", "2026-13-40"),
        "record outside folder": good.replace("docs/verification/calcs/", "docs/other/"),
        "record escapes folder": good.replace("calcs/harness", "calcs/../harness"),
        "extra key": good + "    note: x\n",
        "duplicate entry": good + good,
        "zero version": good.replace("version: 3", "version: 0"),
        "empty approver": good.replace("approver: owner", "approver: ''"),
    }
    for name, text in schema_invalid.items():
        assert reason(_write(tmp_path, text)) == "schema_invalid", name
    assert reason(_write(tmp_path, good.replace("harness.fixture_sum", "harness.nope"))) == "unknown_calc"
    assert reason(_write(tmp_path, "[]", WITHDRAWN.format(digest="any").replace(CALC_ID, "harness.x"))) == (
        "unknown_calc"
    )
    assert reason(_write(tmp_path, good + "    approver: other\n")) == "yaml_invalid"  # duplicate key
    assert reason(_write(tmp_path, "[]", WITHDRAWN.format(digest="all"))) == "schema_invalid"
    # whole-file rules: schema number, extra top-level key, tags, anchors, missing file, wrong root
    assert reason(_write(tmp_path, head="schema: 2\n")) == "schema_invalid"
    assert reason(_write(tmp_path, head="schema: 1\nextra: 1\n")) == "schema_invalid"
    assert reason(_write(tmp_path, head="")) == "schema_invalid"
    assert reason(_write(tmp_path, head="schema: !!int 1\n")) == "yaml_invalid"
    assert reason(_write(tmp_path, head="schema: &a 1\n")) == "yaml_invalid"
    root_list = tmp_path / "list.yaml"
    root_list.write_text("- 1\n", encoding="utf-8")
    assert reason(root_list) == "schema_invalid"
    assert reason(tmp_path / "missing.yaml") == "not_found"
    assert _approvals.APPROVALS_PATH.name == "approvals.yaml"
