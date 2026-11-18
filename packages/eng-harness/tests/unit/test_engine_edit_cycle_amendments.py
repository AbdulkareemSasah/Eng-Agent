"""Engine amendments of the edit cycle (plan 0007 T6; engine spec 0001 rules EC1 to EC6; spec 0007 AC33).

The block bodies are plain test code wrapped as workflows. The fake host stands for the adapter: `save_n` is a save
tool that writes a new file when its argument `new` is true and a save over the original when `target` is `original`;
`open_m` opens a model. No value here is an engineering value.
"""

import asyncio
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from eng_contract.envelope import HostInfo, Provenance, SuccessEnvelope
from eng_contract.kinds.basis import DesignBasis
from fakes.ports import Raise
from pydantic import JsonValue
from workflows.chain import ChainInput, ChainOutput
from workflows.ctx_flows import change_set, reply, request_id
from workflows.modes import mode_rig
from workflows.rig import Rig, request

import eng_harness.basis
import eng_harness.block
from eng_harness import errors
from eng_harness.basis import FieldSpec
from eng_harness.block import RegistryError, WorkflowDef, workflow
from eng_harness.ctx import ApprovalKind, BasisView
from eng_harness.engine import PermissionMode, RunOutcome, RunStatus
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev
from eng_harness.ports import Reconciliation, ToolInfo

T = EventType
COPY, EACH, AUTO = PermissionMode.WORK_ON_COPY, PermissionMode.APPROVE_EACH_WRITE, PermissionMode.AUTONOMOUS_LOGGED
ZERO = "0" * 64  # the file hash the fake host reports for every model


class Saving(ToolInfo):
    """A save tool: `new` true writes a new file, `target` `original` overwrites the engineer's original."""

    def saves_new_file(self, args: Mapping[str, JsonValue]) -> bool:
        """True when the call writes a new file."""
        return args.get("new") is True

    def overwrites_original(self, args: Mapping[str, JsonValue]) -> bool:
        """True for `target` `original`."""
        return args.get("target") == "original"


def make_rig(root: Path) -> Rig:
    """The mode rig with `open_m` (a read that opens a model) and `save_n` (a write, action save)."""
    rig = mode_rig(root)
    for tool in (
        ToolInfo(name="open_m", effect="read", action="open", host_key="csi", model_param="model"),
        Saving(name="save_n", effect="write", action="save", host_key="csi", model_param="model"),
    ):
        rig.host._tools[tool.name] = tool  # the fake host takes its tools at construction
    return rig


def wf(body: Callable[[Any], Any], **options: Any) -> WorkflowDef[ChainInput, ChainOutput]:
    """A workflow that runs `body` and returns what it returns as the references of its output."""

    @workflow(name="chain", version=1, description="Runs its body.", **options)
    async def run(ctx: Any, inp: ChainInput) -> ChainOutput:
        return ChainOutput(refs=list(await body(ctx)))

    return run


def saved(
    rig: Rig, key: str, revision: int, *, file: str | None = None, sha: str = ZERO, host: bool = True
) -> SuccessEnvelope:
    """A save result as an adapter returns it: `provenance.host` with the revision, and `saved_file` for a new file."""
    state = rig.host.models[key]
    assert state.model_id is not None
    info = HostInfo(program="csi", version="1", model_id=state.model_id, model_revision=revision) if host else None
    producer = Provenance(
        tool="harness", tool_version="fake", host=info, inputs={}, started_at=rig.clock.now(), duration_ms=0
    )
    summary: dict[str, JsonValue] = {} if file is None else {"saved_file": {"name": file, "sha256": sha}}
    stored = rig.store.put("harness.run_output/1", {"value": summary}, producer)
    return SuccessEnvelope(
        contract="eng-contract/1", ok=True, result_id=stored.result_id, kind="harness.run_output/1", summary=summary,
        complete=True, provenance=producer,
    )  # fmt: skip


def drive(rig: Rig, flow_of: WorkflowDef[ChainInput, ChainOutput], mode: PermissionMode) -> RunOutcome:
    """Start the run and answer every approval it asks for, as the engineer `ada`, until it ends."""
    engine = rig.engine(flow_of)
    outcome = asyncio.run(engine.start(request(mode=mode)))
    while outcome.status is RunStatus.PAUSED:
        for rid in outcome.pending:
            rig.approvals.script(rid, reply(rig))
        outcome = asyncio.run(engine.resume(outcome.run_id))
    return outcome


