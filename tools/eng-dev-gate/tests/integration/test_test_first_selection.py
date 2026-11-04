"""Integration tests of ``test-first`` part 1 (spec 4.7 steps 1 to 4.2; AC22, AC25, AC26, AC28)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from eng_dev_gate.checks.test_first import Outcome, Selection, SubprocessCommitLog, evaluate, resolve_task
from eng_dev_gate.config import load_gate_config
from eng_dev_gate.frontmatter import Task, parse_plan
from eng_dev_gate.report import Finding
from support.pullrequest import BODY, PLAN_PATH, plan_text, write_event
from support.repo import Repo
from support.tfrepo import BASE_TEST, BASE_TEST_PATH, NEW_TEST, SRC, head_of, tf_repo, tf_run

PLAN_TESTS_FIRST = plan_text().replace(
    "tests_first: []", 'tests_first: ["pkg/tests/test_a.py::test_one", "pkg/tests/test_b.py::test_two"]', 1
)
TASK_BODY = "Work-Item: B-001\nPlan-Task: {}\n"


def _evaluate(repo: Repo, base: str, title: str = "feat: x", plan: str | None = None) -> Outcome:
    task = parse_plan(plan, 400).tasks[0] if plan else None
    return evaluate(title, base, head_of(repo), load_gate_config(repo.root), SubprocessCommitLog(repo.root), task)


def _error_codes(output: str) -> list[str]:
    data = json.loads(output)
    return [f["code"] for s in data["steps"] for f in s["findings"] if f["severity"] == "error"]


@pytest.mark.parametrize(
    ("title", "files", "expected"),
    [
        ("docs: guide", SRC, (0, "skipped", ())),
        ("chore(deps): bump", SRC, (0, "skipped", ())),
        ("ci: pin actions", SRC, (0, "skipped", ())),
        ("release: 0.1.0", SRC, (0, "skipped", ())),
        ("docs(x)!: guide", SRC, (0, "skipped", ())),
        ("feat: a spike", {"spikes/s1/run.py": "x = 1\n"}, (0, "skipped", ())),
        ("feat: a spike", {"spikes/s1/run.py": "x = 1\n", **SRC}, (1, "fail", ("TF002",))),
        ("feat!: breaking", SRC, (1, "fail", ("TF002",))),
        ("fix(scope)!: breaking", SRC, (1, "fail", ("TF002",))),
        ("Update stuff", SRC, (1, "fail", ("TF001",))),
        ("feat:nospace", SRC, (1, "fail", ("TF001",))),
        ("feat(): empty scope", SRC, (1, "fail", ("TF001",))),
        ("feat(a b): spaced scope", SRC, (1, "fail", ("TF001",))),
        ("FEAT: upper", SRC, (1, "fail", ("TF001",))),
        ("wip: unknown type", SRC, (1, "fail", ("TF001",))),
        ("feat: ", SRC, (1, "fail", ("TF001",))),
        ("feat: x\nmore", SRC, (1, "fail", ("TF001",))),
        ("docs: x\nmore", SRC, (1, "fail", ("TF001",))),
    ],
)
def test_exempt_types(
    repo: Repo, title: str, files: dict[str, str], expected: tuple[int, str, tuple[str, ...]]
) -> None:
    """AC22: docs, chore, ci, release and spike-only changes are exempt; a title that does not parse is TF001."""
    base = tf_repo(repo)
    repo.commit(files, "feat: change")
    result, status, errors = tf_run(repo, base, title)
    assert (result.code, status, tuple(errors)) == expected


def test_no_test_commit_and_mixed_commit(repo: Repo) -> None:
    """AC25: no `test:` commit is TF002, a test commit with a non-test file TF003, one with no new test TF010."""
    base = tf_repo(repo)
    repo.commit(SRC, "feat: code only")
    assert tf_run(repo, base, "feat: x")[2].keys() == {"TF002"}
    # a commit whose subject only looks like a test commit does not count
    repo.commit({"pkg/other.txt": "1\n"}, "tests: plural")
    repo.commit({"pkg/other.txt": "2\n"}, "Test: capital")
    assert tf_run(repo, base, "feat: x")[2].keys() == {"TF002"}
    repo.commit({BASE_TEST_PATH: BASE_TEST + "\n" + NEW_TEST, "pkg/src/mixed.py": "z = 1\n"}, "test(x): mixed")
    result, status, errors = tf_run(repo, base, "feat: x")
    assert (result.code, status, list(errors)) == (1, "fail", ["TF003"])
    assert errors["TF003"].startswith("pkg/src/mixed.py ")


def test_no_new_test(repo: Repo) -> None:
    """AC25: a first test commit that adds no test (data file, comment-only or blank-line change) is TF010."""
    base = tf_repo(repo)
    repo.commit({"pkg/tests/data.txt": "1\n", BASE_TEST_PATH: "# a comment\n\n\n" + BASE_TEST + "\n\n"}, "test: none")
    assert tf_run(repo, base, "feat: x")[2].keys() == {"TF010"}
    outcome = _evaluate(repo, base)
    assert outcome.selection is None
    assert [f.code for f in outcome.findings] == ["TF010"]


def test_new_and_changed_tests_detected(repo: Repo) -> None:
    """Selection: the first `test:` commit; new, changed and class tests count, unchanged and non-test ones do not."""
    base = tf_repo(repo, base_files={"pkg/tests/test_c.py": "def test_c() -> None:\n    assert True\n"})
    repo.commit(SRC, "feat: code first")
    changed = "def test_one() -> None:\n    assert 1 + 2 == 3\n\n" + NEW_TEST + "\ndef helper() -> int:\n    return 1\n"
    classes = (
        "class TestD:\n    def test_m(self) -> None:\n        assert True\n\n    def other(self) -> None: ...\n\n"
        "class Helper:\n    def test_not(self) -> None: ...\n\nasync def test_async() -> None: ...\n"
    )
    sha = repo.commit(
        {
            BASE_TEST_PATH: changed,
            "pkg/tests/test_c.py": "# moved down\n\ndef test_c() -> None:\n    assert True\n",
            "pkg/tests/test_d.py": classes,
            "pkg/tests/data.txt": "1\n",
        },
        "test(x): red",
    )
    repo.commit({"pkg/tests/test_f.py": NEW_TEST}, "test: a later test commit is ignored")
    outcome = _evaluate(repo, base)
    assert outcome.findings == []
    assert outcome.selection == Selection(
        commit=sha,
        paths=("pkg/tests/data.txt", "pkg/tests/test_a.py", "pkg/tests/test_c.py", "pkg/tests/test_d.py"),
        tests=(
            "pkg/tests/test_a.py::test_one",
            "pkg/tests/test_a.py::test_two",
            "pkg/tests/test_d.py::TestD::test_m",
            "pkg/tests/test_d.py::test_async",
        ),
    )


def test_rename_and_delete_in_test_commit(repo: Repo) -> None:
    """A renamed test file is compared with its old content; a deleted one holds no tests."""
    long_test = "def test_one() -> None:\n" + "    assert 1 + 1 == 2\n" * 8
    base = tf_repo(
        repo, base_files={BASE_TEST_PATH: long_test, "pkg/tests/test_gone.py": "def test_gone() -> None: ...\n"}
    )
    repo.git("mv", BASE_TEST_PATH, "pkg/tests/test_b.py")
    repo.git("rm", "-q", "pkg/tests/test_gone.py")
    repo.commit({"pkg/tests/test_b.py": long_test + "\n" + NEW_TEST}, "test: rename")
    outcome = _evaluate(repo, base)
    assert outcome.findings == []
    assert outcome.selection is not None
    assert outcome.selection.tests == ("pkg/tests/test_b.py::test_two",)
    assert outcome.selection.paths == ("pkg/tests/test_b.py",)


def test_unparseable_test_file(repo: Repo) -> None:
    """A test file that does not parse is a notice and counts no test; the others still count."""
    base = tf_repo(repo)
    repo.commit({BASE_TEST_PATH: "def test_one(:\n", "pkg/tests/test_e.py": NEW_TEST}, "test: broken")
    outcome = _evaluate(repo, base)
    assert [(f.code, f.severity.value, f.path) for f in outcome.findings] == [("TF010", "notice", BASE_TEST_PATH)]
    assert outcome.selection is not None
    assert outcome.selection.tests == ("pkg/tests/test_e.py::test_two",)


def test_unparseable_base_file_counts_every_test_as_new(repo: Repo) -> None:
    """A base version that does not parse cannot show an unchanged test, so every test of the file is new."""
    base = tf_repo(repo, base_files={BASE_TEST_PATH: "def test_one(:\n"})
    repo.commit({BASE_TEST_PATH: BASE_TEST}, "test: repair")
    outcome = _evaluate(repo, base)
    assert outcome.selection is not None
    assert outcome.selection.tests == ("pkg/tests/test_a.py::test_one",)


def test_refactor_and_test_types(repo: Repo) -> None:
    """AC26: refactor with a test file is TF006 (both paths of a rename); test with a non-test file is TF007."""
    base = tf_repo(repo)
    repo.commit(SRC, "refactor: code")
    for title in ("refactor(x): code", "refactor!: code"):
        result, status, errors = tf_run(repo, base, title)
        assert (result.code, status, errors) == (0, "pass", {})
    assert tf_run(repo, base, "test: code")[2].keys() == {"TF007"}
    repo.rename(BASE_TEST_PATH, "pkg/tests/test_b.py")
    result, status, errors = tf_run(repo, base, "refactor: move")
    assert (result.code, status, list(errors)) == (1, "fail", ["TF006"])
    assert BASE_TEST_PATH in errors["TF006"]
    assert "pkg/tests/test_b.py" in errors["TF006"]


def test_test_type_with_tests_only(repo: Repo) -> None:
    """AC26: a `test:` pull request that changes only test files passes; a non-test file is TF007 with its path."""
    base = tf_repo(repo)
    repo.commit({"pkg/tests/test_z.py": NEW_TEST}, "test: more")
    result, status, errors = tf_run(repo, base, "test(x): more")
    assert (result.code, status, errors) == (0, "pass", {})
    repo.commit(SRC, "test: oops")
    result, status, errors = tf_run(repo, base, "test: more")
    assert (result.code, status, list(errors)) == (1, "fail", ["TF007"])
    assert errors["TF007"].startswith("pkg/src/new.py ")


def test_tests_first_files(repo: Repo) -> None:
    """AC28: a `tests_first` file that the first test commit does not touch is TF008, once per file."""
    base = tf_repo(repo, plan=PLAN_TESTS_FIRST)
    repo.commit({BASE_TEST_PATH: BASE_TEST + "\n" + NEW_TEST}, "test: red")
    outcome = _evaluate(repo, base, plan=PLAN_TESTS_FIRST)
    assert [(f.code, f.severity.value, f.path) for f in outcome.findings] == [("TF008", "error", "pkg/tests/test_b.py")]
    assert outcome.selection is None
    # from the event: the plan task is read from the gate branch through the body
    result = repo.run(["--format", "json", "test-first", "--event", str(write_event(repo, base, BODY))])
    assert (result.code, _error_codes(result.out)) == (1, ["TF008"])
    repo.commit({"pkg/tests/test_b.py": NEW_TEST}, "test: a later commit does not satisfy it")
    assert [f.code for f in _evaluate(repo, base, plan=PLAN_TESTS_FIRST).findings] == ["TF008"]
    repo.git("reset", "-q", "--hard", base)
    repo.commit({BASE_TEST_PATH: BASE_TEST + "\n" + NEW_TEST, "pkg/tests/test_b.py": NEW_TEST}, "test: both files")
    assert _evaluate(repo, base, plan=PLAN_TESTS_FIRST).findings == []


def test_plan_task_resolution(repo: Repo) -> None:
    """The task comes from the single Plan-Task line, read at the gate ref; anything else names no task."""
    tf_repo(repo, plan=PLAN_TESTS_FIRST)
    config, git = load_gate_config(repo.root), SubprocessCommitLog(repo.root)

    def resolve(line: str) -> Task | Finding | None:
        return resolve_task(TASK_BODY.format(line), config, git, "origin/build/v1")

    found = resolve(f"{PLAN_PATH}#T1")
    assert isinstance(found, Task)
    assert (found.id, found.tests_first[0]) == ("T1", "pkg/tests/test_a.py::test_one")
    assert resolve_task("Work-Item: B-001\n", config, git, "origin/build/v1") is None
    assert resolve("none (trivial)") is None
    for bad in ("nonsense", f"{PLAN_PATH}#T9", "pkg/docs/plans/0002-missing.md#T1", f"{PLAN_PATH}#T1\nPlan-Task: x#T1"):
        notice = resolve(bad)
        assert isinstance(notice, Finding)
        assert (notice.code, notice.severity.value) == ("TF008", "notice")
    broken = repo.commit({"pkg/docs/plans/0003-bad.md": "no front matter\n"})
    repo.git("update-ref", "refs/remotes/origin/build/v1", broken)
    assert isinstance(resolve("pkg/docs/plans/0003-bad.md#T1"), Finding)


def test_selected_pull_request_is_judged_by_the_runs(repo: Repo) -> None:
    """A pull request that passes selection is judged by the runs (T17): a test that is green at the base is TF004."""
    base = tf_repo(repo)
    repo.commit({BASE_TEST_PATH: BASE_TEST + "\n" + NEW_TEST}, "test: not red")
    result, status, errors = tf_run(repo, base, "feat: x")
    assert (result.code, status, list(errors)) == (1, "fail", ["TF004"])
    event = write_event(repo, base, TASK_BODY.format("none (trivial)"))
    assert repo.run(["test-first", "--event", str(event)]).code == 1


def test_inputs(repo: Repo, tmp_path: Path) -> None:
    """Options: all of --base, --head, --title together, or an event; a push event is skipped, a fork is exit 2."""
    base = tf_repo(repo)
    head = head_of(repo)
    assert repo.run(["test-first"]).code == 2
    assert repo.run(["test-first", "--base", base, "--head", head]).code == 2
    push = tmp_path / "push.json"
    push.write_text(json.dumps({"ref": "refs/heads/build/v1", "after": head}), encoding="utf-8")
    skipped = repo.run(["--format", "json", "test-first", "--event", str(push)])
    assert (skipped.code, json.loads(skipped.out)["status"]) == (0, "skipped")
    repo.commit(SRC, "feat: code")
    fork = write_event(repo, base, BODY, head_repo="other/fork")
    assert repo.run(["test-first", "--event", str(fork)]).code == 2
