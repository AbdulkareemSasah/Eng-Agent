"""CSI reconciliation by reading model state (plan 0002 T14; spec 0002 4.5.7, AC23).

`CsiReconciler` decides what became of a write cut off by a timeout from the state of its object, read with the same
helpers as `check_model` (`_checks.OBSERVE`, `compare`), so units, tables and tolerance are the read-back's: floats
compare within `tolerance_ratio`, the frozen basis field `checks.readback_relative_tolerance_ratio`, never a constant
here (without it a quantity is `unknown`). Rules per tool: setters are `applied` when the state equals the request and
`not_applied` when it equals the pre-image; a pattern is `applied` when present as requested and `not_applied` when
absent; a combination (delete, then add: not atomic) is `partial` when absent but present before; a deleted
combination is `applied` when absent and `not_applied` when present; anything else, and a read-back that is not
available, is `unknown`. Analysis and design are always `unknown`: no proof of end of the abandoned host call exists
(gap H-G7), so the host's answer is evidence only and nothing is re-run. Units: canonical in the evidence, as read-back.
Errors: `ContractError` from a host read (the tool port turns a timeout into `unknown`). Not here: the Sasaah audit-log
lines of the op (no reader exists yet).
"""

from collections.abc import Callable
from typing import Any, Literal, cast

from pydantic import JsonValue

from eng_harness.adapters._toolport import Decision, HostRead, LostWrite
from eng_harness.adapters.csi import products
from eng_harness.adapters.csi._checks import OBSERVE, Expect, Snapshot, Want, compare, expect, snapshot
from eng_harness.adapters.csi._state import CsiStateReader
from eng_harness.adapters.csi.products import _sap2000_edits as sap2000_edits
from eng_harness.adapters.csi.products._safe_state import SafeStateReader
from eng_harness.adapters.csi.products._sap2000_state import Sap2000StateReader
from eng_harness.servers import CallEffect

__all__ = ["CsiReconciler"]

LONG = frozenset({"csi_run_analysis", "csi_design_run"})  # `long` role; no proof of end of an abandoned call (H-G7)
_UNAVAILABLE = "READBACK_UNAVAILABLE"
_Outcome = Literal["applied", "not_applied", "partial", "unknown"]


def _seen(item: Expect, snap: Snapshot) -> tuple[bool, Want | None]:
    """Whether the object's state could be read, and the state (`None`: the object is absent)."""
    try:
        return True, OBSERVE[item.helper](snap, item.subject)
    except KeyError, TypeError, ValueError:  # a table that was not read (OQ-G10): the helper has nothing to show
        return False, None


def _as_requested(item: Expect, snap: Snapshot, tolerance: float | None) -> bool | None:
    """True when the state shows the request, False when it does not, `None` when that cannot be told."""
    issue = compare(item, snap, tolerance)
    return None if issue is not None and issue.code == _UNAVAILABLE else issue is None


def _frame_matches(row: dict[str, Any], want: Want, tolerance: float | None) -> bool:
    """True when a frame row has the requested section and end points within `tolerance`."""
    if row.get("section") != want.get("section"):
        return False
    i_pt, j_pt = row["i"], row["j"]
    pairs = (
        ("xi_mm", i_pt["x_mm"]),
        ("yi_mm", i_pt["y_mm"]),
        ("zi_mm", i_pt["z_mm"]),
        ("xj_mm", j_pt["x_mm"]),
        ("yj_mm", j_pt["y_mm"]),
        ("zj_mm", j_pt["z_mm"]),
    )
    for name, seen in pairs:
        wanted = want.get(name)
        if not isinstance(wanted, int | float) or not isinstance(seen, int | float):
            return False
        if tolerance is None:
            if seen != wanted:
                return False
        elif abs(seen - wanted) > tolerance * abs(wanted):
            return False
    return True


def _outcome(
    lost: LostWrite, item: Expect, snap: Snapshot, tolerance: float | None
) -> tuple[_Outcome, tuple[str, ...]]:
    """The row of spec 4.5.7 for the tool of `lost` given the state read in `snap`."""
    shows = _as_requested(item, snap, tolerance)
    if shows is None:
        return "unknown", ()
    name, absent = lost.descriptor.name, _seen(item, snap)[1] is None
    if name == "csi_delete_load_combo":
        return ("applied" if shows else "not_applied"), ()
    if shows:
        return "applied", ()
    if name == "csi_add_load_pattern":
        return ("not_applied" if absent else "unknown"), ()
    if name == "csi_add_load_combo":
        if not absent or not lost.known:
            return "unknown", ()
        return ("not_applied", ()) if lost.pre_image is None else ("partial", (item.subject.id,))
    before = lost.pre_image  # a setter: the state equals the pre-image (an object that was absent stays absent)
    if lost.known and (before is None or isinstance(before, dict)):
        return (
            "not_applied" if _as_requested(Expect(item.helper, item.subject, before), snap, tolerance) else "unknown"
        ), ()
    return "unknown", ()


