"""The calc lock file against the registry (plan 0003 T2; spec 0003 AC2, 4.5)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from eng_contract.kinds import NEUTRAL_KINDS

from eng_harness._calc import _hash
from eng_harness.calc import CalcRegistry
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
