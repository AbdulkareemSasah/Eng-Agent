"""Instance binding, lost and reopened models, and the host-state check before live execution (spec 0001 4.5.4, 4.8).

Purpose: each model is bound to the host instance that holds it (`model_bound`); at a resume a model its bound instance
no longer has is found again (reopened) or lost (4.5.1 step 6), a lost or reopened model is never reconciled, and every
model the run wrote is compared with the journal (step 8): a difference stops the run with `engine.host_state`, whose
answer is `accept` (a new baseline), `restore` (the last saved copy returns and the steps after it run again as new
attempts) or `abandon`. Units: none. Errors: `Stopped` (see `_inflight`), `ContractError` from a failing port call.
"""

from collections.abc import Mapping, Sequence

from eng_contract.canonical import payload_sha256
from eng_contract.envelope import Envelope
from pydantic import JsonValue

from eng_harness.engine._inflight import Fold, Resume
from eng_harness.engine._inputs import Question
from eng_harness.journal import Event, EventType, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.ports import HostModelState, HostPort, Reconciliation, SavedModel, ToolInfo, ToolPort, UnitsState

_Obj = Mapping[str, JsonValue]


def bind(writer: JournalWriter, host: HostPort, key: str, host_key: str, instance_id: str, reason: str) -> None:
    """Journal `model_bound`: the model `key` is held by the instance `instance_id` (4.8)."""
    names = [path.name for path in host.model_files(key)]
    body = {"model_key": key, "host_key": host_key, "instance_id": instance_id, "reason": reason, "file_names": names}
    writer.append(EventType.MODEL_BOUND, body)


class BindingTools:
    """A `ToolPort` that binds a model before the first call addressed to it, to the instance `locate` finds (4.8).

    The binding is journaled between the step's `step_started` and its host call (the seam before `step_started` is in
    the ctx). A model no instance holds yet is not bound: an `open` tool has not run, and the model is bound at the
    first call after it.
    """

    def __init__(self, tools: ToolPort, host: HostPort, writer: JournalWriter, events: Sequence[Event]) -> None:
        """Wrap `tools`; the models the journal binds already are not bound again."""
        self._tools, self._host, self._writer = tools, host, writer
        self._bound = {e.payload.model_key for e in events if isinstance(e.payload, ev.ModelBound)}
        self._info: dict[str, ToolInfo] = {}

    async def describe(self, tool: str) -> ToolInfo:
        """The tool's info, kept for the binding of the call that follows."""
        self._info[tool] = await self._tools.describe(tool)
        return self._info[tool]

    def unreleased_tools(self) -> Mapping[str, str]:
        """As the wrapped port."""
        return self._tools.unreleased_tools()

    async def call(self, tool: str, args: _Obj, *, op_id: str, model: str | None) -> Envelope:
        """Bind `model` first when no instance is bound to it; then call the wrapped port."""
        if model is not None and model not in self._bound and (found := await self._host.locate(model)) is not None:
            info = self._info.get(tool) or await self.describe(tool)
            bind(self._writer, self._host, model, info.host_key, found.instance_id, "first_use")
            self._bound.add(model)
        return await self._tools.call(tool, args, op_id=op_id, model=model)

    def supports_reconcile(self, tool: str) -> bool:
        """As the wrapped port."""
        return self._tools.supports_reconcile(tool)

    async def reconcile(self, tool: str, args: _Obj, op_id: str) -> Reconciliation:
        """As the wrapped port."""
        return await self._tools.reconcile(tool, args, op_id)

    async def read_back(self, tool: str, args: _Obj) -> Envelope | None:
        """As the wrapped port."""
        return await self._tools.read_back(tool, args)


async def _units(rt: Resume, kind: str, key: str, instance_id: str, *, must_load: bool = False) -> UnitsState:
    """Read the units of `key` in `instance_id` as `@resume<n>.<kind>.<key>`; differing units stop the run (4.6 #9)."""
    units = await rt.host.read_units(key, instance_id)
    rt.note(kind, key, {"loaded": units.loaded, "ok": units.ok, "instance_id": instance_id})
    if not units.ok or (must_load and not units.loaded):
        rt.stop("units_mismatch", f"the units of {key} are {units.present or 'not loaded'}, not {units.expected}")
    return units


async def locate_models(rt: Resume) -> set[str]:
    """Step 6 of a resume (4.5.1): read the units of each model the run wrote in its bound instance.

    A model that instance does not have is bound again when another instance holds it (reopened, units read there) and
    is lost when none does. Returns the models not to reconcile: the lost ones, and the reopened ones whose reopened
    file lacks writes (a reconciler could report `not_applied` for an edit that is only gone from memory).
    """
    f, lost = Fold(rt.events()), set[str]()
    for key in (k for k in f.written() if k in f.bound):
        if (await _units(rt, "units", key, f.bound[key].instance_id)).loaded:
            continue
        if (found := await rt.host.locate(key)) is None:
            lost.add(key)
            continue
        bind(rt.writer, rt.host, key, f.bound[key].host_key, found.instance_id, "reopened")
        await _units(rt, "units_reopened", key, found.instance_id, must_load=True)
    f = Fold(rt.events())
    return lost | {key for key in f.written() if f.lacking(key)}


