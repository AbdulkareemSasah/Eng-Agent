"""The stop file of a run (spec 0006 4.4.8; AC9, AC10).

Purpose: a stop request is the file `<run folder>/stop.json` with `requested_at` and `by`, written by renaming a
temporary file over it so that a reader never sees a part, and removed by the run process and by `resume`.
`FileRunControl` is the engine's `RunControlPort` over it. Units: none. Errors: `read_stop` raises `ValueError` for a
damaged file; every other function leaves the file system's `OSError` alone.
"""

import os
from pathlib import Path
from typing import Literal

from eng_contract.ids import Clock, Timestamp
from pydantic import BaseModel, ConfigDict, ValidationError

STOP_FILE = "stop.json"


class StopRequest(BaseModel):
    """The stop file's content: when it was asked for, and by what (`cli` is `stop`, `signal` the first interrupt)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_at: Timestamp
    by: Literal["cli", "signal"]


def write_stop(run_dir: Path, by: Literal["cli", "signal"], clock: Clock) -> None:
    """Ask the run in `run_dir` to stop: a temporary file in that folder, renamed over `stop.json`."""
    temporary = run_dir / f"{STOP_FILE}.{os.getpid()}.tmp"
    temporary.write_text(StopRequest(requested_at=clock.now(), by=by).model_dump_json(), encoding="utf-8")
    os.replace(temporary, run_dir / STOP_FILE)


def read_stop(run_dir: Path) -> StopRequest | None:
    """The request in `run_dir`, or `None` when there is none. Raises: `ValueError` for a damaged stop file."""
    try:
        return StopRequest.model_validate_json((run_dir / STOP_FILE).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except ValidationError as damaged:
        raise ValueError("the stop file is damaged") from damaged


def remove_stop(run_dir: Path) -> None:
    """Remove the stop file of `run_dir`; no error when there is none."""
    (run_dir / STOP_FILE).unlink(missing_ok=True)


class FileRunControl:
    """The engine's `RunControlPort`: a run stops while `<runs_dir>/<run_id>/stop.json` exists, whatever it holds."""

    def __init__(self, runs_dir: Path) -> None:
        self._runs_dir = runs_dir

    def stop_requested(self, run_id: str) -> bool:
        """True while the stop file of the run exists."""
        return (self._runs_dir / run_id / STOP_FILE).exists()
