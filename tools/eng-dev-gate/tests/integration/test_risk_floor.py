"""Integration tests of ``risk-floor`` (spec 4.6; AC19 to AC21)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from support.pullrequest import PLAN_PATH, PLAN_TASK, SPEC_PATH, make_gate_repo, plan_text, write_event
from support.repo import Repo, RunResult

ROOT_MAP = "- paths: ['pkg/src/**']\n  risk: r1\n- paths: ['**/docs/plans/*.md']\n  risk: r2\n"
PKG_MAP = "- paths: ['src/hot/**']\n  risk: [r2]\n"
MAPS = {
    ".gate/risk-map.yml": ROOT_MAP,
    "pkg/.gate/risk-map.yml": PKG_MAP,
    "pyproject.toml": "[tool.uv.workspace]\nmembers = ['pkg']\n",
    "pkg/pyproject.toml": "[project]\nname = 'pkg'\nversion = '0'\n",
}


def _plan(*risks: str) -> str:
    return plan_text().replace("\nrisk: r1\n", f"\nrisk: [{', '.join(risks)}]\n")


def _spec(risk: str) -> str:
    return (
        f"---\nid: spec-1\nissue: B-001\nstatus: approved\nsize: small\nrisk: {risk}\n---\n\n- AC1. Given x, then y.\n"
    )


def _run(repo: Repo, event: Path) -> tuple[RunResult, dict[str, str]]:
    """Run ``risk-floor`` on ``event``; return the result and ``{code: "path message" lines}`` of the errors."""
    result = repo.run(["--format", "json", "risk-floor", "--event", str(event)])
    errors: dict[str, str] = {}
    if result.out:
        for step in json.loads(result.out)["steps"]:
            for f in step["findings"]:
                if f["severity"] == "error":
                    errors[f["code"]] = errors.get(f["code"], "") + f"{f['path'] or ''} {f['message']}\n"
    return result, errors


def _pull(
    repo: Repo, plan: str, change: Mapping[str, str], body: str, *, maps: Mapping[str, str] | None = None
) -> Path:
    base = make_gate_repo(repo, base_files=maps or MAPS, plan=plan)
    repo.commit(change, "feat: change")
    return write_event(repo, base, body)


def test_union_of_maps_and_commits(repo: Repo, tmp_path: Path) -> None:
    """AC19: the floor is the union over both maps and both commits; the pull request cannot drop an entry."""
    # The head drops the r1 entry of the root map and adds an r3 entry; the base package map raises r2.
    change = {
        "pkg/src/a.py": "a = 1\n",
        "pkg/src/hot/b.py": "b = 1\n",
        "docs/x.md": "x\n",
        ".gate/risk-map.yml": "- paths: ['docs/**']\n  risk: r3\n",
    }
    event = _pull(repo, _plan("r1"), change, f"{PLAN_TASK}\nRisk: r1\n")
    result, errors = _run(repo, event)
    assert (result.code, set(errors)) == (1, {"RF001"})
    for expected in ("r1", "r2", "r3", "pkg/src/hot/b.py", "docs/x.md"):
        assert expected in errors["RF001"]
    other = Repo(tmp_path / "covered")
    event = _pull(other, _plan("r1", "r2", "r3"), change, f"{PLAN_TASK}\nRisk: r1, r2, r3\n")
    result, errors = _run(other, event)
    assert (result.code, errors) == (0, {})


def test_risk_sets_and_body_line(repo: Repo) -> None:
    """AC20: a plan set needs the same set in the body line; on a lane branch the body line is the recorded risk."""
    base = make_gate_repo(repo, base_files=MAPS, plan=_plan("r1", "r2"))
    repo.commit({"pkg/src/a.py": "a = 1\n"}, "feat: change")
    for body, code in [
        (f"{PLAN_TASK}\nRisk: r1, r2\n", 0),
        (f"{PLAN_TASK}\nRisk: r2 r1 (from the plan)\n", 0),
        (f"{PLAN_TASK}\n", 0),  # no body line: nothing to compare
        (f"{PLAN_TASK}\nRisk: r1\n", 1),
        (f"{PLAN_TASK}\nRisk: r1, r3\n", 1),
    ]:
        result, errors = _run(repo, write_event(repo, base, body))
        assert (result.code, set(errors)) == (code, set() if code == 0 else {"RF002"}), body
    lane = "lane/12-slug"
    for body, code, codes in [
        ("Risk: r1\n", 0, set()),
        ("Risk: r1, r3\n", 0, set()),
        ("Risk: r3\n", 1, {"RF001"}),
        ("", 1, {"RF004"}),
        ("Risk: x\n", 1, {"RF004"}),
    ]:
        result, errors = _run(repo, write_event(repo, base, body, head_ref=lane))
        assert (result.code, set(errors)) == (code, codes), body
    repo.commit({"pkg/src/hot/c.py": "c = 1\n"}, "feat: hot")
    result, errors = _run(repo, write_event(repo, base, "Risk: r1\n", head_ref=lane))
    assert (result.code, set(errors)) == (1, {"RF001"})


def test_recorded_risk_sources(repo: Repo, tmp_path: Path) -> None:
    """A missing plan or Plan-Task is RF004; a spec and plan pull request records the risk of its documents."""
    base = make_gate_repo(repo, base_files=MAPS)
    repo.commit({"pkg/src/a.py": "a = 1\n"}, "feat: change")
    for body in ("Work-Item: B-001\n", "Plan-Task: none (trivial)\n", "Plan-Task: pkg/docs/plans/9.md#T1\n"):
        result, errors = _run(repo, write_event(repo, base, body))
        assert (result.code, set(errors)) == (1, {"RF004"}), body
    for number, (plan_risk, spec_risk, expected) in enumerate([("r1", "r1", {"RF001"}), ("r2", "r1", set())]):
        other = Repo(tmp_path / f"docs{number}")
        base = make_gate_repo(other, base_files=MAPS)
        other.commit({PLAN_PATH: _plan(plan_risk), SPEC_PATH: _spec(spec_risk)}, "docs: plan and spec")
        _, errors = _run(other, write_event(other, base, ""))
        assert set(errors) == expected, (plan_risk, spec_risk)
    other = Repo(tmp_path / "broken")
    base = make_gate_repo(other, base_files=MAPS)
    other.commit({SPEC_PATH: "---\nrisk: r2\n---\n"}, "docs: broken spec")
    assert set(_run(other, write_event(other, base, ""))[1]) == {"RF004"}


def test_event_options_and_push(repo: Repo, tmp_path: Path) -> None:
    """The check runs from --base, --head and --body-file; a push event is skipped; no input is exit 2."""
    base = make_gate_repo(repo, base_files=MAPS, plan=_plan("r1"))
    head = repo.commit({"pkg/src/a.py": "a = 1\n"}, "feat: change")
    body = tmp_path / "body.md"
    body.write_text(f"{PLAN_TASK}\nRisk: r1\n", encoding="utf-8")
    args = ["risk-floor", "--base", base, "--head", head, "--body-file", str(body)]
    assert repo.run(args).code == 0
    body.write_text(f"{PLAN_TASK}\nRisk: r2\n", encoding="utf-8")
    assert repo.run(args).code == 1
    assert repo.run(["risk-floor", "--base", base]).code == 2
    assert repo.run(["risk-floor"]).code == 2
    push = tmp_path / "push.json"
    push.write_text('{"ref": "refs/heads/build/v1", "after": "abc"}', encoding="utf-8")
    skipped = repo.run(["risk-floor", "--event", str(push)])
    assert (skipped.code, "push event" in skipped.out) == (0, True)


@pytest.mark.parametrize(
    "text",
    [
        "- paths: [\n",  # malformed YAML
        "- paths: ['pkg/**']\n  risk: r4\n",  # unknown risk class
        "paths: ['pkg/**']\nrisk: r1\n",  # not a list
        "- risk: r1\n",  # entry without paths
        "- paths: []\n  risk: r1\n",
        "- paths: ['a']\n  risk: r1\n  note: x\n",  # unknown key
        "- paths: ['a']\n  risk: []\n",  # empty risk set
    ],
)
@pytest.mark.parametrize("where", [".gate/risk-map.yml", "pkg/.gate/risk-map.yml"])
def test_invalid_map(repo: Repo, text: str, where: str) -> None:
    """AC21: a malformed map or an unknown risk class is RF003 and exit 2, at either level."""
    event = _pull(repo, _plan("r1"), {"pkg/src/a.py": "a = 1\n"}, f"{PLAN_TASK}\n", maps={**MAPS, where: text})
    result = repo.run(["risk-floor", "--event", str(event)])
    assert (result.code, "RF003" in result.err) == (2, True)


def test_invalid_map_at_head_and_missing_root_map(repo: Repo, tmp_path: Path) -> None:
    """A map broken by the pull request itself is RF003; no root map at either commit is RF003 too (exit 2)."""
    base = make_gate_repo(repo, base_files=MAPS, plan=_plan("r1"))
    repo.commit({"pkg/.gate/risk-map.yml": "- paths: ['a']\n  risk: r9\n"}, "feat: break the map")
    result = repo.run(["risk-floor", "--event", str(write_event(repo, base, PLAN_TASK))])
    assert (result.code, "RF003" in result.err) == (2, True)
    other = Repo(tmp_path / "other")
    base = make_gate_repo(other)
    other.commit({"pkg/src/a.py": "a = 1\n"}, "feat: change")
    missing = other.run(["risk-floor", "--event", str(write_event(other, base, PLAN_TASK))])
    assert (missing.code, "RF003" in missing.err) == (2, True)
