"""The calc lock file against the registry (plan 0003 T2; spec 0003 AC2, 4.5)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from eng_contract.kinds import NEUTRAL_KINDS
from pydantic import ValidationError

from eng_harness._calc._hash import LOCK_PATH, CalcLock, LockEntry, dump_lock, lock_for, read_lock, write_lock
from eng_harness.calc import CalcRegistry, CalcRegistryError
from eng_harness.calcs import REGISTRY

HASH = "ab" * 32
_PATH = Path(__file__).resolve().parents[1] / "data" / "calcs" / "fixture_calcs.py"


@pytest.fixture(scope="module")
def fixtures() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fixture_calcs", _PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["fixture_calcs"] = module
    spec.loader.exec_module(module)
    return module


def _registry(fixtures: ModuleType, *, empty: bool = False) -> CalcRegistry:
    kinds = NEUTRAL_KINDS.extend({fixtures.OUTPUT_KIND: fixtures.FixtureOut})
    return CalcRegistry(kinds, [] if empty else [fixtures.fixture_sum], hasher=lambda _: HASH)


def test_lock_matches_registry() -> None:
    lock = read_lock()
    entries = {entry.id: entry for entry in lock.calcs}
    assert len(entries) == len(lock.calcs)
    for calc_id in REGISTRY:
        entry = entries[calc_id]
        assert not entry.removed, calc_id
        assert entry.version == REGISTRY[calc_id].version, calc_id
        assert entry.content_sha256 == REGISTRY.content_hash(calc_id), calc_id
    for entry in lock.calcs:
        assert (entry.id in REGISTRY) is not entry.removed, entry.id


def test_committed_lock_is_in_canonical_form() -> None:
    assert LOCK_PATH.read_text(encoding="utf-8") == dump_lock(read_lock())


def test_lock_follows_the_registry(fixtures: ModuleType, tmp_path: Path) -> None:
    empty = CalcLock(calcs=[])
    added = lock_for(_registry(fixtures), empty)
    assert added.calcs == [LockEntry(id="harness.fixture_sum", version=3, content_sha256=HASH)]

    removed = lock_for(_registry(fixtures, empty=True), added)
    assert removed.calcs == [LockEntry(id="harness.fixture_sum", version=3, content_sha256=HASH, removed=True)]

    with pytest.raises(CalcRegistryError) as again:
        lock_for(_registry(fixtures), removed)
    assert again.value.rule == "removed"

    path = tmp_path / "calcs.lock.json"
    write_lock(_registry(fixtures), path, previous=empty)
    assert read_lock(path) == added
    assert path.read_text(encoding="utf-8") == dump_lock(added)


def test_lock_file_validation() -> None:
    entry = LockEntry(id="harness.b", version=1, content_sha256=HASH)
    other = LockEntry(id="harness.a", version=1, content_sha256=HASH)
    with pytest.raises(ValidationError):
        CalcLock(calcs=[entry, other])
    with pytest.raises(ValidationError):
        CalcLock(calcs=[entry, entry])
    with pytest.raises(ValidationError):
        LockEntry(id="harness.a", version=1, content_sha256="xyz")
    assert CalcLock(calcs=[other, entry]).removed_ids == frozenset()
    assert CalcLock(calcs=[other.model_copy(update={"removed": True})]).removed_ids == {"harness.a"}