def revisions(rig: Rig, run_id: str) -> list[tuple[str | None, ev.ModelSaved]]:
    """The `model_saved` events of the run (path, payload)."""
    return [(e.path, e.payload) for e in rig.events(run_id) if isinstance(e.payload, ev.ModelSaved)]


def order(rig: Rig, run_id: str) -> list[tuple[EventType, str | None]]:
    """The (type, path) of the step and save events of the run, in journal order."""
    kinds = (T.STEP_STARTED, T.STEP_COMPLETED, T.MODEL_SAVED)
    return [(e.type, e.path) for e in rig.events(run_id) if e.type in kinds and e.path and not e.path.startswith("@")]


@pytest.mark.parametrize("mode", [COPY, EACH, AUTO])
def test_copy_on_open_every_mode(tmp_path: Path, mode: PermissionMode) -> None:
    """EC1: the copy follows the first open of a model key in each mode, once; a later open takes none."""
    rig = make_rig(tmp_path)

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("open_m", {"model": "m1"})
        await ctx.tool("write_b", {"n": 1, "model": "m1"})
        await ctx.tool("open_m", {"model": "m1"})
        return [(await ctx.tool("read_m", {"model": "m1"})).ref.ref]

    outcome = drive(rig, wf(body, copy_on_open=True), mode)
    assert outcome.status is RunStatus.COMPLETED
    run_id, origin = outcome.run_id, rig.host.models["m1"]
    assert [(e.tool, e.model, e.args["model"]) for e in rig.host.ledger] == [
        ("open_m", "m1", "m1"), ("write_b", "m1.copy", "m1.copy"), ("open_m", "m1.copy", "m1.copy"),
        ("read_m", "m1.copy", "m1.copy"),
    ]  # fmt: skip
    assert rig.log.count("host.working_copy") == 1  # no second copy before the first write, none for the later open
    (taken,) = revisions(rig, run_id)
    assert taken[0] == "0~post.working_copy.m1"
    copied = taken[1]
    assert (copied.model_key, copied.role, copied.origin_sha256) == ("m1.copy", "working_copy", origin.file_sha256)
    assert (copied.origin_file_names, copied.file_name) == (["m1.edb"], "m1.copy.edb")
    kinds = order(rig, run_id)
    assert kinds.index((T.MODEL_SAVED, "0~post.working_copy.m1")) < kinds.index((T.STEP_STARTED, "1"))
    assert kinds.index((T.STEP_COMPLETED, "0")) < kinds.index((T.STEP_STARTED, "0~post.working_copy.m1"))
    assert (rig.host.models["m1"].revision, rig.host.models["m1.copy"].revision) == (0, 1)


def test_copy_on_open_off_keeps_the_mode_rules(tmp_path: Path) -> None:
    """EC1: without `copy_on_open` an open takes no copy; `work_on_copy` copies before its first write."""
    steps = [("open_m", {"model": "m1"}), ("write_b", {"n": 1, "model": "m1"})]

    async def body(ctx: Any) -> list[str]:
        return [(await ctx.tool(name, args)).ref.ref for name, args in steps]

    for mode, expected in ((AUTO, []), (COPY, ["1~pre.working_copy.m1"])):
        rig = make_rig(tmp_path / mode.value)
        outcome = drive(rig, wf(body, copy_on_open=False), mode)
        assert [path for path, _ in revisions(rig, outcome.run_id)] == expected
        assert rig.log.count("host.working_copy") == len(expected)


def test_tool_save_journals_revision(tmp_path: Path) -> None:
    """EC2: a live tool save journals `model_saved` (role `revision`) before the next step, the working file named."""
    rig = make_rig(tmp_path)
    rig.host.script("save_n", saved(rig, "m1", 1), saved(rig, "m1", 2, file="snapshot.edb"))

    async def body(ctx: Any) -> list[str]:
        first = await ctx.tool("save_n", {"model": "m1"})
        second = await ctx.tool("save_n", {"model": "m1", "new": True})
        return [first.ref.ref, second.ref.ref]

    outcome = asyncio.run(rig.engine(wf(body)).start(request(mode=AUTO)))
    assert outcome.status is RunStatus.COMPLETED
    model_id = rig.host.models["m1"].model_id or ""
    made = [("m1", model_id, n, f"fp{n}", ZERO, "m1.edb", "revision") for n in (1, 2)]  # never the snapshot's name
    got = [(s.model_key, s.model_id, s.revision, s.fingerprint, s.file_sha256, s.file_name, s.role)
           for _, s in revisions(rig, outcome.run_id)]  # fmt: skip
    assert got == made
    assert [path for path, _ in revisions(rig, outcome.run_id)] == ["0", "1"]
    kinds = order(rig, outcome.run_id)
    assert kinds.index((T.STEP_COMPLETED, "0")) < kinds.index((T.MODEL_SAVED, "0")) < kinds.index((T.STEP_STARTED, "1"))


