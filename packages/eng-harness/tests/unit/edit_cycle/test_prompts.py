"""The A7 prompt counter over a scripted journal (plan 0007 T10; spec 0007 section 4.9, AC26 unit part)."""

from pathlib import Path

from eng_contract.ids import IdSource
from eng_contract.store import ResultStore
from fixtures.report_run import HEADER

from eng_harness.journal import JournalReader

from .journal_script import Script
from .test_timings import _KINDS, write_cycles


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


def test_prompt_count_is_the_number_of_requests() -> None:
    """The count is the length of the counted requests."""
    from eng_harness.report._edit_cycle import PromptCount

    assert PromptCount(cycle=1, requests=()).count == 0


def test_the_real_change_set_approval_kind_counts_like_the_helper_one(
    run_dir: Path, store: ResultStore, ids: IdSource
) -> None:
    """`ApprovalKind.CHANGE_SET` is stored as `change_set`: the first is the cycle's own, the second is counted."""
    from eng_harness.ctx import ApprovalKind
    from eng_harness.report._edit_cycle import count_prompts

    kind = ApprovalKind.CHANGE_SET.value
    assert kind == "change_set"
    s = Script(run_dir, store, ids)
    s.at(0, _KINDS.RUN_STARTED, {**HEADER, "input_ref": s.base, "basis_ref": s.base})
    s.begin("1/0/0", 10)
    s.approval("first", kind, 11, 1)
    s.approval("second", kind, 13, 1)
    s.approval("third", "CHANGE_SET", 15, 1)
    s.end("1/0/0", 10, 20)
    s.writer.close()
    (cycle,) = count_prompts(JournalReader(run_dir))
    assert [(r.kind, r.title) for r in cycle.requests] == [("change_set", "second"), ("CHANGE_SET", "third")]
