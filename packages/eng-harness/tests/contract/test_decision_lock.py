"""The committed decision lock file matches the discovered registry (plan 0005 T2; spec 0005 AC4)."""

import json
from pathlib import Path

import eng_harness
from eng_harness.decisions._points import LOCK_PATH, check_lock, discover, load_lock


def test_lock_matches_registry() -> None:
    assert Path(eng_harness.__file__).parent / "decisions.lock.json" == LOCK_PATH
    assert check_lock(discover(), load_lock(LOCK_PATH)) == ()
    names = [entry["name"] for entry in json.loads(LOCK_PATH.read_text(encoding="utf-8"))]
    assert names == sorted(names)
