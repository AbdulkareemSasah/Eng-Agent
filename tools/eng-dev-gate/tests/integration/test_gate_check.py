"""Integration tests of ``gate-check`` part 1 (spec 4.5 steps 3 to 7; AC6 to AC11)."""

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
from support.repo import Repo

DECOYS = (
    "```\nPlan-Task: pkg/docs/plans/0001-x.md#T9\nPlan-Task: none (trivial)\n```\n"
    "<!--\nPlan-Task: pkg/docs/plans/0001-x.md#T8\n-->\n<!-- Work-Item: B-999 -->\n"
)


def _change(repo: Repo, base: str, body: str = BODY, files: dict[str, str] | None = None) -> Path:
    repo.commit(files or {"pkg/src/new.py": "y = 2\n"}, "feat: change")
    return write_event(repo, base, body)


def test_valid_pull_request_passes(repo: Repo) -> None:
    """AC6: one Plan-Task and one work item (decoys in fences and comments ignored), plan and spec on the gate."""
    base = make_gate_repo(repo)
    event = _change(repo, base, f"## Summary\n{BODY}\n{DECOYS}")
    result, errors = gate_check(repo, event)
    assert (result.code, errors) == (0, {})
    data = json.loads(result.out)
    assert (data["command"], data["mode"], data["status"]) == ("gate-check", "bootstrap", "awaiting-owner")
    assert [f["code"] for f in data["steps"][0]["findings"]] == ["AW08", "AW03"]  # step 10, never skipped silently
    text = repo.run(["gate-check", "--event", str(event)])
    assert text.code == 0
    assert text.out.splitlines()[0] == "mode: bootstrap"


