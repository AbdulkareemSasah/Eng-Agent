"""Platform pair on Windows (plan 0002 T22; spec 0002 AC49).

Defined only on Windows (marker `windows`); it has not run there yet and is an owner local test.
"""

import sys

import pytest

if sys.platform == "win32":
    from eng_harness.servers import platform_inspector, platform_launcher
    from eng_harness.servers._launcher_windows import WindowsLauncher
    from eng_harness.servers._procinfo import WindowsProcessInspector

    @pytest.mark.windows
    def test_platform_pair_windows() -> None:
        inspector = platform_inspector()
        assert isinstance(inspector, WindowsProcessInspector)
        launcher = platform_launcher(inspector)
        assert isinstance(launcher, WindowsLauncher)
        assert launcher._inspector is inspector
        assert inspector.identity(__import__("os").getpid()) is not None
