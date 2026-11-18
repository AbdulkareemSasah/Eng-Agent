"""Launch address never reaches stdout, stderr or the journal; fallback writes to the terminal only (spec 0006 AC61)."""

from functools import partial
from pathlib import Path

from helpers.cli_deps import WORKFLOW, Rig, approves, approving_opener

from eng_harness.cli import CliDeps, ExitCode
from eng_harness.cli._opener import write_to_terminal


def test_address_never_on_stdout_or_stderr(tmp_path: Path) -> None:
    assert CliDeps().terminal_writer is write_to_terminal

    # 1. Redirected stderr, opener failing, no controlling terminal: address and code appear on neither stream.
    missing_tty = tmp_path / "missing" / "tty"
    rig = Rig(
        tmp_path / "no_tty",
        script=approves(wait=True),
        open_with=lambda _: False,
        terminal_writer=partial(write_to_terminal, device=missing_tty),
    )
    assert rig.main("run", WORKFLOW, "--wait-timeout", "1", "--progress", "plain") == ExitCode.AWAITING_ENGINEER
    [address] = rig.opened
    code = address.rsplit("code=", 1)[1]
    streams = rig.out.getvalue() + rig.err.getvalue()
    assert address not in streams
    assert code not in streams
    assert "127.0.0.1" not in streams
    assert "the launch address cannot be shown here; run from a terminal, or use --no-wait and resume later" in streams
    for path in rig.runs.rglob("*"):
        if path.is_file():
            raw = path.read_bytes()
            assert address.encode() not in raw
            assert code.encode() not in raw

    # 2. Opener failing and `--no-browser` with a controlling terminal: address goes to the terminal only.
    for name, options in [("failed", []), ("no_browser", ["--no-browser"])]:
        tty = tmp_path / name / "tty"
        tty.parent.mkdir(parents=True)
        tty.write_text("", encoding="utf-8")
        rig = Rig(
            tmp_path / name,
            script=approves(wait=True),
            open_with=lambda _: False,
            terminal_writer=partial(write_to_terminal, device=tty),
        )
        assert (
            rig.main("run", WORKFLOW, *options, "--wait-timeout", "1", "--json", "--progress", "off")
            == ExitCode.AWAITING_ENGINEER
        ), name
        shown = tty.read_text(encoding="utf-8")
        assert "http://127.0.0.1:" in shown, (name, shown)
        assert "/launch?code=" in shown, (name, shown)
        terminal_code = shown.strip().rsplit("code=", 1)[1]
        streams = rig.out.getvalue() + rig.err.getvalue()
        assert "127.0.0.1" not in streams, name
        assert terminal_code not in streams, name
        assert "cannot be shown here" not in streams, name

    # 3. Successful browser open writes only the fixed message to stderr and leaves the terminal untouched.
    tty = tmp_path / "opened" / "tty"
    tty.parent.mkdir(parents=True)
    tty.write_text("", encoding="utf-8")
    rig = Rig(tmp_path / "opened", script=approves(wait=True), terminal_writer=partial(write_to_terminal, device=tty))
    rig.open_with = approving_opener(rig)
    assert rig.main("run", WORKFLOW, "--no-report", "--progress", "off") == ExitCode.OK
    assert "approval page opened in your browser\n" in rig.err.getvalue()
    assert tty.read_text(encoding="utf-8") == ""
    assert rig.opened[0] not in rig.out.getvalue() + rig.err.getvalue()