def test_event_from_environment(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without --event the event file is named by GITHUB_EVENT_PATH; with neither, exit 2."""
    base = make_gate_repo(repo)
    event = _change(repo, base)
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    assert repo.run(["gate-check"]).code == 2
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    assert repo.run(["gate-check"]).code == 0


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ("Work-Item: B-001\n", "GC001"),
        (f"Work-Item: B-001\n{DECOYS}", "GC001"),
        (f"Work-Item: B-001\n{PLAN_TASK}\n{PLAN_TASK}\n", "GC002"),
        ("Work-Item: B-001\nPlan-Task: pkg/docs/plans/0001-x.md\n", "GC002"),
        ("Work-Item: B-001\nPlan-Task: pkg/docs/plans/0001-x.md#T\n", "GC002"),
        ("Work-Item: B-001\nPlan-Task: pkg/docs/other/0001-x.md#T1\n", "GC002"),
        ("Work-Item: B-001\nPlan-Task: pkg/docs/plans/../plans/0001-x.md#T1\n", "GC002"),
        ("Work-Item: B-001\nPlan-Task: /pkg/docs/plans/0001-x.md#T1\n", "GC002"),
        ("Work-Item: B-001\nplan-task: pkg/docs/plans/0001-x.md#T1\n", "GC001"),
        ("Work-Item: B-001\n  Plan-Task: pkg/docs/plans/0001-x.md#T1\n", "GC001"),
        (f"{PLAN_TASK}\n", "GC003"),
        (f"Work-Item: 12\n{PLAN_TASK}\n", "GC003"),
        (f"Work-Item: B-1x\n{PLAN_TASK}\n", "GC003"),
        (f"```\nWork-Item: B-001\n```\n{PLAN_TASK}\n", "GC003"),
    ],
)
def test_plan_task_line_errors(repo: Repo, body: str, code: str) -> None:
    """AC7: a missing, duplicate or malformed Plan-Task line, or a missing work item, gives GC001, GC002 or GC003."""
    base = make_gate_repo(repo)
    result, errors = gate_check(repo, _change(repo, base, body))
    assert result.code == 1
    assert set(errors) == {code}


def test_work_item_forms_by_mode(repo: Repo) -> None:
    """`Closes #n` is accepted in both modes; `Work-Item: B-n` only in bootstrap mode (spec 4.5 body table)."""
    boot = make_gate_repo(repo)
    event = _change(repo, boot, f"Closes #12\n{PLAN_TASK}\n")
    assert gate_check(repo, event)[0].code == 0


def test_work_item_forms_normal_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With bootstrap off only `Closes #n` is a work item; the gate branch is main."""
    repo = Repo(tmp_path / "normal")
    base = make_gate_repo(repo, bootstrap=False)
    repo.commit({"pkg/src/new.py": "y\n"}, "feat: change")
    gate = base_checkout(repo, base, tmp_path / "gate-base", monkeypatch)
    event_main = write_event(repo, base, f"Work-Item: B-001\n{PLAN_TASK}\n", base_ref="main")
    result, errors = gate_check(repo, event_main, gate=gate)
    assert (result.code, set(errors)) == (1, {"GC003", "GC015"})  # GC015: the identity checks are not verified yet
    event_ok = write_event(repo, base, f"Closes #12\n{PLAN_TASK}\n", base_ref="main", name="ok.json")
    result, errors = gate_check(repo, event_ok, gate=gate)
    assert (result.code, set(errors)) == (1, {"GC015"})


def test_plan_not_on_gate_branch(repo: Repo) -> None:
    """AC8: a plan or spec missing from the gate branch is GC004; a draft passes in bootstrap mode, GC006 otherwise."""
    base = make_gate_repo(repo)
    new_plan = "pkg/docs/plans/0002-y.md"
    base = repo.commit({new_plan: plan_text()}, "chore: plan only in the base commit, not on the gate branch")
    repo.commit(
        {"pkg/src/new.py": "y\n"}, "feat: code"
    )  # a plan in the diff would make this a spec and plan pull request
    body = f"Work-Item: B-001\nPlan-Task: {new_plan}#T1\n"
    result, errors = gate_check(repo, write_event(repo, base, body))
    assert (result.code, set(errors)) == (1, {"GC004"})
    assert new_plan in errors["GC004"]
    # the spec named by the plan is missing from the gate branch
    repo2 = Repo(repo.root.parent / "r2")
    base2 = make_gate_repo(repo2, plan=plan_text(spec="pkg/docs/specs/9999-none.md"))
    repo2.commit({"pkg/src/new.py": "y\n"}, "feat: change")
    result, errors = gate_check(repo2, write_event(repo2, base2, BODY, name="e2.json"))
    assert set(errors) == {"GC004"}
    assert "9999-none" in errors["GC004"]


def test_draft_status_by_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC8: `status: draft` passes in bootstrap mode (plan and spec) and is GC006 with bootstrap off."""
    boot = Repo(tmp_path / "boot")
    base = make_gate_repo(boot, plan=plan_text(status="draft"), base_files={SPEC_PATH: spec_text("draft")})
    boot.commit({"pkg/src/new.py": "y\n"}, "feat: change")
    assert gate_check(boot, write_event(boot, base, BODY))[0].code == 0
    normal = Repo(tmp_path / "normal")
    base = make_gate_repo(
        normal, bootstrap=False, plan=plan_text(status="draft"), base_files={SPEC_PATH: spec_text("draft")}
    )
    normal.commit({"pkg/src/new.py": "y\n"}, "feat: change")
    gate = base_checkout(normal, base, tmp_path / "gate-base", monkeypatch)
    event = write_event(normal, base, f"Closes #1\n{PLAN_TASK}\n", base_ref="main")
    result, errors = gate_check(normal, event, gate=gate)
    assert (result.code, set(errors)) == (1, {"GC006", "GC015"})
    assert PLAN_PATH in errors["GC006"]
    assert SPEC_PATH in errors["GC006"]


def test_invalid_front_matter_is_gc005(repo: Repo) -> None:
    """AC13 at the command: a plan whose front matter is invalid is GC005 and names the problem."""
    base = make_gate_repo(repo, plan=plan_text().replace("status: approved", "status: maybe"))
    result, errors = gate_check(repo, _change(repo, base))
    assert (result.code, set(errors)) == (1, {"GC005"})
    assert "status" in errors["GC005"]


def test_unknown_task(repo: Repo) -> None:
    """AC9: a task id that the plan does not define is GC007."""
    base = make_gate_repo(repo)
    body = f"Work-Item: B-001\nPlan-Task: {PLAN_PATH}#T9\n"
    result, errors = gate_check(repo, _change(repo, base, body))
    assert (result.code, set(errors)) == (1, {"GC007"})
    assert "T9" in errors["GC007"]


def test_file_outside_globs_including_rename(repo: Repo) -> None:
    """AC10: each changed path that matches no glob of the task is GC008; a rename counts both paths."""
    base = make_gate_repo(repo, base_files={"pkg/other/old.py": "a = 1\nb = 2\nc = 3\nd = 4\n"})
    repo.rename("pkg/other/old.py", "pkg/src/moved.py")  # old path is outside T1's globs
    repo.commit({"pkg/src/ok.py": "ok\n", "pkg/elsewhere.py": "z\n"}, "feat: more")
    result, errors = gate_check(repo, write_event(repo, base, BODY))
    assert (result.code, set(errors)) == (1, {"GC008"})
    flagged = json.loads(result.out)["steps"][0]["findings"]
    assert sorted(f["path"] for f in flagged if f["code"] == "GC008") == ["pkg/elsewhere.py", "pkg/other/old.py"]


def test_rename_into_outside_path(repo: Repo) -> None:
    """AC10: the new path of a rename that leaves the task's globs is flagged as well."""
    base = make_gate_repo(repo)
    repo.rename("pkg/src/keep.py", "pkg/outside/keep.py")
    result, _ = gate_check(repo, write_event(repo, base, BODY))
    paths = [f["path"] for f in json.loads(result.out)["steps"][0]["findings"] if f["code"] == "GC008"]
    assert paths == ["pkg/outside/keep.py"]


WORKSPACE = {
    "pyproject.toml": '[tool.uv.workspace]\nmembers = ["lib", "pkg"]\n',
    "lib/pyproject.toml": '[project]\nname = "lib"\nversion = "0"\n',
    "pkg/pyproject.toml": '[project]\nname = "pkg"\nversion = "0"\n',
}
NOTES = "# notes\n"


def _scope_repo(repo: Repo, globs: tuple[str, ...] = ("pkg/src/**", "lib/src/**")) -> str:
    """Plan package ``pkg`` and workspace members ``lib`` and ``pkg``; task globs ``globs``."""
    return make_gate_repo(repo, base_files=WORKSPACE, plan=plan_text(files=globs))


def _gc008_paths(out: str) -> list[str]:
    findings = json.loads(out)["steps"][0]["findings"]
    return sorted(f["path"] for f in findings if f["code"] == "GC008")


def test_changelog_and_local_testing_in_scope(repo: Repo) -> None:
    """AC10a: the two files of a member or plan package are in scope beside a changed file matching a task glob."""
    base = _scope_repo(repo)
    files = {
        "pkg/src/new.py": "y = 2\n",
        "pkg/CHANGELOG.md": NOTES,
        "pkg/docs/local-testing.md": NOTES,
        "lib/src/a.py": "a = 1\n",
        "lib/CHANGELOG.md": NOTES,
    }
    result, errors = gate_check(repo, _change(repo, base, files=files))
    assert (result.code, errors) == (0, {})


def test_changelog_and_local_testing_without_task_file_are_outside(repo: Repo) -> None:
    """AC10a: without another changed file under the directory that matches a task glob, they are GC008."""
    base = _scope_repo(repo)
    files = {
        "pkg/CHANGELOG.md": NOTES,
        "pkg/docs/local-testing.md": NOTES,
        "lib/src/a.py": "a = 1\n",  # anchors lib, not pkg
        "pkg/sub/CHANGELOG.md": NOTES,  # not the <dir>/CHANGELOG.md of a member or of the plan package
    }
    result, errors = gate_check(repo, _change(repo, base, files=files))
    assert (result.code, set(errors)) == (1, {"GC008"})
    assert _gc008_paths(result.out) == ["pkg/CHANGELOG.md", "pkg/docs/local-testing.md", "pkg/sub/CHANGELOG.md"]


def test_changelog_in_other_directory_is_outside(repo: Repo) -> None:
    """AC10a: a directory that is neither a workspace member nor holds the plan has no exception."""
    base = _scope_repo(repo, ("pkg/src/**", "other/src/**"))
    files = {"other/src/b.py": "b = 1\n", "other/CHANGELOG.md": NOTES}
    result, errors = gate_check(repo, _change(repo, base, files=files))
    assert (result.code, set(errors)) == (1, {"GC008"})
    assert _gc008_paths(result.out) == ["other/CHANGELOG.md"]


def _lines(n: int) -> str:
    return "".join(f"v{i} = {i}\n" for i in range(n))


def test_budget_counting(repo: Repo) -> None:
    """AC11: additions plus deletions count, except tests, generated and spike files; over the limit is GC009."""
    plan = plan_text(files=("pkg/**", "uv.lock", "spikes/**"), max_changed_lines=10)
    base = make_gate_repo(repo, plan=plan, base_files={"pkg/src/keep.py": "a\nb\nc\n"})
    repo.commit(
        {
            "pkg/src/keep.py": "a\nB\nc\n",  # 1 added + 1 deleted = 2
            "pkg/src/a.py": _lines(3),  # 3
            "pkg/src/b.py": _lines(5),  # 5 -> 10 in total, the limit
            "pkg/tests/test_x.py": _lines(50),
            "pkg/src/test_y.py": _lines(50),
            "uv.lock": _lines(50),
            "spikes/s.py": _lines(50),
        },
        "feat: change",
    )
    result, errors = gate_check(repo, write_event(repo, base, BODY))
    assert (result.code, errors) == (0, {})
    repo.commit({"pkg/src/c.py": "one\n"}, "feat: one more line")
    result, errors = gate_check(repo, write_event(repo, base, BODY, name="e2.json"))
    assert (result.code, set(errors)) == (1, {"GC009"})
    message = errors["GC009"]
    assert "11" in message
    assert message.index("pkg/src/b.py") < message.index("pkg/src/a.py")  # largest files are named, largest first
    assert "uv.lock" not in message
    assert "pkg/tests/test_x.py" not in message


def test_binary_file_counts_zero_with_notice(repo: Repo) -> None:
    """AC11: a binary file counts zero lines and gives a notice, not an error."""
    base = make_gate_repo(repo)
    (repo.root / "pkg/src").mkdir(parents=True, exist_ok=True)
    (repo.root / "pkg/src/blob.bin").write_bytes(bytes(range(256)) * 20)
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "feat: blob")
    result, errors = gate_check(repo, write_event(repo, base, BODY))
    assert (result.code, errors) == (0, {})
    findings = json.loads(result.out)["steps"][0]["findings"]
    assert [(f["severity"], f["path"]) for f in findings] == [
        ("notice", "pkg/src/blob.bin"),
        ("awaiting", None),
        ("awaiting", None),
    ]


