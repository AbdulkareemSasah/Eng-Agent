"""Platform inspector and launcher factory (plan 0002 T22; spec 0002 AC49, section 4.1)."""

import importlib
from types import SimpleNamespace
from typing import Any, cast

import pytest

from eng_harness.servers import _platform, platform_inspector, platform_launcher
from eng_harness.servers._launcher import PosixLauncher
from eng_harness.servers._procinfo import PosixProcessInspector


def test_platform_pair() -> None:
    """On POSIX the pair is the POSIX inspector and a POSIX launcher over that very inspector."""
    inspector = platform_inspector()
    assert isinstance(inspector, PosixProcessInspector)
    launcher = platform_launcher(inspector)
    assert isinstance(launcher, PosixLauncher)
    assert launcher._inspector is inspector
    assert isinstance(platform_launcher(cast(Any, _Other())), PosixLauncher)


class _Other:
    """An inspector that is not the POSIX one: the launcher keeps its own default."""


def test_windows_pair_over_the_given_inspector(monkeypatch: pytest.MonkeyPatch) -> None:
    """On Windows the inspector is over kernel32 and the launcher joins the process and job signatures."""
    modules: dict[str, Any] = {
        "eng_harness.servers._procinfo": SimpleNamespace(
            PROCESS_SIGNATURES={"a": 1},
            CtypesKernel32=lambda signatures: ("kernel32", signatures),
            WindowsProcessInspector=lambda kernel: ("inspector", kernel),
        ),
        "eng_harness.servers._launcher_windows": SimpleNamespace(
            JOB_SIGNATURES={"b": 2}, WindowsLauncher=lambda kernel, inspector: ("launcher", kernel, inspector)
        ),
    }
    monkeypatch.setattr(_platform, "_windows", lambda: True)
    monkeypatch.setattr(importlib, "import_module", lambda name: modules[name])
    inspector = cast(Any, platform_inspector())
    assert inspector == ("inspector", ("kernel32", {"a": 1}))
    assert cast(Any, platform_launcher(inspector)) == ("launcher", ("kernel32", {"a": 1, "b": 2}), inspector)
