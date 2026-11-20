"""IDEA reconciliation of write-like tools (plan 0014 T8; spec 0014 AC18, section 4.8).

Purpose: decide the outcome of a lost `idea_native_set_loads` from the `out_path` file and its read-back, and
always answer `unknown` for `idea_calculate` without re-running anything (the result lives only in memory after
the call returns; S-12 / `E/IdeaSession.cs:1058-1086`). Units: host N and N.m compared through
`compare_loads_readback` with the frozen basis field `checks.readback_relative_tolerance_ratio`. Errors:
`ContractError` from a host read (the tool port turns a timeout into `unknown`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import JsonValue

from eng_harness.adapters._toolport import Decision, HostRead, LostWrite
from eng_harness.adapters.idea import _checks as checks
from eng_harness.adapters.idea._tools import NativeSetLoadsArgs
from eng_harness.servers import CallEffect

__all__ = ["IdeaReconciler"]

_CALCULATE_TOOLS = frozenset({"idea_calculate"})
_SET_LOADS = "idea_native_set_loads"


class IdeaReconciler:
    """The `Reconciler` of the IDEA tool port (spec 0014 AC18)."""

    def __init__(self, *, tolerance_ratio: float | None) -> None:
        """`tolerance_ratio` is the frozen `checks.readback_relative_tolerance_ratio` (basis field)."""
        self._tolerance = tolerance_ratio

    async def decide(self, lost: LostWrite, read: HostRead) -> Decision:
        """The outcome of `lost` (AC18); never re-runs `idea_calculate`."""
        name = lost.descriptor.name
        if name in _CALCULATE_TOOLS:
            return Decision(
                outcome="unknown",
                evidence={
                    "reason": "idea_calculate has no readable state after a timeout; re-run is the engineer's decision",
                    "tool": name,
                },
            )
        if name == _SET_LOADS:
            return await self._set_loads(lost, read)
        return Decision(outcome="unknown", evidence={"reason": "no reconciliation rule", "tool": name})

    async def observe(self, lost: LostWrite, read: HostRead) -> dict[str, JsonValue] | None:
        """Observed state of a lost write, or `None` when the adapter has no read-back for it."""
        if lost.descriptor.name in _CALCULATE_TOOLS:
            return None
        if lost.descriptor.name != _SET_LOADS:
            return None
        if not isinstance(lost.model, NativeSetLoadsArgs):
            return None
        out_path = Path(lost.model.out_path)
        if not out_path.is_file():
            return {"observed": None, "out_path": str(out_path)}
        body = await read(
            "idea_native_get_loads",
            {"path": str(out_path), "connection_id": lost.model.connection_id},
            CallEffect.READ,
        )
        return {"observed": body.get("loads"), "out_path": str(out_path)}

    async def _set_loads(self, lost: LostWrite, read: HostRead) -> Decision:
        """applied when out_path exists and reads back as requested; not_applied when absent; else unknown."""
        if not isinstance(lost.model, NativeSetLoadsArgs):
            return Decision(outcome="unknown", evidence={"reason": "args are not NativeSetLoadsArgs"})
        out_path = Path(lost.model.out_path)
        if not out_path.is_file():
            return Decision(
                outcome="not_applied",
                evidence={"out_path": str(out_path), "exists": False},
            )
        body = await read(
            "idea_native_get_loads",
            {"path": str(out_path), "connection_id": lost.model.connection_id},
            CallEffect.READ,
        )
        got = body.get("loads")
        got_list: list[dict[str, Any]] | None
        if isinstance(got, list) and all(isinstance(item, dict) for item in got):
            got_list = [dict(item) for item in got]
        else:
            got_list = None
        requested = [dict(item) for item in lost.model.loads]
        issues = checks.compare_loads_readback(
            requested=requested,
            got=got_list,
            tolerance_ratio=self._tolerance,
            connection=lost.model.connection_id,
        )
        mismatch = [issue for issue in issues if issue.code in ("READBACK_MISMATCH", "READBACK_UNAVAILABLE")]
        if not mismatch:
            return Decision(
                outcome="applied",
                evidence={"out_path": str(out_path), "exists": True, "read_back_ok": True},
            )
        return Decision(
            outcome="unknown",
            evidence={
                "out_path": str(out_path),
                "exists": True,
                "read_back_ok": False,
                "issue_codes": [issue.code for issue in mismatch],
            },
        )