def test_push_event_is_skipped(repo: Repo, tmp_path: Path) -> None:
    """A push event exits 0 as skipped (spec 4.5)."""
    make_gate_repo(repo)
    event = tmp_path / "push.json"
    event.write_text(json.dumps({"ref": "refs/heads/build/v1", "after": "a" * 40}), encoding="utf-8")
    result = repo.run(["--format", "json", "gate-check", "--event", str(event)])
    assert result.code == 0
    assert json.loads(result.out)["status"] == "skipped"


def test_fork_is_a_usage_error(repo: Repo) -> None:
    """A pull request from another repository exits 2, never 0 (`none (...)` reasons are tested in part 2)."""
    base = make_gate_repo(repo)
    repo.commit({"pkg/src/new.py": "y\n"}, "feat: change")
    fork = write_event(repo, base, BODY, head_repo="other/r")
    assert repo.run(["gate-check", "--event", str(fork)]).code == 2


def test_gate_ref_option(repo: Repo) -> None:
    """--gate-ref names the ref the plan and spec are read from."""
    base = make_gate_repo(repo)
    repo.git("update-ref", "refs/heads/elsewhere", base)
    repo.git("update-ref", "-d", "refs/remotes/origin/build/v1")
    event = _change(repo, base)
    assert repo.run(["gate-check", "--event", str(event)]).code == 3  # default ref origin/build/v1 does not resolve
    assert repo.run(["gate-check", "--event", str(event), "--gate-ref", "elsewhere"]).code == 0


