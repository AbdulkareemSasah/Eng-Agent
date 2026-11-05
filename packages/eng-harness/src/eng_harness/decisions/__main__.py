"""``uv run python -m eng_harness.decisions --write-lock`` writes both locks (spec 0005 sections 4.2 and 4.4)."""

import argparse
from collections.abc import Sequence

from eng_harness.decisions import _points, _rules


def main(argv: Sequence[str] | None = None) -> int:
    """Write ``decisions.lock.json`` and ``rules.lock.json``; return the exit code.

    Errors: ``DecisionDefinitionError`` (nothing written) when either has a changed hash under an unchanged version.
    """
    parser = argparse.ArgumentParser(prog="eng_harness.decisions")
    parser.add_argument("--write-lock", action="store_true", required=True)
    parser.parse_args(argv)
    points, rules = _points.discover(), _rules.discover()
    old_points = _points.load_lock(_points.LOCK_PATH) if _points.LOCK_PATH.exists() else []
    old_rules = _rules.load_rule_lock(_rules.RULES_LOCK_PATH) if _rules.RULES_LOCK_PATH.exists() else []
    findings = (*_points.check_lock(points, old_points), *_rules.check_rule_lock(rules, old_rules))
    if any(f.code == "VERSION_BUMP_REQUIRED" for f in findings):
        raise _points.DecisionDefinitionError("VERSION_BUMP_REQUIRED: a point or rule changed without a version bump")
    _points.write_lock(points, _points.LOCK_PATH)
    _rules.write_rule_lock(rules, _rules.RULES_LOCK_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
