"""Command `stop` (spec 0006 sections 4.2.1, 4.4.8, AC9, AC71; plan 0006 T16).

Purpose: write `<run_dir>/stop.json` only while the run lock is held by a live engine, and optionally wait for
the lock to be released. Units: wait timeout in seconds. Errors: unknown run is `NOT_FOUND` (6), invalid workspace
or negative wait is `USAGE` (2).
"""

import time
from argparse import Namespace
from typing import TYPE_CHECKING

from eng_harness._runlock import is_locked
from eng_harness.cli._control import write_stop
from eng_harness.cli._exit import ExitCode
from eng_harness.cli._status import existing_run_dir, require_workspace, say_error

if TYPE_CHECKING:
    from eng_harness.cli import CliDeps

_POLL_INTERVAL_S = 0.05


def stop_command(args: Namespace, deps: CliDeps) -> int:
    """`stop RUN_ID`: request a live run to pause at the next safe point (spec 0006 AC9)."""
    if args.wait is not None and args.wait < 0:
        say_error(deps, "--wait must be at least 0")
        return ExitCode.USAGE
    workspace = require_workspace(deps)
    if workspace is None:
        return ExitCode.USAGE
    run_dir = existing_run_dir(deps, workspace, args.run_id)
    if run_dir is None:
        return ExitCode.NOT_FOUND
    if not is_locked(run_dir):
        deps.stdout.write(f"run {args.run_id} is not running\n")
        return ExitCode.OK
    write_stop(run_dir, "cli", deps.clock)
    deps.stdout.write(f"stop requested for run {args.run_id}\n")
    if args.wait is not None:
        deadline = time.monotonic() + args.wait
        while is_locked(run_dir):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(_POLL_INTERVAL_S, remaining))
        if is_locked(run_dir):
            deps.stdout.write(f"run {args.run_id} is still stopping\n")
        else:
            deps.stdout.write(f"run {args.run_id} stopped\n")
    return ExitCode.OK
