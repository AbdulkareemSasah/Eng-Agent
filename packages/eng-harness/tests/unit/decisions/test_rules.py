"""Rule definitions, restricted basis view, registry, lock and review table (plan 0005 T4; spec 0005 AC9 to AC13)."""

import hashlib
import importlib
import inspect
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from eng_contract.kinds.basis import BasisField, DesignBasis
from eng_contract.quantity import Quantity
from pydantic import BaseModel, ConfigDict

from eng_harness.block import LockFinding
from eng_harness.ctx import BasisView
from eng_harness.decisions import _rules
from eng_harness.decisions._points import PointRegistry, decision_point
from eng_harness.decisions._rules import (
    Rule,
    RuleRegistry,
    check_rule_lock,
    discover,
    load_rule_lock,
    write_rule_lock,
)
from eng_harness.decisions.types import DecisionDefinitionError, Pick, RuleBasis, rule
from eng_harness.errors import BlockRuleViolation

fixture_rules = importlib.import_module("rules.fixtures.fixture_rules")  # tests/rules/fixtures, a namespace package
POINT: str = fixture_rules.POINT
Action: Any = fixture_rules.Action
FixtureState: Any = fixture_rules.FixtureState
bearing_only: Rule = fixture_rules.bearing_only
reads_undeclared: Rule = fixture_rules.reads_undeclared

RESULT = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"
GOOD: dict[str, Any] = {
    "id": "fixture_point.some_rule",
    "version": 1,
    "point": POINT,
    "rationale": "A rationale without digits.",
    "thresholds": ("limits.bearing_ratio",),
}


def _view(declared: tuple[str, ...] = ("limits.bearing_ratio", "limits.other_ratio")) -> BasisView:
    field = BasisField(
        value=0.5, unit="1", source="engineer:eng@2026-01-01T00:00:00.000Z", confirmed=True, citation=None
    )
    basis = DesignBasis(template=None, fields={"limits.bearing_ratio": field, "limits.other_ratio": field})
    return BasisView(RESULT, basis, declared)


def _fn(state: BaseModel, basis: RuleBasis) -> Pick[Any] | None:
    return None


async def _async_fn(state: BaseModel, basis: RuleBasis) -> None:
    return None


def _generator_fn(state: BaseModel, basis: RuleBasis) -> Any:
    yield 1


def _plain_state_fn(state: int, basis: RuleBasis) -> None:
    return None


def _any_state_fn(state: Any, basis: RuleBasis) -> None:
    return None


def _one_param_fn(state: BaseModel) -> None:
    return None


def _no_source_fn(state: BaseModel, basis: RuleBasis) -> None:
    return None


_no_source_fn.__module__ = "module_without_source_for_b168"


def _make(fn: Callable[..., object] = _fn, **overrides: object) -> Rule:
    return rule(**{**GOOD, **overrides})(fn)


@pytest.mark.parametrize(
    ("fn", "overrides"),
    [
        (_fn, {"id": "Fixture_point.rule"}),
        (_fn, {"id": "fixture_point.1rule"}),
        (_fn, {"id": "fixture_point"}),
        (_fn, {"id": "other_point.some_rule"}),
        (_fn, {"version": 0}),
        (_fn, {"version": True}),
        (_fn, {"rationale": ""}),
        (_fn, {"rationale": "Limit of 5 mm."}),
        (_fn, {"rationale": f"Arabic digit {chr(0x665)}."}),
        (_fn, {"thresholds": ("bearing",)}),
        (_fn, {"thresholds": ("Limits.Bearing",)}),
        (_async_fn, {}),
        (_generator_fn, {}),
        (_plain_state_fn, {}),
        (_any_state_fn, {}),
        (_one_param_fn, {}),
        (_no_source_fn, {}),
    ],
)
def test_registration_rules(fn: Callable[..., object], overrides: dict[str, object]) -> None:
    with pytest.raises(DecisionDefinitionError):
        _make(fn, **overrides)


def test_registration_accepts_a_good_rule_and_registry_rules() -> None:
    made = _make()
    assert (made.id, made.version, made.point, made.thresholds, made.state) == (
        "fixture_point.some_rule",
        1,
        POINT,
        ("limits.bearing_ratio",),
        BaseModel,
    )
    assert _make(thresholds=()).thresholds == ()
    point = decision_point(name=POINT, version=1, title="Fixture point", options=Action, state=FixtureState)(object)
    registry = RuleRegistry([reads_undeclared, bearing_only], PointRegistry([point]))
    assert [r.id for r in registry.rules] == ["fixture_point.bearing_only", "fixture_point.reads_undeclared"]
    assert registry.get("fixture_point.bearing_only") is bearing_only
    assert registry.get("fixture_point.nothing") is None
    assert len(RuleRegistry([bearing_only]).with_(made).rules) == 2
    assert registry.with_().points is registry.points
    with pytest.raises(DecisionDefinitionError, match="duplicate"):
        RuleRegistry([bearing_only, bearing_only])
    with pytest.raises(DecisionDefinitionError, match="no decision point"):
        RuleRegistry([bearing_only], PointRegistry([]))
    other_state = type("OtherState", (BaseModel,), {"model_config": ConfigDict(frozen=True, extra="forbid")})
    other = decision_point(name=POINT, version=1, title="Other", options=Action, state=other_state)(object)
    with pytest.raises(DecisionDefinitionError, match="state model"):
        RuleRegistry([bearing_only], PointRegistry([other]))


