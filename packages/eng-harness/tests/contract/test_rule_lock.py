"""The committed rule lock file matches the discovered registry (plan 0005 T4; spec 0005 AC10)."""

import json
from pathlib import Path

import eng_harness
from eng_harness.decisions._rules import RULES_LOCK_PATH, check_rule_lock, discover, load_rule_lock


def test_lock_matches_registry() -> None:
    assert Path(eng_harness.__file__).parent / "rules.lock.json" == RULES_LOCK_PATH
    assert check_rule_lock(discover(), load_rule_lock(RULES_LOCK_PATH)) == ()
    ids = [entry["id"] for entry in json.loads(RULES_LOCK_PATH.read_text(encoding="utf-8"))]
    assert ids == sorted(ids)