def _reconciled(f: Fold, key: str, after: int) -> list[tuple[int, str]]:
    """(closing seq, result ref) of the writes on `key` reconciled `applied` after sequence `after`."""
    return [
        (s.closed_at, s.closing.result.ref) for s in f.steps.values()
        if isinstance(s.closing, ev.StepReconciled) and s.closing.outcome == "applied" and s.closing.result
        and s.began.model_key == key and s.closed_at > after
    ]  # fmt: skip


def _difference(rt: Resume, f: Fold, key: str, state: HostModelState) -> tuple[str, str] | None:
    """Why the host's state of `key` is not the journal's (reason, detail), or None when they agree (4.5.4)."""
    if not state.loaded:
        return "model_not_loaded", f"{key} is not loaded in its host"
    if lost := f.lacking(key):
        return (
            "model_reopened",
            f"{key} was reopened from its last save, which lacks {len(lost)} write(s) made after it",
        )
    if key not in f.saved:
        return None  # nothing was saved: there is no state to compare with
    seq, saved = f.saved[key]
    want: tuple[str | None, int | None, str | None] = (saved.model_id, saved.revision, saved.fingerprint)
    since = max(seq, f.bound_at[key] if f.bound[key].reason == "reopened" else 0)  # a reopened file starts at its save
    if refs := _reconciled(f, key, since):  # a write reconciled `applied` after that: the host holds its result
        info = rt.store.get(max(refs)[1]).producer.host
        want = (info.model_id, info.model_revision, None) if info else (None, None, None)
    found = (state.model_id, state.revision, state.fingerprint)
    if want[0] is not None and all(w in (None, n) for w, n in zip(want, found, strict=True)):
        return None
    return "model_differs", f"{key} is at revision {state.revision} ({state.fingerprint}), the journal has {want[1]}"


async def check(rt: Resume) -> None:
    """Step 8 of a resume (4.5.4): compare each model the run wrote with the journal; on a difference ask the engineer.

    The state is read from the bound instance as `@resume<n>.model_state.<key>`. A model without a binding was never
    reached by a call that names it and is left alone.
    """
    for key in Fold(rt.events()).written():
        f = Fold(rt.events())  # an earlier model's answer may have added events
        if key not in f.bound:
            continue
        state = await rt.host.model_state(key, f.bound[key].instance_id)
        rt.note(
            "model_state",
            key,
            {"loaded": state.loaded, "revision": state.revision, "instance_id": f.bound[key].instance_id},
        )
        if (found := _difference(rt, f, key, state)) is not None:
            await _resolve(rt, f, key, *found)


async def _resolve(rt: Resume, f: Fold, key: str, reason: str, detail: str) -> None:
    """Ask the engineer what to do with the model `key` (`accept` only if it differs; `restore` only if it is safe)."""
    seq = f.saved[key][0] if key in f.saved else 0
    restorable = key in f.saved and not any(s.seq > seq and s.began.model_key != key for s in f.writes())
    offered = [o for o, ok in (("accept", reason == "model_differs"), ("restore", restorable), ("abandon", True)) if ok]
    question = Question(name="state", prompt="What to do with the model", options=tuple(offered))
    rid = "hst_" + payload_sha256([rt.run_id, key, seq, reason])[:32]
    choice, _ = await rt.ask(
        "engine.host_state", rid, f"A model changed while the run was stopped ({key})", question, detail
    )
    if choice == "accept":  # the differences are the engineer's: the model as it is becomes the baseline
        saved = await rt.host.save(key, "baseline")
        rt.writer.append(EventType.MODEL_SAVED, {"model_key": key, **saved.model_dump(mode="json"), "role": "baseline"})
        return
    await _restore(rt, f, key, seq)


async def _restore(rt: Resume, f: Fold, key: str, seq: int) -> None:
    """Restore the last save of `key` (journaled at `seq`); the steps after it run again as new attempts."""
    was, old = f.saved[key][1], f.bound[key]
    kept = was.model_dump(include={"model_id", "revision", "fingerprint", "file_sha256", "file_name"})
    instance = await rt.host.restore(key, SavedModel.model_validate(kept))
    if instance.instance_id != old.instance_id:  # an instance the server started for the restore
        rt.writer.append(EventType.HOST_STARTED, {"host_key": old.host_key, **instance.model_dump(mode="json")})
    bind(rt.writer, rt.host, key, old.host_key, instance.instance_id, "restored")
    # a second `run_resumed` with this resume's number cuts the steps after the save (the first came before the check)
    cut = {"resume_no": rt.number, "code_hash_changed": False, "servers": [], "restored_to_seq": seq}
    rt.writer.append(EventType.RUN_RESUMED, cut)
    await _units(rt, "units_restored", key, instance.instance_id, must_load=True)
    for step in f.pending():  # a write in flight after the save is never reconciled against the restored model
        if step.seq > seq and step.began.model_key == key:
            rt.writer.append(EventType.STEP_RERUN, {"reason": "restored"}, path=step.path, attempt=step.attempt)
