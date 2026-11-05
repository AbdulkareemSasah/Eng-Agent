"""Expected step times from the journals of earlier runs (spec 0006 section 4.3, AC15).

Purpose: a read-only index of `(kind, name)` to the median duration of completed instances in the latest completed
runs of one workflow. Units are milliseconds. Journals are opened read-only; a journal that fails verification is
logged and skipped, because an estimate is a display aid and must never stop a run.
"""

import logging
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from eng_harness._text import format_duration_ms
from eng_harness.errors import JournalIntegrityError
from eng_harness.journal import JournalReader

_LOG = logging.getLogger(__name__)


class ExpectedSettings(Protocol):
    """The two `[progress]` settings that this module reads."""

    history_runs: int
    min_samples: int


@dataclass(frozen=True)
class Estimate:
    """Median, minimum and maximum duration in milliseconds over `samples` earlier step instances."""

    median_ms: int
    min_ms: int
    max_ms: int
    samples: int


def estimate(samples: Sequence[int]) -> Estimate:
    """Summarize durations (ms); the median is `statistics.median` floored, so it lies between minimum and maximum.

    Raises:
        ValueError: `samples` is empty.
    """
    if not samples:
        raise ValueError("no samples")
    return Estimate(int(statistics.median(samples)), min(samples), max(samples), len(samples))


class ExpectedTimes:
    """Estimates keyed by `(kind, name)`; lookups are dictionary reads."""

    def __init__(self, estimates: Mapping[tuple[str, str], Estimate]) -> None:
        """Hold the estimates as given."""
        self._estimates = dict(estimates)

    @classmethod
    def build(cls, workspace: Path, workflow: str, settings: ExpectedSettings) -> ExpectedTimes:
        """Read the latest `history_runs` runs of `workflow` that ended COMPLETED under `<workspace>/runs`.

        Run folders are `run_<ULID>`, so descending name order is newest first. Only completed step instances with a
        duration count; failed, reconciled and rerun instances contribute nothing. A pair with fewer than
        `min_samples` samples is left out.
        """
        durations: dict[tuple[str, str], list[int]] = {}
        taken = 0
        folders = sorted((p for p in (workspace / "runs").glob("run_*") if p.is_dir()), reverse=True)
        for folder in folders:
            if taken >= settings.history_runs:
                break
            if not (folder / "journal.sqlite").is_file():
                continue
            try:
                reader = JournalReader(folder)
                try:
                    run = reader.run()
                    steps = reader.steps() if run.workflow == workflow and run.status == "COMPLETED" else []
                finally:
                    reader.close()
            except JournalIntegrityError:
                _LOG.warning("journal skipped for expected times: %s", folder.name, exc_info=True)
                continue
            if run.workflow != workflow or run.status != "COMPLETED":
                continue
            taken += 1
            for step in steps:
                if step.status == "completed" and step.duration_ms is not None:
                    durations.setdefault((step.kind, step.name), []).append(step.duration_ms)
        return cls({k: estimate(v) for k, v in durations.items() if len(v) >= settings.min_samples})

    def lookup(self, kind: str, name: str) -> Estimate | None:
        """The estimate of a step, or None when there is none."""
        return self._estimates.get((kind, name))

    def describe(self, kind: str, name: str) -> str:
        """`expected ~02:10 (01:05 to 04:40, 7 earlier runs)` or `no estimate`."""
        est = self.lookup(kind, name)
        if est is None:
            return "no estimate"
        low, high = format_duration_ms(est.min_ms), format_duration_ms(est.max_ms)
        return f"expected ~{format_duration_ms(est.median_ms)} ({low} to {high}, {est.samples} earlier runs)"
