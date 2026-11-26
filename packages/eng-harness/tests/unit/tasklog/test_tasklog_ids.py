"""Task and need ids (plan 0015 T3a; spec 0015 §4.2)."""

import re

import pytest
from eng_contract.ids import FixedClock, SeededIdSource

from eng_harness.tasklog._ids import new_need_id, new_task_id

_TASK_ULID = "01KDVDNA00EEHMW00B9ZA4ZDSH"
_TASK_ID = f"task_{_TASK_ULID}"


def test_new_task_id_is_prefixed_ulid() -> None:
    """`task_` plus a ULID from the injected source; two calls differ (§4.2)."""
    ids = SeededIdSource(b"tasklog-ids-test", FixedClock(1_000_000))
    first, second = new_task_id(ids), new_task_id(ids)
    assert re.fullmatch(r"task_[0-9A-HJKMNP-TV-Z]{26}", first)
    assert re.fullmatch(r"task_[0-9A-HJKMNP-TV-Z]{26}", second)
    assert first != second


def test_new_need_id_counts_from_one() -> None:
    """`need_<task ULID>_<n>` with the task's ULID and the ordinal (§4.2)."""
    assert new_need_id(_TASK_ID, 1) == f"need_{_TASK_ULID}_1"
    assert new_need_id(_TASK_ID, 2) == f"need_{_TASK_ULID}_2"


def test_new_need_id_refuses_bad_task_or_ordinal() -> None:
    """A task id without the prefix, or an ordinal below 1, is refused (§4.2)."""
    with pytest.raises(ValueError, match="prefix"):
        new_need_id("bogus", 1)
    with pytest.raises(ValueError, match="ordinal"):
        new_need_id(_TASK_ID, 0)