@pytest.mark.parametrize(
    ("args", "result"),
    [
        ({"model": "m1"}, {"host": False}),  # no provenance.host
        ({"model": "m1", "new": True}, {"file": "s.edb", "host": False}),
        ({"model": "m1", "new": True}, {}),  # a new-file save without saved_file
        ({"model": "m1", "new": True}, {"file": "s.edb", "sha": "1" * 64}),  # not a copy of the saved model
    ],
)
def test_tool_save_integrity_errors(tmp_path: Path, args: dict[str, JsonValue], result: dict[str, Any]) -> None:
    """EC2: a save with no host record, no `saved_file` or another hash is `ModelIntegrityError`; nothing journaled."""
    rig = make_rig(tmp_path)
    rig.host.script("save_n", saved(rig, "m1", 1, **result))
    caught: list[errors.ModelIntegrityError] = []

    async def body(ctx: Any) -> list[str]:
        try:
            await ctx.tool("save_n", args)
        except errors.ModelIntegrityError as exc:
            caught.append(exc)
        return []

    outcome = asyncio.run(rig.engine(wf(body)).start(request(mode=AUTO)))
    assert outcome.status is RunStatus.COMPLETED
    assert len(caught) == 1
    assert revisions(rig, outcome.run_id) == []


class _Cut(BaseException):
    """A process death between the start of a write and its end."""