class CsiReconciler:
    """The `Reconciler` of the CSI tool port: `product` names the host, `tolerance_ratio` the read-back tolerance."""

    def __init__(
        self,
        *,
        product: str,
        tolerance_ratio: float | None,
        tolerance: Callable[[], float | None] | None = None,
    ) -> None:
        """`tolerance_ratio` is the frozen ratio; `tolerance` lazily supplies it and is queried until a value arrives.

        Without either, a quantity read-back remains unknown. A supplied zero is a value, never a missing tolerance.
        """
        self._product, self._tolerance, self._profile = product, tolerance_ratio, products.profile(product)
        self._provider = tolerance

    async def decide(self, lost: LostWrite, read: HostRead) -> Decision:
        """The outcome of `lost` (spec 4.5.7); the evidence is what was read."""
        if lost.descriptor.name in LONG:
            return await self._long(lost, read)
        if lost.descriptor.name == "csi_add_frame_by_coord" and self._profile.add_frame_naming == "reply":
            return await self._add_frame_by_geometry(lost, read)
        item = expect(lost.model)
        snap = await self._snapshot(lost, read)
        if self._tolerance is None and self._provider is not None:
            self._tolerance = self._provider()
        outcome, missing = _outcome(lost, item, snap, self._tolerance)
        seen: dict[str, JsonValue] = {
            "requested": item.want, "observed": _seen(item, snap)[1], "pre_image_known": lost.known,
            "pre_image": lost.pre_image,
        }  # fmt: skip
        return Decision(outcome=outcome, missing=missing, evidence=seen)

    async def observe(self, lost: LostWrite, read: HostRead) -> dict[str, JsonValue] | None:
        """`{"observed": state}` of the written object (`None` as a value: absent); no read-back for the long tools."""
        if lost.descriptor.name in LONG:
            return None
        if lost.descriptor.name == "csi_add_frame_by_coord" and self._profile.add_frame_naming == "reply":
            snap = await self._snapshot(lost, read)
            frames = snap.state.payloads["model.frame_placements/1"].model_dump(mode="json")["frames"]
            ids = sorted(str(row["id"]) for row in frames)
            return {"observed": {"frame_ids": cast(JsonValue, ids), "frames": cast(JsonValue, frames)}}
        item = expect(lost.model)
        readable, state = _seen(item, await self._snapshot(lost, read))
        return {"observed": state} if readable else None

    async def _add_frame_by_geometry(self, lost: LostWrite, read: HostRead) -> Decision:
        """AC12: applied when exactly one new frame matches the requested points and section."""
        if not isinstance(lost.model, sap2000_edits.AddFrameByCoordArgs):
            return Decision(outcome="unknown", evidence={"reason": "not an add-frame model"})
        if self._tolerance is None and self._provider is not None:
            self._tolerance = self._provider()
        snap = await self._snapshot(lost, read)
        frames = snap.state.payloads["model.frame_placements/1"].model_dump(mode="json")["frames"]
        before: set[str] = set()
        if lost.known and isinstance(lost.pre_image, dict):
            ids = lost.pre_image.get("frame_ids")
            if isinstance(ids, list):
                before = {str(item) for item in ids}
        added = [row for row in frames if str(row["id"]) not in before]
        want = expect(lost.model).want or {}
        tol = self._tolerance
        matches = [row for row in added if _frame_matches(row, want, tol)]
        if len(matches) == 1:
            outcome: _Outcome = "applied"
        elif len(matches) == 0 and len(added) == 0:
            outcome = "not_applied"
        else:
            outcome = "unknown"
        evidence: dict[str, JsonValue] = {
            "requested": cast(JsonValue, want),
            "observed": {"added": cast(JsonValue, added), "matches": cast(JsonValue, matches)},
            "pre_image_known": lost.known,
            "pre_image": lost.pre_image,
        }
        return Decision(outcome=outcome, evidence=evidence)

    async def _long(self, lost: LostWrite, read: HostRead) -> Decision:
        """Analysis and design: `unknown` whatever the host answers; `locked` and the raw status codes are evidence."""
        target: dict[str, Any] = {"target": lost.binding.target.model_dump()}
        info = await read("csi_model_info", target, CallEffect.READ)
        evidence: dict[str, JsonValue] = {"locked": info.get("locked"), "proof_of_end": False}
        if lost.descriptor.action == "analysis":
            evidence["analysis_status"] = await read("csi_analysis_status", target, CallEffect.READ)
        return Decision(outcome="unknown", evidence=evidence)

    async def _snapshot(self, lost: LostWrite, read: HostRead) -> Snapshot:
        """The model state and the read-back tables, read as `check_model` reads them."""
        # Ask the profile: declared absences → SAP2000; joint_loads tables → SAFE; else ETABS (spec 0008 AC2).
        if self._profile.declared_absences:
            reader_type: type = Sap2000StateReader
        elif "joint_loads" in self._profile.tables:
            reader_type = SafeStateReader
        else:
            reader_type = CsiStateReader
        reader = reader_type(product=self._product, call=read)
        state = await reader.read(lost.binding.target.pid, None)
        target: dict[str, Any] = {"target": lost.binding.target.model_dump()}
        return await snapshot(reader._rows, target, state, self._profile)  # B-451: the reader's validated read
