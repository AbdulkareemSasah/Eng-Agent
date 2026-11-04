"""Integration tests of ``gate-check`` part 2 (spec 4.5 steps 1, 2, 3, 8, 9; AC12, AC14 to AC18)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from support.pullrequest import (
    BODY,
    PLAN_PATH,
    PLAN_TASK,
    SPEC_PATH,
    base_checkout,
    gate_check,
    make_gate_repo,
    plan_text,
    spec_text,
    write_event,
)
from support.repo import Repo, RunResult

DOCS = "Work-Item: B-001\nPlan-Task: none (spec and plan)\n"
CODEOWNERS = ".github/CODEOWNERS"
OWNERS = "# protected\n/pkg/src/protected/ @owner  # inline\n\n**/AGENTS.md @owner\n/.github/ @owner\n"
MORE = "\nMore.\n"
SECOND_CRITERION = "- AC2. Given a, then b.\n"
NEW_PLAN = "pkg/docs/plans/0002-y.md"


def _lines(n: int) -> str:
    return "".join(f"v{i} = {i}\n" for i in range(n))


def _findings(result: RunResult) -> list[tuple[str, str, str | None]]:
    """``(code, severity, path)`` of every finding of the single step."""
    step = json.loads(result.out)["steps"][0]
    return [(f["code"], f["severity"], f["path"]) for f in step["findings"]]


def _errors(result: RunResult) -> set[str]:
    return {code for code, severity, _ in _findings(result) if severity == "error"}


def _commit_and_check(repo: Repo, base: str, files: dict[str, str], body: str, **event: str) -> RunResult:
    """Commit ``files`` on top of the branch and run ``gate-check`` on the event for the new head."""
    repo.commit(files, "docs: change")
    return gate_check(repo, write_event(repo, base, body, **event))[0]


@pytest.mark.parametrize(
    ("files", "body", "code", "needle"),
    [
        ({PLAN_PATH: plan_text() + MORE}, DOCS, None, ""),
        ({PLAN_PATH: plan_text() + MORE, SPEC_PATH: spec_text() + "\nA note.\n"}, DOCS, None, ""),
        ({PLAN_PATH: plan_text() + MORE, "pkg/src/new.py": "y = 2\n"}, DOCS, "GC010", "pkg/src/new.py"),
        ({PLAN_PATH: plan_text() + MORE}, BODY, "GC011", "spec and plan"),
        ({PLAN_PATH: plan_text() + MORE}, "Work-Item: B-001\n", "GC001", ""),
        ({PLAN_PATH: plan_text(status="maybe")}, DOCS, "GC005", "status"),
        ({PLAN_PATH: plan_text(max_changed_lines=401)}, DOCS, "GC005", "401"),
        ({SPEC_PATH: "no front matter\n"}, DOCS, "GC005", "front matter"),
        ({PLAN_PATH: plan_text(spec="pkg/docs/specs/9999-none.md")}, DOCS, "GC004", "9999-none"),
        ({PLAN_PATH: plan_text() + MORE, SPEC_PATH: spec_text() + SECOND_CRITERION}, DOCS, "GC016", "AC2"),
    ],
)
def test_spec_plan_pull_request_only(
    repo: Repo, files: dict[str, str], body: str, code: str | None, needle: str
) -> None:
    """AC12 and AC13: a spec or plan pull request holds only specs and plans, valid, with every criterion covered."""
    base = make_gate_repo(repo)
    result = _commit_and_check(repo, base, files, body)
    assert (result.code, _errors(result)) == ((1, {code}) if code else (0, set()))
    assert needle in result.out


def test_deleted_documents_are_not_parsed(repo: Repo) -> None:
    """AC12: a deleted spec or plan is a document change without front matter to parse."""
    base = make_gate_repo(repo, base_files={NEW_PLAN: plan_text()})
    repo.git("rm", "-q", NEW_PLAN)
    repo.git("commit", "-q", "-m", "docs: delete")
    result, errors = gate_check(repo, write_event(repo, base, DOCS))
    assert (result.code, errors) == (0, {})


def test_lane_branch(repo: Repo) -> None:
    """AC14: a draft `lane/<issue>-<slug>` passes with a notice and skips the rest; otherwise GC012."""
    base = make_gate_repo(repo)
    repo.commit({"pkg/elsewhere.py": "z = 1\n"}, "feat: lane tool")  # outside every task, no Plan-Task line
    draft = gate_check(repo, write_event(repo, base, "no plan task\n", head_ref="lane/12-wall-check", draft=True))[0]
    assert draft.code == 0
    assert json.loads(draft.out)["status"] == "pass"
    assert _findings(draft) == [("GC012", "notice", None)]
    bad = [("lane/12-wall-check", False), ("lane/x-foo", True), ("lane/12", True), ("lane/12-Foo", True)]
    bad += [("lane/12-", True), ("lane/-foo", True), ("lane/1_2-foo", True)]
    for name, is_draft in bad:
        event = write_event(repo, base, BODY, head_ref=name, draft=is_draft, name="bad.json")
        result, errors = gate_check(repo, event)
        assert (result.code, set(errors)) == (1, {"GC012"}), name
    other = write_event(repo, base, "Work-Item: B-001\n", head_ref="lanes/12-foo", draft=True, name="other.json")
    assert set(gate_check(repo, other)[1]) == {"GC001"}  # not a lane branch: the ordinary checks run


@pytest.mark.parametrize(
    ("reason", "files", "fits"),
    [
        ("trivial", {"docs/a.md": _lines(10)}, True),
        ("trivial", {"docs/a.md": _lines(11)}, False),
        ("trivial", {"docs/a.md": _lines(1), "uv.lock": _lines(50)}, True),  # generated files are not counted
        ("trivial", {"pkg/src/x.py": "x = 1\n"}, False),
        ("trivial", {"pkg/tests/test_x.py": "x = 1\n"}, False),
        ("trivial", {".github/note.md": "x\n"}, False),
        ("trivial", {".gate/note.md": "x\n"}, False),
        ("trivial", {"pkg/pyproject.toml": "x = 1\n"}, False),
        ("trivial", {"docs/config.yml": "a: 1\n"}, False),
        ("trivial", {"docs/schema.txt": "a\n"}, False),
        ("trivial", {"docs/data.json": "{}\n"}, False),
        ("hub documents", {"design/a.md": "a\n", "design/sub/b.md": "b\n"}, True),
        ("hub documents", {"design/a.md": "a\n", "pkg/b.md": "b\n"}, False),
        ("spike", {"spikes/s/check.py": "a = 1\n"}, True),
        ("spike", {"spikes/s/check.py": "a = 1\n", "pkg/b.md": "b\n"}, False),
        ("release", {"pkg/pyproject.toml": "a\n", "pkg/CHANGELOG.md": "b\n", "uv.lock": "c\n"}, True),
        ("release", {"pkg/pyproject.toml": "a\n", "other/CHANGELOG.md": "b\n"}, False),
        ("release", {"pkg/pyproject.toml": "a\n", "pkg/x.py": "b\n"}, False),
        ("spec and plan", {"pkg/src/x.py": "x = 1\n"}, False),
        ("whatever", {"docs/a.md": "a\n"}, False),
    ],
)
def test_none_reasons(repo: Repo, reason: str, files: dict[str, str], fits: bool) -> None:
    """AC15: `none (<reason>)` needs a reason of the table and a diff that fits it, else GC011."""
    base = make_gate_repo(repo)
    result = _commit_and_check(repo, base, files, f"Work-Item: B-001\nPlan-Task: none ({reason})\n")
    assert (result.code, _errors(result)) == ((0, set()) if fits else (1, {"GC011"})), (reason, files)


def _draft_gate_repo(repo: Repo, status: str) -> str:
    return make_gate_repo(repo, plan=plan_text(status=status), base_files={SPEC_PATH: spec_text(status)})


def test_status_approved(repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC16: setting `approved` fails in bootstrap mode (GC014) and needs verified approvals otherwise (GC015)."""
    base = _draft_gate_repo(repo, "draft")
    both = {PLAN_PATH: plan_text(status="approved"), SPEC_PATH: spec_text("approved")}
    result = _commit_and_check(repo, base, both, DOCS)
    assert sorted(f for f in _findings(result) if f[0] == "GC014") == [
        ("GC014", "error", PLAN_PATH),
        ("GC014", "error", SPEC_PATH),
    ]
    assert (result.code, _errors(result)) == (1, {"GC014"})
    added = _commit_and_check(repo, base, {NEW_PLAN: plan_text(status="approved")}, DOCS, name="added.json")
    assert ("GC014", "error", NEW_PLAN) in _findings(added)  # a new document with the status is also setting it
    drafts = Repo(tmp_path / "drafts")  # a draft stays a draft: no finding
    base = _draft_gate_repo(drafts, "draft")
    assert _commit_and_check(drafts, base, {PLAN_PATH: plan_text(status="draft") + MORE}, DOCS).code == 0
    approved = Repo(tmp_path / "approved")  # an approved document that is edited does not set the status again
    base = _draft_gate_repo(approved, "approved")
    assert _commit_and_check(approved, base, {PLAN_PATH: plan_text() + MORE}, DOCS).code == 0


