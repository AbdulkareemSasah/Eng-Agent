"""Launch-address opener and terminal writer (spec 0006 section 4.4.4, AC61).

The opener never uses `webbrowser` (which honours `BROWSER`). The address is never written to standard output or
standard error: only to the controlling terminal.
"""

import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

Spawn = Callable[[list[str], dict[str, str]], int]
StartFile = Callable[[str], None]

_COMMANDS = {"darwin": "open"}
_STARTFILE: StartFile | None = getattr(os, "startfile", None)


def _run(command: list[str], env: dict[str, str]) -> int:
    return subprocess.run(command, env=env, check=False, timeout=30, capture_output=True).returncode  # noqa: S603  # B-177: fixed opener, address is the only argument


def open_address(
    address: str,
    *,
    platform: str = sys.platform,
    environ: Mapping[str, str] = os.environ,
    spawn: Spawn = _run,
    startfile: StartFile | None = _STARTFILE,
) -> bool:
    """Open `address` with the platform opener, with `BROWSER` removed from the child environment.

    Returns:
        True when the opener ran and succeeded; False on any failure (the caller then shows the address on the
        controlling terminal only). Nothing is raised for an opener failure.
    """
    try:
        if platform == "win32":
            if startfile is None:
                return False
            startfile(address)
            return True
        env = {key: value for key, value in environ.items() if key != "BROWSER"}
        return spawn([_COMMANDS.get(platform, "xdg-open"), address], env) == 0
    except OSError, subprocess.SubprocessError:
        return False


def write_to_terminal(text: str, *, device: Path | None = None) -> bool:
    """Write `text` to the controlling terminal (`/dev/tty`, `CONOUT$` on Windows); False when there is none."""
    target = device or Path("CONOUT$" if sys.platform == "win32" else "/dev/tty")
    try:
        with target.open("a", encoding="utf-8", newline="\n") as terminal:
            terminal.write(text + "\n")
    except OSError:
        return False
    return True
