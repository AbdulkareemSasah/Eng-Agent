"""Command-line parser and entry point (spec 0006 AC1, AC65)."""

import io
import re
import subprocess
import sys
import tomllib
from argparse import Namespace
from pathlib import Path

from eng_harness.cli import CliDeps, ExitCode, main

ROOT = Path(__file__).resolve().parents[5]
PACKAGE = ROOT / "packages" / "eng-harness"
COMMANDS = ["run", "resume", "status", "stop", "report", "doctor"]


def _call(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, deps=CliDeps(stdout=out, stderr=err, environ={}))
    return code, out.getvalue(), err.getvalue()


def test_commands_exact_and_no_approve() -> None:
    code, out, _ = _call(["--help"])
    assert code == ExitCode.OK
    match = re.search(r"\{([a-z,]+)\}", out)
    assert match is not None
    assert match.group(1).split(",") == COMMANDS
    for word in ("approve", "reject", "sign", "engineer"):
        assert word not in out.lower().split()
    for bad in (["approve"], ["reject"], ["sign"], ["ru", "wf"], ["stat"], ["rep", "x"], ["doc"], []):
        assert _call(bad)[0] == ExitCode.USAGE, bad
    for command in COMMANDS:
        _, text, _ = _call([command, "--help"])
        assert not re.search(r"--(approve|reject|sign|engineer|name)\b", text)


def test_options_of_the_commands() -> None:
    for argv in (
        ["run", "wf", "--input", "i.json", "--basis", "b.yaml", "--template", "t@1", "--mode", "work_on_copy",
         "--run-class", "trial", "--answers", "a.json", "--no-wait", "--wait-timeout", "5", "--no-browser",
         "--progress", "json", "--json", "--no-report"],
        ["resume", "01RUN", "--answers", "a.json", "--no-wait", "--json"],
        ["status"], ["status", "01RUN", "--json"], ["stop", "01RUN", "--wait", "3"],
        ["report", "01RUN", "--out", "r.html", "--force"], ["doctor", "--json", "--show-paths"],
    ):
        _, _, err = _call(argv)
        assert "usage:" not in err, (argv, err)
    assert _call(["run", "wf", "--mode", "nonsense"])[0] == ExitCode.USAGE
    assert _call(["--workspace", "relative/dir", "status"])[0] == ExitCode.USAGE


def test_handlers_receive_parsed_arguments() -> None:
    seen: list[tuple[str, str | None]] = []

    def handler(args: Namespace, deps: CliDeps) -> int:
        seen.append((args.command, args.run_id))
        return 12

    deps = CliDeps(stdout=io.StringIO(), stderr=io.StringIO(), environ={}, handlers={"status": handler})
    assert main(["status", "01RUN"], deps=deps) == ExitCode.STOPPED
    assert seen == [("status", "01RUN")]


def test_entry_point_and_root_form() -> None:
    package = tomllib.loads((PACKAGE / "pyproject.toml").read_text(encoding="utf-8"))
    assert package["project"]["scripts"] == {"eng-harness": "eng_harness.cli:main"}
    root = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "eng-harness" not in root.get("project", {}).get("scripts", {})
    assert "eng_harness.cli" in package["tool"]["eng-gate"]["public_modules"]
    _, expected, _ = _call(["--help"])
    done = subprocess.run(  # noqa: S603  # B-177: fixed interpreter and module, no external input
        [sys.executable, "-m", "eng_harness", "--help"], capture_output=True, check=False, timeout=60
    )
    assert done.returncode == 0
    assert done.stdout.decode("utf-8").replace("\r\n", "\n") == expected
    assert "usage: eng-harness" in expected
