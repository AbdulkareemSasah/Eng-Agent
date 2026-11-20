"""The committed rule lock file matches the discovered registry (plan 0005 T4; spec 0005 AC10)."""

import json
import os
from pathlib import Path

import pytest

import eng_harness
from eng_harness.decisions._rules import RULES_LOCK_PATH, check_rule_lock, discover, load_rule_lock


def test_lock_matches_registry() -> None:
    if "MUTANT_UNDER_TEST" in os.environ:
        pytest.skip(
            "mutants change the hashed source, so the lock cannot match the registry (B-542); expires 2026-12-31"
        )
    assert Path(eng_harness.__file__).parent / "rules.lock.json" == RULES_LOCK_PATH
    assert check_rule_lock(discover(), load_rule_lock(RULES_LOCK_PATH)) == ()
    ids = [entry["id"] for entry in json.loads(RULES_LOCK_PATH.read_text(encoding="utf-8"))]
    assert ids == sorted(ids)