def test_code_hash_is_stable() -> None:
    source = Path(inspect.getfile(fixture_rules)).read_bytes().decode("utf-8").replace("\r\n", "\n")
    expected = hashlib.sha256(source.encode("utf-8")).hexdigest()
    assert bearing_only.code_sha256 == expected
    assert reads_undeclared.code_sha256 == expected  # one module, one hash
    assert bearing_only.module == fixture_rules.__name__


def test_lock_check_and_write(tmp_path: Path) -> None:
    registry = RuleRegistry([bearing_only, reads_undeclared])
    path = tmp_path / "rules.lock.json"
    write_rule_lock(registry, path)
    entries = json.loads(path.read_text(encoding="utf-8"))
    assert entries == [
        {"id": "fixture_point.bearing_only", "version": 1, "code_sha256": bearing_only.code_sha256},
        {"id": "fixture_point.reads_undeclared", "version": 2, "code_sha256": reads_undeclared.code_sha256},
    ]
    assert check_rule_lock(registry, load_rule_lock(path)) == ()
    changed = [{**entries[0], "code_sha256": "0" * 64}, entries[1]]
    assert check_rule_lock(registry, changed) == (LockFinding("fixture_point.bearing_only", "VERSION_BUMP_REQUIRED"),)
    stale = [{**entries[0], "version": 7}, {"id": "fixture_point.gone", "version": 1, "code_sha256": "0" * 64}]
    assert check_rule_lock(registry, stale) == (
        LockFinding("fixture_point.bearing_only", "LOCK_STALE"),
        LockFinding("fixture_point.gone", "LOCK_STALE"),
        LockFinding("fixture_point.reads_undeclared", "LOCK_STALE"),
    )
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(DecisionDefinitionError, match="VERSION_BUMP_REQUIRED"):
        write_rule_lock(registry, path)
    assert json.loads(path.read_text(encoding="utf-8")) == changed  # refused: nothing written
    path.write_text('{"id": 1}', encoding="utf-8")
    with pytest.raises(DecisionDefinitionError, match="lock"):
        load_rule_lock(path)


def test_discover_is_empty_without_rules_package() -> None:
    assert discover().rules == ()
    assert _rules.RULES_LOCK_PATH.name == "rules.lock.json"


def test_rule_basis_is_restricted() -> None:
    basis = RuleBasis(_view(), bearing_only.thresholds)
    limit = basis.quantity("limits.bearing_ratio")
    assert limit == Quantity(0.5, "1")
    assert Quantity(0.6, "1") > limit
    state = FixtureState(bearing_ratio=Quantity(0.6, "1"), bearing_fails=True)
    assert bearing_only.fn(state, basis) == Pick(Action.ENLARGE)
    assert bearing_only.fn(state.model_copy(update={"bearing_fails": False}), basis) is None
    with pytest.raises(BlockRuleViolation, match=r"limits\.other_ratio"):
        reads_undeclared.fn(state, RuleBasis(_view(), reads_undeclared.thresholds))
    for read in (basis.quantity, basis.count):
        with pytest.raises(BlockRuleViolation, match="thresholds"):
            read("limits.other_ratio")
    with pytest.raises(BlockRuleViolation, match="thresholds"):
        basis.choice("limits.other_ratio", Action)
    with pytest.raises(BlockRuleViolation, match="required_basis"):  # the view's own restriction still applies
        RuleBasis(_view(("limits.other_ratio",)), ("limits.bearing_ratio",)).quantity("limits.bearing_ratio")


def test_review_table() -> None:
    registry = RuleRegistry([reads_undeclared, bearing_only])
    rows = registry.review_table({})
    assert [r.id for r in rows] == ["fixture_point.bearing_only", "fixture_point.reads_undeclared"]
    first = rows[0]
    assert (first.point, first.version, first.rationale, first.thresholds, first.code_sha256, first.approval) == (
        POINT,
        1,
        bearing_only.rationale,
        ("limits.bearing_ratio",),
        bearing_only.code_sha256,
        "draft",
    )
    approved = registry.review_table({"fixture_point.bearing_only": bearing_only.code_sha256})
    assert [r.approval for r in approved] == ["approved", "draft"]
    stale = registry.review_table({"fixture_point.bearing_only": "0" * 64})  # bound to the hash: a stale one is draft
    assert [r.approval for r in stale] == ["draft", "draft"]


def test_write_lock_command_writes_both_and_refuses_a_bump(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from eng_harness.decisions import __main__ as command
    from eng_harness.decisions import _points

    points_lock, rules_lock = tmp_path / "decisions.lock.json", tmp_path / "rules.lock.json"
    monkeypatch.setattr(_points, "LOCK_PATH", points_lock)
    monkeypatch.setattr(_rules, "RULES_LOCK_PATH", rules_lock)
    assert command.main(["--write-lock"]) == 0
    assert json.loads(points_lock.read_text(encoding="utf-8")) == []
    assert json.loads(rules_lock.read_text(encoding="utf-8")) == []
    monkeypatch.setattr(_rules, "discover", lambda: RuleRegistry([bearing_only]))
    stale = [{"id": bearing_only.id, "version": 1, "code_sha256": "0" * 64}]
    rules_lock.write_text(json.dumps(stale), encoding="utf-8")
    points_lock.write_text("[]\n", encoding="utf-8")
    with pytest.raises(DecisionDefinitionError, match="VERSION_BUMP_REQUIRED"):
        command.main(["--write-lock"])
    assert json.loads(rules_lock.read_text(encoding="utf-8")) == stale  # refused: neither lock written
