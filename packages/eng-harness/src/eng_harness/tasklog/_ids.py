"""Task and need ids (spec 0015 section 4.2).

Purpose: `new_task_id` forms `task_<ULID>` from the injected `IdSource`; `new_need_id` forms
`need_<task ULID>_<n>` from a task id and the need's ordinal. Folder names carry no owner words.
Units: none; the need ordinal starts at 1.
Errors: `ValueError` when the task id has no `task_` prefix or the ordinal is below 1.
"""

from eng_contract.ids import IdSource

__all__ = ["NEED_ID_PREFIX", "TASK_ID_PREFIX", "new_need_id", "new_task_id"]

TASK_ID_PREFIX = "task_"
"""Prefix of a task id: `task_` plus a ULID from the injected `IdSource` (spec 0015 §4.2)."""

NEED_ID_PREFIX = "need_"
"""Prefix of a need id: `need_<task ULID>_<n>` (spec 0015 §4.2)."""

_FIRST_ORDINAL = 1
"""The ordinal of a task's first need (spec 0015 §4.2: `need_<task ULID>_<n>` counts from 1)."""


def new_task_id(ids: IdSource) -> str:
    """A new `task_<ULID>` id from `ids` (spec 0015 §4.2)."""
    return f"{TASK_ID_PREFIX}{ids.new_ulid()}"


def new_need_id(task_id: str, ordinal: int) -> str:
    """The `need_<task ULID>_<n>` id of the task's nth need (spec 0015 §4.2).

    Raises:
        ValueError: `task_id` has no `task_` prefix, or `ordinal` is below 1.
    """
    if not task_id.startswith(TASK_ID_PREFIX):
        raise ValueError(f"task id has no {TASK_ID_PREFIX!r} prefix")
    if ordinal < _FIRST_ORDINAL:
        raise ValueError(f"need ordinal starts at {_FIRST_ORDINAL}, got {ordinal}")
    return f"{NEED_ID_PREFIX}{task_id[len(TASK_ID_PREFIX) :]}_{ordinal}"