def _ratchet(version: int = 1, **counts: dict[str, int] | None) -> str:
    return json.dumps({"version": version, "counts": {k: v for k, v in counts.items() if v is not None}}) + "\n"


def _ratchet_case(repo: Repo, recorded: str, changed: str, flagged: bool) -> None:
    base = make_gate_repo(
        repo, base_files={**WORKSPACE, ".gate/ratchet.json": recorded}, plan=plan_text(files=("pkg/src/**",))
    )
    files = {"pkg/src/new.py": "y = 2\n", ".gate/ratchet.json": changed}
    result, errors = gate_check(repo, _change(repo, base, files=files))
    assert (result.code, set(errors)) == ((1, {"GC008"}) if flagged else (0, set()))
    assert _gc008_paths(result.out) == ([".gate/ratchet.json"] if flagged else [])


_ONE = {"noqa": 1}
_TWO = {"noqa": 2}
_ZERO = {"noqa": 0}
_EMPTY: dict[str, int] = {}


@pytest.mark.parametrize(
    ("recorded", "changed", "flagged"),
    [
        (_ratchet(pkg=_ZERO, lib=_ONE), _ratchet(pkg=_ONE, lib=_ONE), False),  # in scope: only pkg changes
        (_ratchet(pkg=_ONE), _ratchet(pkg=_ZERO), False),  # lowering of an in-scope package
        (_ratchet(pkg=_ONE), _ratchet(), False),  # entry of an in-scope package removed
        (_ratchet(lib=_ONE), _ratchet(lib=_ONE, pkg=_ONE), False),  # key added with a count of an in-scope package
        (_ratchet(pkg=_ZERO), _ratchet(pkg=_ONE, lib=_ONE), True),  # count of another package (new entry)
        (_ratchet(pkg=_ONE, lib=_ONE), _ratchet(pkg=_TWO, lib=_TWO), True),  # one package in scope, one not
        (_ratchet(pkg=_ONE, lib=_TWO), _ratchet(pkg=_ONE, lib=_ONE), True),  # lowering of another package
        (_ratchet(pkg=_ONE, lib=_ONE), _ratchet(pkg=_TWO), True),  # entry of another package removed
        (_ratchet(pkg=_ONE, lib=_ONE), _ratchet(pkg=_TWO, libx=_ONE), True),  # another package renamed
        (_ratchet(pkg=_ONE), _ratchet(version=2, pkg=_TWO), True),  # version change
        (_ratchet(pkg=_ONE), _ratchet(pkg=_TWO, lib=_EMPTY), True),  # key added without a count change
        (_ratchet(pkg=_ONE, lib=_EMPTY), _ratchet(pkg=_TWO), True),  # key removed without a count change
        (_ratchet(pkg=_ONE), _ratchet(pkg=_ONE).replace(", ", ","), True),  # a reformat changes no count
        (_ratchet(pkg=_ONE), "not json", True),  # a file that does not parse fails closed
    ],
)
def test_ratchet_baseline_in_scope(repo: Repo, recorded: str, changed: str, flagged: bool) -> None:
    """AC10b: only counts of packages with another in-scope change are in scope; any other change is GC008."""
    _ratchet_case(repo, recorded, changed, flagged)


def test_ratchet_baseline_root_never_anchors(repo: Repo) -> None:
    """AC10b: a count of the workspace root (.) is GC008."""
    _ratchet_case(repo, _ratchet(), _ratchet(**{".": _ONE}), True)


def test_ratchet_baseline_root_beside_package(tmp_path: Path) -> None:
    """AC10b: an in-scope package does not carry a root count along."""
    _ratchet_case(Repo(tmp_path / "r"), _ratchet(pkg=_ONE), _ratchet(pkg=_TWO, **{".": _ONE}), True)


def test_ratchet_baseline_created_in_scope(repo: Repo) -> None:
    """AC10b: a baseline that did not exist before counts every package as zero before the change."""
    base = make_gate_repo(repo, base_files=WORKSPACE)
    files = {"pkg/src/new.py": "y = 2\n", ".gate/ratchet.json": _ratchet(pkg=_ONE)}
    result, errors = gate_check(repo, _change(repo, base, files=files))
    assert (result.code, errors) == (0, {})