def test_status_approved_with_bootstrap_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC16: with bootstrap off the approvals port (plan task T24) is not implemented, so verification fails closed."""
    normal = Repo(tmp_path / "normal")
    draft = {SPEC_PATH: spec_text("draft")}
    base = make_gate_repo(normal, bootstrap=False, plan=plan_text(status="draft"), base_files=draft)
    normal.commit({PLAN_PATH: plan_text(status="approved")}, "docs: approve")
    gate = base_checkout(normal, base, tmp_path / "gate-base", monkeypatch)
    event = write_event(normal, base, "Closes #1\nPlan-Task: none (spec and plan)\n", base_ref="main")
    result, errors = gate_check(normal, event, gate=gate)
    assert (result.code, set(errors)) == (1, {"GC015"})
    assert PLAN_PATH in errors["GC015"]
    assert "not implemented" in errors["GC015"]


def test_protected_paths_awaiting_owner(repo: Repo) -> None:
    """AC17: a changed path covered by CODEOWNERS is AW02 in bootstrap mode; patterns of the base still apply."""
    plan = plan_text(files=("pkg/src/**", ".github/**"))
    base = make_gate_repo(repo, plan=plan, base_files={CODEOWNERS: OWNERS, "pkg/src/protected/a.py": "a = 1\n"})
    ok = _commit_and_check(repo, base, {"pkg/src/free.py": "f = 1\n"}, BODY)
    assert (ok.code, _findings(ok)) == (0, [])
    result = _commit_and_check(repo, base, {"pkg/src/protected/a.py": "a = 2\n"}, BODY, name="p.json")
    assert result.code == 0
    data = json.loads(result.out)
    assert data["status"] == "awaiting-owner"
    awaiting = [f for f in data["steps"][0]["findings"] if f["severity"] == "awaiting"]
    assert [f["code"] for f in awaiting] == ["AW02"]
    assert "pkg/src/protected/a.py" in awaiting[0]["message"]
    assert "pkg/src/free.py" not in awaiting[0]["message"]
    repo.commit({CODEOWNERS: "/nothing/ @owner\n"}, "ci: drop protection")  # removed by the pull request itself
    repo.rename("pkg/src/protected/a.py", "pkg/src/moved.py")  # a rename counts both paths
    moved = gate_check(repo, write_event(repo, base, BODY, name="m.json"))[0]
    assert moved.code == 0
    assert "pkg/src/protected/a.py" in json.loads(moved.out)["steps"][0]["findings"][0]["message"]


def test_protected_paths_with_bootstrap_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC17: with bootstrap off the owner's approving review is required; verification is plan task T24 (GC015)."""
    plan = plan_text(files=("pkg/src/**", ".github/**"))
    normal = Repo(tmp_path / "normal")
    files = {CODEOWNERS: OWNERS, "pkg/src/protected/a.py": "a\n"}
    base = make_gate_repo(normal, bootstrap=False, plan=plan, base_files=files)
    normal.commit({"pkg/src/protected/a.py": "b\n"}, "feat: change")
    gate = base_checkout(normal, base, tmp_path / "gate-base", monkeypatch)
    event = write_event(normal, base, f"Closes #1\n{PLAN_TASK}\n", base_ref="main")
    result, errors = gate_check(normal, event, gate=gate)
    assert (result.code, set(errors)) == (1, {"GC015"})
    assert "pkg/src/protected/a.py" in errors["GC015"]
    assert "not implemented" in errors["GC015"]