def test_tool_save_without_its_model_saved_is_journaled_at_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EC2: a save completed whose `model_saved` was not written is appended after the host-state check, once."""
    rig = make_rig(tmp_path)
    rig.host.script("save_n", saved(rig, "m1", 1))
    read = rig.host.model_state
    broken = {"on": True}

    async def state(key: str, instance_id: str) -> Any:
        if broken["on"]:
            raise _Cut
        return await read(key, instance_id)

    monkeypatch.setattr(rig.host, "model_state", state)

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("save_n", {"model": "m1"})
        return [(await ctx.tool("read_a", {"n": 1})).ref.ref]

    engine = rig.engine(wf(body))
    with pytest.raises(_Cut):
        asyncio.run(engine.start(request(mode=AUTO)))
    (run_id,) = rig.run_ids()
    assert revisions(rig, run_id) == []  # stopped between the step and its save record
    broken["on"] = False
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED
    ((path, found),) = revisions(rig, run_id)
    assert (path, found.role, found.revision, found.fingerprint, found.file_name) == (
        "0",
        "revision",
        1,
        "fp1",
        "m1.edb",
    )
    kinds = order(rig, run_id)
    assert kinds.index((T.MODEL_SAVED, "0")) < kinds.index((T.STEP_STARTED, "1"))
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED
    assert len(revisions(rig, run_id)) == 1  # a completed run appends nothing again


def test_reconciled_tool_save_is_journaled_after_the_check(tmp_path: Path) -> None:
    """EC2: a save reconciled `applied` at a resume reads no state in reconciliation; the host-state check compares the
    live state with its result (a change while paused, or a snapshot whose hash is not the model's, is a mismatch) and,
    when it passes, `model_saved` is appended from the check's read before the block runs."""

    def resumed(name: str, state: dict[str, Any], snapshot: str) -> tuple[Rig, RunOutcome, list[str]]:
        rig = make_rig(tmp_path / name)

        async def body(ctx: Any) -> list[str]:
            await ctx.tool("write_b", {"n": 1, "model": "m1"})
            await ctx.tool("save_n", {"model": "m1", "new": True})
            return [(await ctx.tool("read_a", {"n": 2})).ref.ref]

        engine = rig.engine(wf(body))
        rig.host.script("save_n", Raise(_Cut()))
        with pytest.raises(_Cut):
            asyncio.run(engine.start(request(mode=COPY)))
        (run_id,) = rig.run_ids()
        (begun,) = [e.payload for e in rig.events(run_id) if e.path == "1" and isinstance(e.payload, ev.StepStarted)]
        copy = rig.host.models["m1.copy"]
        rig.host.reconciliations[begun.op_id or ""] = Reconciliation(
            outcome="applied", result=saved(rig, "m1.copy", 2, file="snapshot.edb", sha=snapshot)
        )
        rig.host.models["m1.copy"] = copy.model_copy(update={"revision": 2, "fingerprint": "fp2", **state})
        mark = len(rig.log)
        return rig, asyncio.run(engine.resume(run_id)), rig.log[mark:]

    rig, done, log = resumed("passes", {}, ZERO)
    assert log.index("tool.reconcile") < log.index("host.model_state")  # no state is read to reconcile
    assert done.status is RunStatus.COMPLETED
    found = [(p, s) for p, s in revisions(rig, done.run_id) if s.role == "revision"]
    assert [p for p, _ in found] == ["1"]
    made = found[0][1]
    assert (made.model_key, made.revision, made.fingerprint, made.file_name) == ("m1.copy", 2, "fp2", "m1.copy.edb")
    kinds = order(rig, done.run_id)
    assert kinds.index((T.MODEL_SAVED, "1")) < kinds.index((T.STEP_STARTED, "2"))
    for name, state, snapshot in (("edited", {"revision": 9}, ZERO), ("snapshot", {}, "1" * 64)):
        rig, done, _ = resumed(name, state, snapshot)  # a change while paused; a snapshot that is not the model's file
        assert (done.status, done.escalation and done.escalation.reason) == (
            RunStatus.NEEDS_ENGINEER,
            "host_state_mismatch",
        )
        assert [s for _, s in revisions(rig, done.run_id) if s.role == "revision"] == []


def test_mode_resolved_approval_not_always_ask(tmp_path: Path) -> None:
    """EC3: under a mode-resolved approval an always-ask step still asks; under an engineer's approval it does not."""
    for kind, asked in ((ApprovalKind.CHANGE_SET, True), (ApprovalKind.SIGN_OFF, False)):
        rig = make_rig(tmp_path / kind.value)
        rig.host.previews["delete_d"] = change_set(rig, "i1")

        async def body(ctx: Any, kind: ApprovalKind = kind, rig: Rig = rig) -> list[str]:
            approval = await ctx.approve("Plan", change_set(rig, "i1"), kind=kind)
            return [(await ctx.tool("delete_d", {"model": "m1"}, under=approval, item="i1")).ref.ref]

        engine = rig.engine(wf(body))
        outcome = asyncio.run(engine.start(request(mode=AUTO)))
        if kind is ApprovalKind.SIGN_OFF:  # an engineer's answer to the sign-off itself
            rig.approvals.script(outcome.pending[0], reply(rig))
            outcome = asyncio.run(engine.resume(outcome.run_id))
        elif asked:
            assert [e.tool for e in rig.host.ledger] == []  # the delete waits for the engine's own approval
            inserted = request_id(outcome.run_id, "1~pre.approve")
            assert (outcome.status, outcome.pending) == (RunStatus.PAUSED, (inserted,))
            assert [p.title for p in rig.approvals.presented] == ["Apply delete_d"]
            rig.approvals.script(inserted, reply(rig))
            outcome = asyncio.run(engine.resume(outcome.run_id))
        assert outcome.status is RunStatus.COMPLETED
        assert [e.tool for e in rig.host.ledger] == ["delete_d"]
        by = [e.payload.by for e in rig.events(outcome.run_id) if isinstance(e.payload, ev.ApprovalResolved)]
        assert by == (["mode:autonomous_logged", "engineer:ada"] if asked else ["engineer:ada"])
        (begun,) = [
            e.payload for e in rig.events(outcome.run_id) if e.path == "1" and isinstance(e.payload, ev.StepStarted)
        ]
        assert begun.under == request_id(outcome.run_id, "0")  # the step still runs under the approval it was given


def test_required_basis_from_fields() -> None:
    """EC4: `required_basis` is derived from `basis_fields`; a different or repeated declaration is `RegistryError`."""

    async def fn(ctx: object, inp: ChainInput) -> ChainOutput:
        return ChainOutput(refs=[])

    def spec(path: str, *, required: bool = True) -> FieldSpec:
        return FieldSpec(path=path, kind="quantity", label="A field", required=required, unit="1")

    first, second, third = (
        spec("limits.drift_ratio"),
        spec("limits.sway_ratio"),
        spec("limits.slack_ratio", required=False),
    )

    def make(**options: Any) -> WorkflowDef[ChainInput, ChainOutput]:
        return workflow(name="wf_fields", version=1, description="d", **options)(fn)

    derived = make(basis_fields=(first, third, second))
    assert (derived.required_basis, derived.basis_fields, derived.copy_on_open) == (
        ("limits.drift_ratio", "limits.sway_ratio"), (first, third, second), False,
    )  # fmt: skip
    reordered = make(basis_fields=(first, second), required_basis=("limits.sway_ratio", "limits.drift_ratio"))
    assert reordered.required_basis == ("limits.drift_ratio", "limits.sway_ratio")
    assert make(copy_on_open=True).copy_on_open is True
    plain, given = make(), make(required_basis=("a.b",))
    assert (plain.basis_fields, plain.required_basis, given.basis_fields, given.required_basis) == (
        (),
        (),
        (),
        ("a.b",),
    )
    for options, reason in (
        ({"basis_fields": (first, first)}, "field_invalid"),
        ({"basis_fields": (first, first), "required_basis": ("limits.drift_ratio",)}, "field_invalid"),
        ({"basis_fields": (first, second), "required_basis": ("limits.drift_ratio",)}, "declaration_mismatch"),
        (
            {"basis_fields": (first, third), "required_basis": ("limits.drift_ratio", "limits.slack_ratio")},
            "declaration_mismatch",
        ),
        (
            {"basis_fields": (first,), "required_basis": ("limits.drift_ratio", "limits.drift_ratio")},
            "declaration_mismatch",
        ),
    ):
        with pytest.raises(RegistryError, match=reason):
            make(**options)
    with pytest.raises(RegistryError) as refused:
        make(basis_fields=(first, second), required_basis=("limits.drift_ratio",))
    assert str(refused.value) == "wf_fields: declaration_mismatch at limits.sway_ratio"
    with pytest.raises(AttributeError, match="no attribute 'Nope'"):
        _ = eng_harness.block.Nope
    assert eng_harness.block.FieldSpec is eng_harness.basis.FieldSpec


def test_save_under_approval_keeps_chain(tmp_path: Path) -> None:
    """EC5: a save under an approval is re-checked; the next write finds the save's state; another change voids it."""

    def run(name: str, edit: Callable[[Rig], None] | None, when: str) -> tuple[Rig, list[str], RunOutcome]:
        rig = make_rig(tmp_path / name)
        rig.host.script("save_n", saved(rig, "m1", 1))
        voided: list[str] = []

        async def body(ctx: Any) -> list[str]:
            approval = await ctx.approve("Plan", change_set(rig, "i1"))
            steps = [("save_n", {"model": "m1"}), ("write_b", {"n": 1, "model": "m1"})]
            for number, (tool, args) in enumerate(steps):
                if edit is not None and when == ("before_save", "between")[number]:
                    edit(rig)
                try:
                    await ctx.tool(tool, args, under=approval, item="i1")
                except errors.ApprovalVoid as void:
                    voided.append(void.message)
            return []

        return rig, voided, drive(rig, wf(body), AUTO)

    def other_file(rig: Rig) -> None:
        rig.host.models["m1"] = rig.host.models["m1"].model_copy(update={"file_sha256": "f" * 64})

    def other_revision(rig: Rig) -> None:
        rig.host.models["m1"] = rig.host.models["m1"].model_copy(update={"revision": 5, "fingerprint": "fp5"})

    rig, voided, outcome = run("none", None, "")
    assert (outcome.status, voided, [e.tool for e in rig.host.ledger]) == (
        RunStatus.COMPLETED,
        [],
        ["save_n", "write_b"],
    )
    rig, voided, _ = run("file", other_file, "between")  # the file changed after the save: same revision, still void
    assert [e.tool for e in rig.host.ledger] == ["save_n"]
    assert len(voided) == 1
    rig, voided, _ = run("revision", other_revision, "before_save")  # changed before the save: void before the call
    assert [e.tool for e in rig.host.ledger] == []
    assert len(voided) == 2


def test_revision_save_no_write_preview(tmp_path: Path) -> None:
    """EC6: in `approve_each_write` a save to a new file that overwrites no original gets no preview; others do."""
    rig = make_rig(tmp_path)
    rig.host.script("save_n", saved(rig, "m1", 1, file="a.edb"), saved(rig, "m1", 2), saved(rig, "m1", 4, file="b.edb"))
    rig.host.script("write_b", saved(rig, "m1", 3))

    async def body(ctx: Any) -> list[str]:
        steps = [
            ("save_n", {"model": "m1", "new": True}),
            ("save_n", {"model": "m1"}),
            ("write_b", {"n": 1, "model": "m1"}),
        ]
        steps += [("save_n", {"model": "m1", "new": True, "target": "original"})]
        return [(await ctx.tool(name, args)).ref.ref for name, args in steps]

    outcome = drive(rig, wf(body), EACH)
    assert outcome.status is RunStatus.COMPLETED
    run_id = outcome.run_id
    asked = [request_id(run_id, f"{n}~pre.approve") for n in (1, 2, 3)]
    shown = list(dict.fromkeys(p.request_id for p in rig.approvals.presented))
    assert shown == asked  # the first save was not previewed
    assert [e.tool for e in rig.host.ledger] == ["save_n", "save_n", "write_b", "save_n"]
    assert len(revisions(rig, run_id)) == 3  # the three saves; write_b is no save


def test_basis_view_record_ref() -> None:
    """The basis record's reference, for a calc input `basis`: `res_<id>`, needing no declared path."""
    result_id = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    view = BasisView(result_id, DesignBasis(template=None, fields={}), ())
    assert view.record_ref().ref == result_id
    assert (
        BasisView(result_id, DesignBasis(template=None, fields={}), ("limits.drift_ratio",)).record_ref().ref
        == result_id
    )
    with pytest.raises(errors.BlockRuleViolation):
        view.ref("limits.drift_ratio")  # a field's value is still read only through a declared path


class ContentFree(ToolInfo):
    """A write `open` that guarantees unchanged model content without `path` (engine 4.8, B-562)."""

    def opens_model_without_writing(self, args: Mapping[str, JsonValue]) -> bool:
        """True without `path`."""
        return "path" not in args


def free_rig(root: Path) -> Rig:
    """The rig of this module with `open_w`, a write-classified open that may change no model content."""
    rig = make_rig(root)
    tool = ContentFree(name="open_w", effect="write", action="open", host_key="csi", model_param="model")
    rig.host._tools[tool.name] = tool
    return rig


def checked(rig: Rig, run_id: str) -> list[str]:
    """The paths of the `check_model` steps of the run, in order."""
    return [e.path or "" for e in rig.events(run_id) if isinstance(e.payload, ev.StepStarted) and e.payload.name
            == "check_model"]  # fmt: skip


def opened(rig: Rig, run_id: str, path: str) -> ev.StepStarted:
    """The latest `step_started` of the step at `path`."""
    found = [e.payload for e in rig.events(run_id) if e.path == path and isinstance(e.payload, ev.StepStarted)]
    return found[-1]


@pytest.mark.parametrize(
    ("first", "args", "dirty"),
    [
        (False, {"model": "m1"}, False),  # recorded true: no dirty mark, so no check
        (False, {"model": "m1", "path": "x"}, True),  # no guarantee: an ordinary write
        (True, {"model": "m1"}, True),  # an earlier write's flag stays set
    ],
)
def test_content_free_open_skips_only_its_own_dirty_mark(
    tmp_path: Path, first: bool, args: dict[str, JsonValue], dirty: bool
) -> None:
    """Invariant 1 (B-562): an open recorded as changing no content leaves the dirty flag as it was; the replay after a
    process death reads the recorded value."""
    rig = free_rig(tmp_path)
    rig.host.script("read_a", Raise(_Cut()))  # the process dies after the open: the resume replays it

    async def body(ctx: Any) -> list[str]:
        if first:
            await ctx.tool("write_b", {"n": 1, "model": "m1"})
        await ctx.tool("open_w", args)
        return [(await ctx.tool("read_a", {"n": 2})).ref.ref]

    engine = rig.engine(wf(body))
    with pytest.raises(_Cut):
        asyncio.run(engine.start(request(mode=AUTO)))
    (run_id,) = rig.run_ids()
    began = opened(rig, run_id, "1" if first else "0")
    assert (began.effect, began.action) == ("write", "open")  # the write effect is kept
    assert began.opens_model_without_writing is (None if "path" in args else True)
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED
    assert checked(rig, run_id) == (["~end.check_model.m1"] if dirty else [])


def _applied(rig: Rig) -> Callable[..., Any]:
    """A reconciler that reports every write `applied` with a stored result (the call itself raised)."""

    async def reconcile(tool: str, args: Mapping[str, JsonValue], op_id: str) -> Reconciliation:
        return Reconciliation(outcome="applied", result=saved(rig, "m1", 0))

    return reconcile


def test_immediately_applied_open_binds_and_copies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """EC1 (B-562): an open confirmed `applied` during its call binds the model, reads its units and takes the copy,
    as a successful call does, before the next step on the model; it marks nothing dirty."""
    rig = free_rig(tmp_path)
    rig.host.script("open_w", Raise(RuntimeError("the call raised")))
    monkeypatch.setattr(rig.host, "reconcile", _applied(rig))

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("open_w", {"model": "m1"})
        return [(await ctx.tool("read_m", {"model": "m1"})).ref.ref]

    outcome = asyncio.run(rig.engine(wf(body, copy_on_open=True)).start(request(mode=AUTO)))
    assert outcome.status is RunStatus.COMPLETED
    run_id, events = outcome.run_id, rig.events(outcome.run_id)
    (reconciled,) = [e.seq for e in events if e.path == "0" and isinstance(e.payload, ev.StepReconciled)]
    (bound,) = [e.seq for e in events if isinstance(e.payload, ev.ModelBound) and e.payload.model_key == "m1"]
    (units,) = [e.seq for e in events if e.path == "0~post.units.m1" and isinstance(e.payload, ev.StepCompleted)]
    (copy,) = [e.seq for e in events if e.path == "0~post.working_copy.m1" and isinstance(e.payload, ev.ModelSaved)]
    (read,) = [e.seq for e in events if e.path == "1" and isinstance(e.payload, ev.StepStarted)]
    assert reconciled < bound < units < copy < read
    assert [(e.tool, e.model) for e in rig.host.ledger] == [("open_w", "m1"), ("read_m", "m1.copy")]
    assert checked(rig, run_id) == []  # the applied open marked no model dirty


def test_replayed_open_binds_before_the_live_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """EC1 (B-562): a process that died after an open completed, before its binding, binds the model and reads its units
    at the replay, from the journaled host and action, before it takes the still-live copy; once recorded, the copy
    replays with no second binding or copy."""
    rig = free_rig(tmp_path)
    locate, cut = rig.host.locate, {"on": True}

    async def located(key: str) -> Any:
        if cut["on"]:
            raise _Cut
        return await locate(key)

    monkeypatch.setattr(rig.host, "locate", located)

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("open_w", {"model": "m1"})
        return [(await ctx.tool("read_m", {"model": "m1"})).ref.ref]

    engine = rig.engine(wf(body, copy_on_open=True))
    with pytest.raises(_Cut):
        asyncio.run(engine.start(request(mode=AUTO)))
    (run_id,) = rig.run_ids()
    assert not [e for e in rig.events(run_id) if isinstance(e.payload, ev.ModelBound)]
    cut["on"] = False
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED
    events = rig.events(run_id)
    bound = [e.seq for e in events if isinstance(e.payload, ev.ModelBound) and e.payload.model_key == "m1"]
    units = [e.seq for e in events if e.path == "0~post.units.m1" and isinstance(e.payload, ev.StepCompleted)]
    copy = [e.seq for e in events if e.path == "0~post.working_copy.m1" and isinstance(e.payload, ev.ModelSaved)]
    assert len(bound) == len(units) == len(copy) == 1
    assert bound[0] < units[0] < copy[0]
    assert checked(rig, run_id) == []
    mark = len(events)
    assert asyncio.run(rig.engine(wf(body, copy_on_open=True)).resume(run_id)).status is RunStatus.COMPLETED
    assert len(rig.events(run_id)) == mark  # the recorded copy replays: no second binding, units read or copy
    assert rig.log.count("host.working_copy") == 1
