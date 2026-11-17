"""The platform inspector and launcher, one factory for the doctor and `build_ports` (spec 0002 4.1)."""

import importlib
import os
from typing import cast

from eng_harness.servers._launcher import PosixLauncher, ProcessLauncher
from eng_harness.servers._procinfo import PosixProcessInspector, ProcessInspector


def _windows() -> bool:
    return os.name == "nt"


def platform_inspector() -> ProcessInspector:
    """The POSIX inspector, or the Windows one."""
    if not _windows():
        return PosixProcessInspector()
    pi = importlib.import_module("eng_harness.servers._procinfo")
    return cast(ProcessInspector, pi.WindowsProcessInspector(pi.CtypesKernel32(pi.PROCESS_SIGNATURES)))


def platform_launcher(inspector: ProcessInspector) -> ProcessLauncher:
    """The POSIX launcher, or the Job Object launcher, over `inspector`."""
    if not _windows():
        if not isinstance(inspector, PosixProcessInspector):
            raise TypeError(f"POSIX launcher needs a PosixProcessInspector, not {type(inspector).__name__}")
        return PosixLauncher(inspector)
    pi, jobs = (importlib.import_module(f"eng_harness.servers.{name}") for name in ("_procinfo", "_launcher_windows"))
    kernel32 = pi.CtypesKernel32({**pi.PROCESS_SIGNATURES, **jobs.JOB_SIGNATURES})
    return cast(ProcessLauncher, jobs.WindowsLauncher(kernel32, inspector))