def test_codeowners_pattern_outside_the_subset_is_a_usage_error(repo: Repo) -> None:
    """A CODEOWNERS pattern with syntax outside the supported subset exits 2 rather than under-protecting."""
    base = make_gate_repo(repo, base_files={CODEOWNERS: "/pkg/[ab].py @owner\n"})
    repo.commit({"pkg/src/new.py": "y = 2\n"}, "feat: change")
    assert gate_check(repo, write_event(repo, base, BODY))[0].code == 2


def test_gate_branch_merge(repo: Repo) -> None:
    """AC18: the gate branch into main is AW06 in bootstrap mode; any other base than the gate branch is GC013."""
    base = make_gate_repo(repo)
    repo.commit({"pkg/elsewhere.py": "z = 1\n"}, "feat: anything")  # would be GC008 and GC001 if it were checked
    merge = gate_check(repo, write_event(repo, base, "no body\n", base_ref="main", head_ref="build/v1"))[0]
    assert merge.code == 0
    data = json.loads(merge.out)
    assert (data["status"], [f["code"] for f in data["steps"][0]["findings"]]) == ("awaiting-owner", ["AW06"])
    for target in ("main", "release/1"):  # not the gate branch; the other checks still run and accumulate
        result = gate_check(repo, write_event(repo, base, BODY, base_ref=target, name="t.json"))[0]
        assert (result.code, _errors(result)) == (1, {"GC008", "GC013"}), target


