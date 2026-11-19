"""Child blocks of the edit cycle, steps 3 to 10 (spec 0007 section 4.5; plan 0007 T8).

Purpose: `read_state` (steps 3 and 4: read the model, report the differences from the last recorded revision),
`obtain_change_set` (step 5: ask for the change set and check it, asking again while the check fails),
`apply_change_set` (steps 6 to 10: approve, save the revision snapshot, write, read back, decide D-2, save) and
`edit_cycle_once` (the return to step 3 after a voided approval or a restore, spec 0007 4.5.1). Every value moves by
reference; the blocks read statuses, names and lists of stored results through `ctx.read` and never a number.
Units: none here; the calcs and the tool port hold them.
Errors: `AttemptsExhausted` (an engine escalation) when `attempts.change_set` or `attempts.approval_void` runs out;
`ToolFailed`, `CalcRefused` and the other step errors of the ctx calls reach the engine unchanged.
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from eng_contract.refs import Ref
from eng_contract.verdicts import VerdictStatus
from pydantic import BaseModel, ConfigDict

from eng_harness.block import block
from eng_harness.ctx import ApprovalKind, Preview, PreviewItem
from eng_harness.errors import ApprovalVoid
from eng_harness.rules import edit_cycle as edit_rules
from eng_harness.workflows.model_edit_cycle._change_set import ChangeSetDraft
from eng_harness.workflows.model_edit_cycle._points import (
    READBACK_POLICY,
    ReadbackAction,
    ReadbackReason,
    ReadbackState,
)

__all__ = [
    "ApplyInput",
    "ApplyOutput",
    "ChangeSetInput",
    "ChangeSetOutput",
    "ChangeSetRequest",
    "CycleInput",
    "CycleOutput",
    "ReadInput",
    "ReadOutput",
    "Route",
    "StateRefs",
    "apply_change_set",
    "edit_cycle_once",
    "obtain_change_set",
    "read_state",
]

_SECTIONS = ("stories", "frames", "areas", "loads", "restraints")
"""The read-set fields of the step 3 read that the difference report and the read-back check compare."""
_KEYS = (*_SECTIONS, "names")
_NO_FINDINGS = (False, False, False, False)
_REVISION = "revision"
"""The id of the step 6 preview item that stands for the step 7 revision save (spec 0007 4.5 step 6)."""
_TOOLS = {
    "frame_section": ("csi_assign_frame_section", "frame", ("section",)),
    "area_section": ("csi_assign_area_section", "area", ("section",)),
    "wall_section": ("csi_define_wall_section", "", ("name", "material", "shell_type")),
    "frame_uniform_load": ("csi_set_frame_load_distributed", "frame", ("pattern", "direction")),
    "area_uniform_load": ("csi_set_area_load_uniform", "area", ("pattern", "direction")),
    "load_pattern_add": ("csi_add_load_pattern", "", ("name", "type")),
    "load_combination_set": ("csi_add_load_combo", "", ("name", "type")),
    "load_combination_delete": ("csi_delete_load_combo", "", ("name",)),
    "joint_restraints": ("csi_set_point_restraint", "joint", ("ux", "uy", "uz", "rx", "ry", "rz")),
}
"""Spec 0007 4.3.1: the tool of each item kind, the argument that names one target (empty: the item names its
object), and the item fields passed as they are. Values are added from the check's resolved references."""


