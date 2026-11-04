"""Tests of the secret scan (spec 4.11, AC46) and of the ``security`` job files (AC62).

Sample secrets are built at run time from parts, so the repository scan does not flag this file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from eng_dev_gate.checks.check import make_handler
from eng_dev_gate.toolrun import SubprocessToolRunner
from support.repo import Repo, RunResult
from support.toy import GATE_YML, make_workspace

GITHUB_TOKEN = "gh" + "p_" + "a1" * 18  # 36 alphanumerics
SAMPLES = {  # test id -> (rule id, a text that the rule must match)
    "github-token": ("github-token", GITHUB_TOKEN),
    "github-fine-grained": ("github-fine-grained-token", "github" + "_pat_" + "11AAAA_bbbb"),
    "aws": ("aws-access-key-id", "AK" + "IA" + "ABCDEFGH12345678"),
    "google": ("google-api-key", "AI" + "za" + "a" * 35),
    "slack": ("slack-token", "xo" + "xb-" + "1234-abcd"),
    "anthropic": ("anthropic-key", "sk-" + "ant-" + "api03-abcdef"),
    "pem": ("private-key", "-----BEGIN " + "RSA PRIVATE" + " KEY-----"),
    "assignment": ("credential-assignment", "pass" + 'word = "' + "hunter22" + '"'),
    "assignment-json": ("credential-assignment", '"my_to' + 'ken": "' + "abcdefgh" + '"'),
    "posix-path": ("personal-path", "/ho" + "me/alice/work"),
    "mac-path": ("personal-path", "/Us" + "ers/alice/work"),
    "windows-path": ("personal-path", "C:" + "\\Us" + "ers\\alice"),
}
CLEAN_LINES = [
    "pass" + 'word = "short"',  # fewer than 8 characters
    "to" + "ken = get_" + "token()",  # not a quoted literal
    "/ho" + "me/<name>/work",  # a placeholder, not a name
    "C:" + "\\Us" + "ers\\<name>",
    "x = 1",
]


def _gate_yml(allow: str = "", small: bool = False) -> str:
    text = GATE_YML.replace("1048576", "64") if small else GATE_YML
    return text + (f"secrets:\n  allow:\n{allow}" if allow else "")


def _repo_with_base(repo: Repo, gate_yml: str | None = None) -> str:
    return repo.commit({".gate/gate.yml": gate_yml or _gate_yml(), "README.md": "clean\n"})


def _findings(result: RunResult) -> list[dict[str, object]]:
    return [f for step in json.loads(result.out)["steps"] for f in step["findings"]]


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def test_range_scan_no_echo(repo: Repo) -> None:
    """AC46: SC001 names rule, path, line and fingerprint, never the text; a later removal does not hide it."""
    base = _repo_with_base(repo)
    repo.commit({"src/leak.txt": f"first\nkey = {GITHUB_TOKEN}\n"}, "feat: add")
    repo.commit({"src/leak.txt": "first\n"}, "fix: remove")
    result = repo.run(["secrets", "--range", f"{base}..HEAD"])
    assert result.code == 1
    assert "SC001" in result.out
    assert "github-token" in result.out
    assert "src/leak.txt" in result.out
    assert _fingerprint(GITHUB_TOKEN) in result.out
    assert GITHUB_TOKEN not in result.out + result.err
    structured = repo.run(["--format", "json", "secrets", "--range", f"{base}..HEAD"])
    (finding,) = _findings(structured)
    assert (finding["code"], finding["path"], finding["line"]) == ("SC001", "src/leak.txt", 2)
    assert GITHUB_TOKEN not in structured.out + structured.err


def test_allowlist_fingerprint(repo: Repo) -> None:
    """AC46: an allowlist entry with a matching rule, path and fingerprint suppresses the hit; any mismatch does not."""
    entry = "    - {{rule: github-token, path: {path}, fingerprint: '{fp}'}}\n"
    good = entry.format(path="src/leak.txt", fp=_fingerprint(GITHUB_TOKEN))
    base = _repo_with_base(repo, _gate_yml(good))
    repo.commit({"src/leak.txt": f"{GITHUB_TOKEN}\n"})
    assert repo.run(["secrets", "--range", f"{base}..HEAD"]).code == 0
    for wrong in (
        entry.format(path="src/leak.txt", fp="0" * 12),
        entry.format(path="src/other.txt", fp=_fingerprint(GITHUB_TOKEN)),
    ):
        repo.commit({".gate/gate.yml": _gate_yml(wrong)})
        assert repo.run(["secrets", "--range", f"{base}..HEAD"]).code == 1


@pytest.mark.parametrize("sample", sorted(SAMPLES))
def test_every_rule_matches(repo: Repo, sample: str) -> None:
    """Spec 4.11: each rule of the list matches its sample, in a range and in the tree."""
    rule, text = SAMPLES[sample]
    base = _repo_with_base(repo)
    repo.commit({"a.txt": f"line one\nprefix {text} suffix\n"})
    for argv in (["--range", f"{base}..HEAD"], ["--tree"]):
        result = repo.run(["--format", "json", "secrets", *argv])
        assert result.code == 1, (sample, argv)
        assert {f["line"] for f in _findings(result)} == {2}
        assert any(f"{rule} " in str(f["message"]) for f in _findings(result)), (sample, argv)
        assert text not in result.out + result.err


def test_clean_lines_pass(repo: Repo) -> None:
    base = _repo_with_base(repo)
    repo.commit({"a.txt": "\n".join(CLEAN_LINES) + "\n"})
    assert repo.run(["secrets", "--range", f"{base}..HEAD"]).code == 0
    assert repo.run(["secrets", "--tree"]).code == 0


def test_only_added_lines_of_the_range_are_scanned(repo: Repo) -> None:
    """A leak older than the range, or only in context lines of it, is not reported by the range scan."""
    repo.commit({".gate/gate.yml": _gate_yml(), "a.txt": f"{GITHUB_TOKEN}\nkeep\n"})
    base = repo.commit({"b.txt": "x\n"})
    repo.commit({"a.txt": f"{GITHUB_TOKEN}\nkeep\nmore\n"})
    assert repo.run(["secrets", "--range", f"{base}..HEAD"]).code == 0
    assert repo.run(["secrets", "--tree"]).code == 1


def test_hunk_lines_that_look_like_headers(repo: Repo) -> None:
    """An added line that reads like a diff header is data: the hunk counts decide, not the line prefix."""
    base = _repo_with_base(repo)
    repo.commit({"a.txt": f"++ b/fake\n@@ -1 +1 @@\n{GITHUB_TOKEN}\n"})
    result = repo.run(["--format", "json", "secrets", "--range", f"{base}..HEAD"])
    assert [(f["path"], f["line"]) for f in _findings(result)] == [("a.txt", 3)]


def test_skipped_files_are_sc002(repo: Repo) -> None:
    """Spec 4.11: large and binary files are skipped with the notice SC002 (a notice does not fail)."""
    base = _repo_with_base(repo, _gate_yml(small=True))
    repo.commit({"big.txt": f"{GITHUB_TOKEN}\n" + "x" * 100 + "\n"})
    (repo.root / "bin.dat").write_bytes(b"\0\1\2" + GITHUB_TOKEN.encode())
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "feat: binary")
    for argv in (["--range", f"{base}..HEAD"], ["--tree"]):
        result = repo.run(["--format", "json", "secrets", *argv])
        assert result.code == 0, argv
        assert {(f["code"], f["path"]) for f in _findings(result)} == {("SC002", "big.txt"), ("SC002", "bin.dat")}


def test_tree_scan_reads_tracked_files_only(repo: Repo) -> None:
    _repo_with_base(repo)
    (repo.root / "untracked.txt").write_text(GITHUB_TOKEN, encoding="utf-8")
    assert repo.run(["secrets", "--tree"]).code == 0


@pytest.mark.parametrize("argv", [[], ["--range", "a..b", "--tree"], ["--range", "nodots"], ["--range", "--all..x"]])
def test_bad_arguments_are_usage_errors(repo: Repo, argv: list[str]) -> None:
    _repo_with_base(repo)
    assert repo.run(["secrets", *argv]).code == 2


def test_unknown_revision_is_an_environment_fault(repo: Repo) -> None:
    _repo_with_base(repo)
    assert repo.run(["secrets", "--range", "nope..HEAD"]).code == 3


def _check_secrets(repo: Repo) -> RunResult:
    return repo.run(["--format", "json", "check", "--only", "secrets"], {"check": make_handler(SubprocessToolRunner())})


def test_check_step_uses_the_merge_base_with_the_gate_branch(repo: Repo) -> None:
    """Spec 4.12 step 9: the range is the merge base with origin/<gate_branch>; without that ref the tree is scanned."""
    make_workspace(repo, ["a"])
    old = repo.commit({"old.txt": f"{GITHUB_TOKEN}\n"})
    assert _check_secrets(repo).code == 1  # no origin ref: the whole tree
    repo.git("update-ref", "refs/remotes/origin/build/v1", old)
    repo.commit({"new.txt": "clean\n"})
    assert _check_secrets(repo).code == 0  # the leak is not in origin/build/v1..HEAD
    repo.commit({"new.txt": f"{GITHUB_TOKEN}\n"})
    failed = _check_secrets(repo)
    assert failed.code == 1
    assert GITHUB_TOKEN not in failed.out + failed.err


def test_security_job_files() -> None:
    """AC62: the ``security`` job runs the scan (range on pull requests, tree on pushes) and ``uv audit --locked``."""
    root = Path(__file__).resolve().parents[4]
    action = (root / "tools/eng-dev-gate/actions/security/action.yml").read_text(encoding="utf-8")
    assert "secrets --range" in action
    assert "secrets --tree" in action
    assert "uv audit --locked" in action
    assert "github.event.pull_request.title" not in action
    assert "github.event.pull_request.body" not in action