def test_gate_branch_with_bootstrap_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC18: with bootstrap off the gate branch is main; a pull request from build/v1 is not special."""
    normal = Repo(tmp_path / "normal")
    base = make_gate_repo(normal, bootstrap=False)
    normal.commit({"pkg/src/new.py": "y\n"}, "feat: change")
    gate = base_checkout(normal, base, tmp_path / "gate-base", monkeypatch)
    wrong = write_event(normal, base, f"Closes #1\n{PLAN_TASK}\n", base_ref="build/v1")
    assert set(gate_check(normal, wrong, gate=gate)[1]) == {"GC013"}
    merge_like = write_event(normal, base, "Closes #1\n", base_ref="main", head_ref="build/v1", name="n.json")
    assert set(gate_check(normal, merge_like, gate=gate)[1]) == {"GC001"}


def test_draft_documents_that_need_the_owner(tmp_path: Path) -> None:
    """Spec 4.5 step 4: in bootstrap mode a draft spec of risk r1 or r2 and a draft large plan are AW01."""
    large = plan_text(status="draft").replace("size: small", "size: large")
    r3_spec = spec_text("draft").replace("risk: r1", "risk: r3")
    quiet = Repo(tmp_path / "quiet")  # a draft spec of risk r3 and a draft plan that is not large wait for no owner
    base = make_gate_repo(quiet, plan=plan_text(status="draft"), base_files={SPEC_PATH: r3_spec})
    result = _commit_and_check(quiet, base, {"pkg/src/new.py": "y = 2\n"}, BODY)
    assert (result.code, _findings(result), json.loads(result.out)["status"]) == (0, [], "pass")
    loud = Repo(tmp_path / "loud")
    base = make_gate_repo(loud, plan=large, base_files={SPEC_PATH: spec_text("draft")})
    result = _commit_and_check(loud, base, {"pkg/src/new.py": "y = 2\n"}, BODY)
    assert result.code == 0
    assert sorted(_findings(result)) == [("AW01", "awaiting", PLAN_PATH), ("AW01", "awaiting", SPEC_PATH)]
