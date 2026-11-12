"""The calc lock file against the registry (plan 0003 T2; spec 0003 AC2, 4.5)."""

import importlib.util
import os
import sys
import warnings
from pathlib import Path
from types import ModuleType

import pytest
from eng_contract.kinds import NEUTRAL_KINDS

from eng_harness._calc import _hash
from eng_harness._calc._approvals import APPROVALS_PATH, check_approvals, load_approvals
from eng_harness.calc import CalcRegistry, CalcRegistryError
from eng_harness.calcs import REGISTRY

_FIXTURES = Path(__file__).resolve().parents[1] / "data" / "calcs" / "fixture_calcs.py"
EMPTY: dict[str, object] = {"schema": 1, "calcs": []}


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


def test_lock_matches_registry() -> None:
    if "MUTANT_UNDER_TEST" in os.environ:
        pytest.skip(
            "mutants change the hashed source, so the lock cannot match the registry (B-437); expires 2026-12-31"
        )
    lock = _hash.read_lock()
    assert lock["schema"] == 1
    assert _hash.lock_problems(REGISTRY, lock) == []
    assert _hash.LOCK_PATH.read_bytes() == _hash.render_lock(_hash.build_lock(REGISTRY, lock))  # the writer's output


def test_lock_detects_drift_and_keeps_removed_ids(fixtures: ModuleType, tmp_path: Path) -> None:
    kinds = NEUTRAL_KINDS.extend({fixtures.OUTPUT_KIND: fixtures.FixtureOut})
    registry = CalcRegistry(kinds, [fixtures.fixture_sum])
    digest = registry.content_hash("harness.fixture_sum")
    entry = {"id": "harness.fixture_sum", "version": 3, "content_sha256": digest}
    good = {"schema": 1, "calcs": [entry]}
    assert _hash.build_lock(registry, EMPTY) == good
    assert _hash.lock_problems(registry, good) == []
    drift: dict[str, dict[str, object]] = {
        "missing entry": EMPTY,
        "hash": {"schema": 1, "calcs": [entry | {"content_sha256": "0" * 64}]},
        "version": {"schema": 1, "calcs": [entry | {"version": 4}]},
        "registered but removed": {"schema": 1, "calcs": [{"id": "harness.fixture_sum", "removed": True}]},
        "unregistered, not removed": {"schema": 1, "calcs": [entry, entry | {"id": "harness.gone"}]},
    }
    for name, lock in drift.items():
        assert _hash.lock_problems(registry, lock), name
    # a calc that vanished stays in the lock as removed, and its id is then refused (AC2)
    removed = _hash.build_lock(CalcRegistry(kinds), good)
    assert removed == {"schema": 1, "calcs": [{"id": "harness.fixture_sum", "removed": True}]}
    assert _hash.removed_ids(removed) == {"harness.fixture_sum"}
    assert _hash.build_lock(CalcRegistry(kinds), removed) == removed
    # the module entry point writes the same bytes
    target = tmp_path / "calcs.lock.json"
    target.write_bytes(_hash.render_lock(EMPTY))
    assert _hash.main(["--write-lock"], registry=registry, lock_path=target) == 0
    assert target.read_bytes() == _hash.render_lock(good)
    assert _hash.read_lock(target) == good
    with pytest.raises(SystemExit):
        _hash.main([], registry=registry, lock_path=target)


def test_render_lock_is_sorted_indented_utf8_lf() -> None:
    lock = {"schema": 1, "calcs": [{"version": 2, "id": "b", "content_sha256": "c"}]}
    assert _hash.render_lock(lock) == (
        b'{\n  "calcs": [\n    {\n      "content_sha256": "c",\n      "id": "b",\n      "version": 2\n    }\n  ],\n'
        b'  "schema": 1\n}\n'
    )


