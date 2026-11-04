"""Integration tests of the ``ratchet`` command and step on temporary repositories (spec 4.9, AC40)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from eng_dev_gate.checks import ratchet
from support.repo import Repo, RunResult, make_repo
from support.toy import GATE_YML, make_workspace

SUPPRESSED = "x = 1  # noqa: E501 B-1\ny = 2  # noqa: E501 B-2\n"


class FixedClock:
    """A clock that always reports 2026-06-15."""

    def today(self) -> date:
        return date(2026, 6, 15)


def _ratchet(repo: Repo, *argv: str, gate_root: Repo | None = None) -> RunResult:
    options = ["--gate-root", str(gate_root.root)] if gate_root else []
    return repo.run(["--format", "json", *options, "ratchet", *argv], {"ratchet": ratchet.make_handler(FixedClock())})


def _file(count: int) -> dict[str, str]:
    return {".gate/ratchet.json": json.dumps({"version": 1, "counts": {"pkgs/a": {"noqa": count}}})}


def _base(directory: Path, count: int | None) -> Repo:
    base = make_repo(directory)
    base.commit({".gate/gate.yml": GATE_YML, **({} if count is None else _file(count))})
    return base


def _codes(result: RunResult) -> list[tuple[str, str]]:
    steps = json.loads(result.out)["steps"]
    return [(f["code"], f["severity"]) for s in steps for f in s["findings"]]


def test_json_raise_vs_base(repo: Repo, tmp_path: Path) -> None:
    """AC40: a count raised against the base commit is AW05 (awaiting owner in bootstrap mode, exit 0)."""
    make_workspace(repo, ["a"], module=SUPPRESSED)
    repo.commit(_file(2))
    raised = _ratchet(repo, gate_root=_base(tmp_path / "raised", 1))
    assert raised.code == 0, raised.out
    assert _codes(raised) == [("AW05", "awaiting")]
    assert json.loads(raised.out)["status"] == "awaiting-owner"
    absent = _ratchet(repo, gate_root=_base(tmp_path / "absent", None))  # a package absent from the base counts as zero
    assert _codes(absent) == [("AW05", "awaiting")]
    assert _codes(_ratchet(repo, gate_root=_base(tmp_path / "same", 2))) == []
    assert _codes(_ratchet(repo, gate_root=_base(tmp_path / "lower", 5))) == []
    assert _codes(_ratchet(repo)) == []  # no gate root: nothing to compare with


def test_update_lowers_and_never_raises(repo: Repo) -> None:
    """AC40: ``--update`` rewrites the file with lower counts and refuses to raise one."""
    make_workspace(repo, ["a"], module=SUPPRESSED)
    repo.commit(_file(5))
    path = repo.root / ".gate" / "ratchet.json"
    assert _codes(_ratchet(repo)) == [("RT001", "notice")]
    done = _ratchet(repo, "--update")
    assert done.code == 0
    assert json.loads(path.read_text(encoding="utf-8"))["counts"]["pkgs/a"]["noqa"] == 2
    assert _codes(_ratchet(repo)) == []
    repo.commit(_file(1))
    before = path.read_text(encoding="utf-8")
    refused = _ratchet(repo, "--update")
    assert refused.code == 1
    assert _codes(refused) == [("RT001", "error")]
    assert path.read_text(encoding="utf-8") == before


def test_invalid_file_is_rt005_exit_2(repo: Repo) -> None:
    make_workspace(repo, ["a"])
    repo.commit({".gate/ratchet.json": '{"version": 1, "counts": {"pkgs/a": {"noqa": -1}}}'})
    bad = _ratchet(repo)
    assert bad.code == 2
    assert "RT005" in bad.err


def test_step_runs_in_check(repo: Repo) -> None:
    """The ``ratchet`` step is part of ``check`` and fails it on a missing issue reference (RT006)."""
    make_workspace(repo, ["a"], module="x = 1  # noqa: E501\n")
    repo.commit(_file(1))
    result = repo.run(["--format", "json", "check", "--only", "ratchet"])
    assert result.code == 1, result.out
    (step,) = json.loads(result.out)["steps"]
    assert step["name"] == "ratchet"
    assert [f["code"] for f in step["findings"]] == ["RT006"]