class _M(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ChangeSetRequest(_M):
    """The engineer's answer to the change-set request: one field, `change_set` (spec 0007 4.3.1)."""

    change_set: ChangeSetDraft


class Route(StrEnum):
    """How `apply_change_set` ended: the next step of the cycle."""

    DONE = "done"
    REJECTED = "rejected"
    VOID = "void"
    RESTORED = "restored"
    STOPPED = "stopped"


_ROUTES = {
    ReadbackAction.CONTINUE: Route.DONE,
    ReadbackAction.RESTORE_PREVIOUS: Route.RESTORED,
    ReadbackAction.STOP_CYCLE: Route.STOPPED,
}


class StateRefs(_M):
    """The references of one model-state read: the host status and each read-set result (spec 0007 4.10)."""

    status: Ref
    stories: Ref
    frames: Ref
    areas: Ref
    loads: Ref
    restraints: Ref
    names: Ref


class ReadInput(_M):
    """The model key and the read `R[k-1]` the difference report starts from (none in cycle 1)."""

    model: str
    previous: StateRefs | None


class ReadOutput(_M):
    """The read `S[k]` and its difference report."""

    state: StateRefs
    diff: Ref


class ChangeSetOutput(_M):
    """A checked change set: its answer field, the draft, and the passing check."""

    answered: Ref
    draft: ChangeSetDraft
    check: Ref


class ChangeSetInput(_M):
    """The read, its difference report and a change set kept from an earlier iteration (checked again, not asked)."""

    state: StateRefs
    diff: Ref
    kept: ChangeSetOutput | None


class ApplyInput(_M):
    """What steps 6 to 10 need: the key, the read, the report and the checked change set (none: an empty one)."""

    model: str
    state: StateRefs
    diff: Ref
    change_set: ChangeSetOutput | None


class ApplyOutput(_M):
    """The route, the read `R[k]` after the writes (none when nothing was read) and the evidence."""

    route: Route
    state: StateRefs | None
    effects: Ref | None
    readback: Ref | None
    snapshot: str | None


class CycleInput(_M):
    """The model key, the read `R[k-1]` and whether a change set is asked (false after `hand_edit`)."""

    model: str
    previous: StateRefs | None
    ask: bool


class CycleOutput(_M):
    """How the cycle ended, its read `R[k]` and report, and the evidence of its apply step."""

    route: Route
    state: StateRefs
    diff: Ref
    change_set: ChangeSetOutput | None
    effects: Ref | None
    readback: Ref | None


def _ref(value: object) -> Ref:
    return Ref.model_validate({"$ref": value})


async def _data(ctx: Any, ref: Ref, pointer: str) -> Any:
    """The value of a stored result at `pointer` as plain data (the dump, so that no attribute `value` is read)."""
    return (await ctx.read(ref, pointer)).model_dump()["value"]


def _state(read: Any) -> StateRefs:
    return StateRefs(status=read.ref, **{key: _ref(read.summary[key]) for key in _KEYS})


def _sides(prefix: str, refs: StateRefs) -> dict[str, Ref]:
    """The flat `before_<field>` or `after_<field>` inputs of the difference and read-back calcs (spec 0007 4.5)."""
    return {f"{prefix}_{name}": getattr(refs, name) for name in _SECTIONS}


@block(name="read_state", version=1)
async def read_state(ctx: Any, inp: ReadInput) -> ReadOutput:
    """Steps 3 and 4: read the model, then the differences from `R[k-1]` (from itself in cycle 1)."""
    state = _state(await ctx.tool("csi_read_model_state", {"model": inp.model}))
    before = state if inp.previous is None else inp.previous
    diff = await ctx.calc(
        "harness.model_diff",
        {**_sides("before", before), **_sides("after", state), "basis": ctx.basis.record_ref()},
    )
    return ReadOutput(state=state, diff=diff.ref)


@block(name="obtain_change_set", version=1)
async def obtain_change_set(ctx: Any, inp: ChangeSetInput) -> ChangeSetOutput:
    """Step 5: ask for the change set and check it; a check that fails asks again, up to `attempts.change_set`."""
    title = "Change set"
    kept = inp.kept
    async for _ in ctx.attempts(ctx.basis.count("attempts.change_set")):
        if kept is None:
            asked = await ctx.ask(ChangeSetRequest, title=title)
            answered = asked.field_ref("change_set")
            draft = ChangeSetRequest.model_validate(asked.model_dump()["value"]).change_set
        else:
            answered, draft, kept = kept.answered, kept.draft, None
        check = await ctx.calc(
            "harness.change_set_check",
            {
                "change_set": answered,
                "frames": inp.state.frames,
                "areas": inp.state.areas,
                "restraints": inp.state.restraints,
                "names": inp.state.names,
                "diff": inp.diff,
                "basis": ctx.basis.record_ref(),
            },
        )
        if await _data(ctx, check.ref, "/status") == "PASS":
            break
        title = f"Change set: the check {check.ref.ref} refused the previous one"
    return ChangeSetOutput(answered=answered, draft=draft, check=check.ref)


def _item_args(model: str, item: Any, resolved: Mapping[str, Any], target: str) -> dict[str, Any]:
    """The tool arguments of one item and one target; each resolved value goes in as its reference."""
    _, aim, fields = _TOOLS[item.kind]
    dumped = item.model_dump(mode="json")
    args: dict[str, Any] = {"model": model, **{name: dumped[name] for name in fields}}
    if aim:
        args[aim] = target
    if item.kind == "load_combination_set":
        args["items"] = [{"case": term["case"]} for term in dumped["items"]]
    for value in resolved["values"]:
        *parents, last = value["pointer"].removeprefix("/").split("/")
        node: Any = args
        for part in parents:
            node = node[int(part)] if isinstance(node, list) else node[part]
        node[last] = _ref(value["ref"])
    return args


def _found(rows: Any, unexpected: Any) -> tuple[bool, bool, bool, bool]:
    """Which kinds of finding the read-back has: mismatch, missing, unexpected, not read (spec 0007 4.6, D-2)."""
    seen = {row["result"] for row in rows}
    return ("mismatch" in seen, "missing" in seen, bool(unexpected), "not_read" in seen)


async def _decide(
    ctx: Any, status: VerdictStatus, found: tuple[bool, bool, bool, bool], reason: ReadbackReason, refs: tuple[Ref, ...]
) -> Route:
    """D-2 (spec 0007 4.6): the read-back status, its findings and the reason, through the cascade; the next step."""
    mismatch, missing, unexpected, not_read = found
    state = ReadbackState(
        status=status,
        has_mismatch=mismatch,
        has_missing=missing,
        has_unexpected=unexpected,
        has_not_read=not_read,
        reason=reason,
        refs=refs,
    )
    decision = await ctx.decide(
        "edit_cycle_readback_result", ReadbackAction, state, [edit_rules.readback_result_pass], READBACK_POLICY
    )
    return _ROUTES[decision.choice]


async def _approve(ctx: Any, inp: ApplyInput, resolved: list[Any]) -> tuple[Any, list[str]]:
    """Step 6: the approval of the revision item and one item per change-set item; the accepted item ids."""
    items = [
        PreviewItem(
            id=row["item_id"],
            label=f"{row['kind']}: {', '.join(row['targets'])}",
            refs=tuple(_ref(value["ref"]) for value in row["values"]),
        )
        for row in resolved
    ]
    revision = PreviewItem(id=_REVISION, label="Save a revision of the model before the first change", refs=())
    shown = Preview(items=(revision, *items), diff_ref=inp.diff, models=(inp.model,))
    approval = await ctx.approve("Change set", shown, kind=ApprovalKind.CHANGE_SET)
    return approval, [row["item_id"] for row in resolved if approval.accepts(row["item_id"])]


async def _write(ctx: Any, inp: ApplyInput, change: ChangeSetOutput, resolved: list[Any], approval: Any) -> None:
    """Step 8: each accepted item on each of its targets, under the approval, in the order of the change set."""
    by_id = {row["item_id"]: row for row in resolved}
    for item in change.draft.items:
        if item.id in by_id and approval.accepts(item.id):
            tool, aim, _ = _TOOLS[item.kind]
            for target in by_id[item.id]["targets"] if aim else [""]:
                await ctx.tool(tool, _item_args(inp.model, item, by_id[item.id], target), under=approval, item=item.id)


async def _save(ctx: Any, model: str, approval: Any) -> Any:
    """Step 7: save the model in place and as a new revision snapshot, the first write under the approval."""
    args = {"model": model, "as_new_revision": True}
    if approval is None:
        return await ctx.tool("csi_save_model", args)
    return await ctx.tool("csi_save_model", args, under=approval, item=_REVISION)


async def _after(ctx: Any, model: str, done: ApplyOutput) -> ApplyOutput:
    """Act on the D-2 choice: `continue` saves (step 10), `restore_previous` reopens this cycle's snapshot (spec
    0007 4.5.1), `stop_cycle` leaves the model as it is."""
    if done.route is Route.RESTORED:
        await ctx.tool("csi_open_revision", {"model": model, "revision": done.snapshot})
    if done.route is Route.DONE:
        await ctx.tool("csi_save_model", {"model": model})  # step 10
    return done


async def _record(ctx: Any, inp: ApplyInput) -> ApplyOutput:
    """An empty change set (after `hand_edit`): the engineer's changes are saved as a revision, nothing is written."""
    saved = await _save(ctx, inp.model, None)
    snapshot = str(saved.summary["saved_file"]["name"])
    done = ApplyOutput(route=Route.DONE, state=None, effects=None, readback=None, snapshot=snapshot)
    return await _after(ctx, inp.model, done)


@block(name="apply_change_set", version=1)
async def apply_change_set(ctx: Any, inp: ApplyInput) -> ApplyOutput:
    """Steps 6 to 10 of one cycle; an empty change set only records the engineer's changes as a revision."""
    change = inp.change_set
    if change is None:
        return await _record(ctx, inp)
    resolved = await _data(ctx, change.check, "/resolved")
    approval, accepted = await _approve(ctx, inp, resolved)
    if not approval.accepts(_REVISION):
        return ApplyOutput(route=Route.REJECTED, state=None, effects=None, readback=None, snapshot=None)
    expected = await ctx.calc(
        "harness.expected_effects",
        {
            "check": change.check,
            "approval_items": accepted,
            "change_set": change.answered,
            "loads": inp.state.loads,
            "restraints": inp.state.restraints,
            "basis": ctx.basis.record_ref(),
        },
    )
    effects: Ref = expected.ref
    try:
        saved = await _save(ctx, inp.model, approval)
    except ApprovalVoid:  # before the first write: back to step 3 (spec 0007 4.5.1)
        return ApplyOutput(route=Route.VOID, state=None, effects=effects, readback=None, snapshot=None)
    snapshot = str(saved.summary["saved_file"]["name"])
    done = ApplyOutput(route=Route.DONE, state=None, effects=effects, readback=None, snapshot=snapshot)
    try:
        await _write(ctx, inp, change, resolved, approval)
    except ApprovalVoid:  # after a write: the engineer decides (spec 0007 4.5.1)
        route = await _decide(
            ctx, VerdictStatus.NEEDS_ENGINEER, _NO_FINDINGS, ReadbackReason.MODEL_CHANGED_DURING_APPLY, (effects,)
        )
        return await _after(ctx, inp.model, done.model_copy(update={"route": route}))
    after = _state(await ctx.tool("csi_read_model_state", {"model": inp.model}))
    readback = await ctx.calc(
        "harness.readback_check",
        {"effects": effects, **_sides("before", inp.state), **_sides("after", after), "basis": ctx.basis.record_ref()},
    )
    found = _found(await _data(ctx, readback.ref, "/items"), await _data(ctx, readback.ref, "/unexpected"))
    status = VerdictStatus(await _data(ctx, readback.ref, "/status"))
    route = await _decide(ctx, status, found, ReadbackReason.READBACK, (readback.ref, effects))
    return await _after(
        ctx, inp.model, done.model_copy(update={"route": route, "state": after, "readback": readback.ref})
    )


@block(name="edit_cycle_once", version=1)
async def edit_cycle_once(ctx: Any, inp: CycleInput) -> CycleOutput:
    """Steps 3 to 10 of one cycle, again from step 3 after a voided approval or a restore (D-5, spec 0007 4.5.1)."""
    kept: ChangeSetOutput | None = None
    before = inp.previous  # R[k-1]; in cycle 1 the first read, so that a return to step 3 reports the edit (R[0])
    async for _ in ctx.attempts(ctx.basis.count("attempts.approval_void")):
        read = await ctx.block(read_state, ReadInput(model=inp.model, previous=before))
        before = read.state if before is None else before
        if inp.ask:
            kept = await ctx.block(obtain_change_set, ChangeSetInput(state=read.state, diff=read.diff, kept=kept))
        applied = await ctx.block(
            apply_change_set, ApplyInput(model=inp.model, state=read.state, diff=read.diff, change_set=kept)
        )
        if applied.route not in (Route.VOID, Route.RESTORED):
            break
    state = read.state if applied.state is None else applied.state
    return CycleOutput(
        route=applied.route, state=state, diff=read.diff, change_set=kept, effects=applied.effects,
        readback=applied.readback,
    )  # fmt: skip
