"""The A7 prompt counter over a scripted journal (plan 0007 T10; spec 0007 section 4.9, AC26 unit part)."""

from pathlib import Path

from eng_contract.ids import IdSource
from eng_contract.store import ResultStore

from .test_timings import write_cycles


def test_prompt_counter(run_dir: Path, store: ResultStore, ids: IdSource) -> None:
    """Each cycle's own requests do not count; re-asks, repeats, engine requests and D-2 or D-3 screens do."""
    from eng_harness.report._edit_cycle import count_prompts

    counts = count_prompts(write_cycles(run_dir, store, ids, open_tail=True))
    assert [(c.cycle, c.count) for c in counts] == [(1, 1), (2, 3), (3, 1)]
    assert [(r.kind, r.title) for r in counts[0].requests] == [("block", "Change set again")]
    assert [(r.kind, r.title) for r in counts[1].requests] == [
        ("CHANGE_SET", "ap3"), ("engine.in_flight", "In flight"), ("engine.decision", "edit_cycle_analysis_messages"),
    ]  # fmt: skip
    assert [(r.kind, r.title) for r in counts[2].requests] == [("INFO", "open1")]
