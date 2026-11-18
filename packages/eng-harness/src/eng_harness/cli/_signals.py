"""Interrupt signal handling for `run` and `resume` (spec 0006 sections 4.2.3, 4.4.8; AC10)."""

import contextlib
import os
import signal
import threading
from collections.abc import Callable, Iterator
from types import FrameType
from typing import NoReturn, TextIO

from eng_contract.ids import Clock

from eng_harness.cli._control import write_stop
from eng_harness.cli._exit import ExitCode
from eng_harness.cli._wiring import RunIdCell


def _flush(*streams: TextIO) -> None:
    for stream in streams:
        with contextlib.suppress(OSError, ValueError):
            stream.flush()


class InterruptController:
    """Two-stage interrupt handler: first signal requests a stop if a run folder exists, second exits 130."""

    def __init__(
        self,
        cell: RunIdCell,
        clock: Clock,
        stdout: TextIO,
        stderr: TextIO,
        *,
        exit_process: Callable[[int], NoReturn] | None = None,
    ) -> None:
        self._cell, self._clock, self._stdout, self._stderr = cell, clock, stdout, stderr
        self._exit: Callable[[int], NoReturn] = exit_process or os._exit
        self._requested = False

    def handle(self, _signum: int, _frame: FrameType | None = None) -> None:
        """Handle an interrupt signal (`SIGINT` or `SIGTERM`)."""
        if not self._requested and self._cell.run_id is not None:
            folder = self._cell.folder()
            if folder.is_dir():
                self._requested = True
                try:
                    write_stop(folder, "signal", self._clock)
                except OSError:
                    self._abort()
                with contextlib.suppress(OSError, ValueError):
                    self._stderr.write("eng-harness: stop requested; send another interrupt to exit now\n")
                    self._stderr.flush()
                return
        self._abort()

    def _abort(self) -> NoReturn:
        self._requested = True
        _flush(self._stdout, self._stderr)
        self._exit(int(ExitCode.INTERRUPTED))


@contextlib.contextmanager
def install_interrupt_handler(
    cell: RunIdCell,
    clock: Clock,
    stdout: TextIO,
    stderr: TextIO,
    *,
    exit_process: Callable[[int], NoReturn] | None = None,
) -> Iterator[InterruptController]:
    """Install `InterruptController` for `SIGINT` (and `SIGTERM` when defined) on the main thread, then restore."""
    controller = InterruptController(cell, clock, stdout, stderr, exit_process=exit_process)
    if threading.current_thread() is not threading.main_thread():
        yield controller
        return
    signals = [signal.SIGINT]
    sigterm = getattr(signal, "SIGTERM", None)
    if sigterm is not None:
        signals.append(sigterm)
    previous = [(sig, signal.signal(sig, controller.handle)) for sig in signals]
    try:
        yield controller
    finally:
        for sig, handler in reversed(previous):
            signal.signal(sig, handler)