def test_lock_problem_messages(fixtures: ModuleType) -> None:
    kinds = NEUTRAL_KINDS.extend({fixtures.OUTPUT_KIND: fixtures.FixtureOut})
    registry = CalcRegistry(kinds, [fixtures.fixture_sum])
    digest = registry.content_hash("harness.fixture_sum")
    entry = {"id": "harness.fixture_sum", "version": 3, "content_sha256": digest}
    gone = {"id": "harness.gone", "version": 1, "content_sha256": digest}
    missing = ["harness.fixture_sum: registered but missing from the lock or marked removed"]
    differs = ["harness.fixture_sum: the lock entry differs from the registry (run the lock writer)"]
    assert _hash.lock_problems(registry, {"schema": 2, "calcs": [entry]}) == ["unsupported lock schema"]
    assert _hash.lock_problems(registry, {"calcs": [entry]}) == ["unsupported lock schema"]
    assert _hash.lock_problems(registry, {"schema": 1, "calcs": [entry, entry]}) == [
        "harness.fixture_sum: duplicate lock entry"
    ]
    assert _hash.lock_problems(registry, EMPTY) == missing
    assert _hash.lock_problems(registry, {"schema": 1}) == missing
    assert _hash.lock_problems(registry, {"schema": 1, "calcs": [{"id": "harness.fixture_sum", "removed": True}]}) == (
        missing
    )
    assert _hash.lock_problems(registry, {"schema": 1, "calcs": [entry | {"version": 4}]}) == differs
    assert _hash.lock_problems(registry, {"schema": 1, "calcs": [entry | {"content_sha256": "0" * 64}]}) == differs
    assert _hash.lock_problems(registry, {"schema": 1, "calcs": [entry, gone]}) == [
        "harness.gone: in the lock but not registered and not marked removed"
    ]
    assert _hash.lock_problems(registry, {"schema": 1, "calcs": [entry, {"id": "harness.gone", "removed": True}]}) == []
    assert _hash.lock_problems(CalcRegistry(kinds), {"schema": 1}) == []
    assert _hash.removed_ids({"schema": 1}) == frozenset()
    assert _hash.removed_ids({"schema": 1, "calcs": [entry, {"id": "x", "removed": False}]}) == frozenset()


def test_build_lock_sorts_by_id_and_keeps_every_removed_id(fixtures: ModuleType) -> None:
    kinds = NEUTRAL_KINDS.extend({fixtures.OUTPUT_KIND: fixtures.FixtureOut})
    registry = CalcRegistry(kinds, [fixtures.fixture_sum])
    digest = registry.content_hash("harness.fixture_sum")
    previous = {
        "schema": 1,
        "calcs": [
            {"id": "z.old", "removed": True},
            {"id": "a.old", "version": 1, "content_sha256": "1" * 64},
            {"id": "harness.fixture_sum", "version": 1, "content_sha256": "2" * 64},
        ],
    }
    assert _hash.build_lock(registry, previous) == {
        "schema": 1,
        "calcs": [
            {"id": "a.old", "removed": True},
            {"id": "harness.fixture_sum", "version": 3, "content_sha256": digest},
            {"id": "z.old", "removed": True},
        ],
    }
    assert _hash.build_lock(registry, {"schema": 1}) == _hash.build_lock(registry, EMPTY)


def test_registry_refuses_a_removed_id(fixtures: ModuleType) -> None:
    kinds = NEUTRAL_KINDS.extend({fixtures.OUTPUT_KIND: fixtures.FixtureOut})
    with pytest.raises(CalcRegistryError) as caught:
        CalcRegistry(kinds, [fixtures.fixture_sum], removed={"harness.fixture_sum"})
    assert caught.value.rule == "removed"
    assert CalcRegistry(kinds, [fixtures.fixture_sum], removed={"other"}).content_hash("harness.fixture_sum")


def test_main_requires_exactly_the_write_flag(fixtures: ModuleType, tmp_path: Path) -> None:
    kinds = NEUTRAL_KINDS.extend({fixtures.OUTPUT_KIND: fixtures.FixtureOut})
    target = tmp_path / "calcs.lock.json"
    target.write_bytes(_hash.render_lock(EMPTY))
    for argv in (["--write-lock", "x"], ["--other"], ["x", "--write-lock"]):
        with pytest.raises(SystemExit):
            _hash.main(argv, registry=CalcRegistry(kinds), lock_path=target)
    assert target.read_bytes() == _hash.render_lock(EMPTY)


def test_shipped_calcs_are_draft() -> None:
    """AC10: the shipped approvals.yaml parses, and every registered calc declares draft (ADR-0028 section 4)."""
    shipped = load_approvals(APPROVALS_PATH, REGISTRY)
    assert shipped.schema_version == 1
    assert [calc_id for calc_id in REGISTRY if REGISTRY[calc_id].verification != "draft"] == []
    findings = check_approvals(REGISTRY, shipped)
    assert not any(finding.kind == "unknown_calc" for finding in findings)
    for finding in findings:  # spec 0003 4.5: stale entries are reported, not failed
        warnings.warn(f"stale approval for {finding.calc_id}", stacklevel=1)
