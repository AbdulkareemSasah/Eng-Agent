"""Launch-address opener and terminal writer (spec 0006 AC61, section 4.4.4)."""

from pathlib import Path

import pytest

from eng_harness.cli._opener import open_address, write_to_terminal

ADDRESS = "http://127.0.0.1:50000/launch/CODE"


class _Spawn:
    def __init__(self, result: int = 0, error: OSError | None = None) -> None:
        self.calls: list[tuple[list[str], dict[str, str]]] = []
        self.result = result
        self.error = error

    def __call__(self, command: list[str], env: dict[str, str]) -> int:
        self.calls.append((command, env))
        if self.error is not None:
            raise self.error
        return self.result


def test_browser_variable_ignored() -> None:
    spawn = _Spawn()
    environ = {"BROWSER": "capture-program", "PATH": "/usr/bin", "HOME": "/h"}
    assert open_address(ADDRESS, platform="linux", environ=environ, spawn=spawn, startfile=None) is True
    [(command, env)] = spawn.calls
    assert command == ["xdg-open", ADDRESS]
    assert "BROWSER" not in env
    assert env == {"PATH": "/usr/bin", "HOME": "/h"}
    assert environ["BROWSER"] == "capture-program"


def test_platform_commands() -> None:
    spawn = _Spawn()
    assert open_address(ADDRESS, platform="darwin", environ={}, spawn=spawn, startfile=None)
    assert spawn.calls[0][0] == ["open", ADDRESS]
    started: list[str] = []
    assert open_address(ADDRESS, platform="win32", environ={}, spawn=spawn, startfile=started.append)
    assert started == [ADDRESS]
    assert len(spawn.calls) == 1


@pytest.mark.parametrize("spawn", [_Spawn(result=3), _Spawn(error=FileNotFoundError("xdg-open"))])
def test_failure_is_reported_not_raised(spawn: _Spawn) -> None:
    assert open_address(ADDRESS, platform="linux", environ={}, spawn=spawn, startfile=None) is False


def test_startfile_failure_is_reported() -> None:
    def broken(_: str) -> None:
        raise OSError("no association")

    assert open_address(ADDRESS, platform="win32", environ={}, spawn=_Spawn(), startfile=broken) is False


def test_terminal_writer(tmp_path: Path) -> None:
    target = tmp_path / "tty"
    target.write_text("", encoding="utf-8")
    assert write_to_terminal(ADDRESS, device=target) is True
    assert ADDRESS in target.read_text(encoding="utf-8")
    assert write_to_terminal(ADDRESS, device=tmp_path / "missing" / "tty") is False
