"""Instance binding, lost and reopened models, and the host-state check before live execution (spec 0001 4.5.4, 4.8).

Purpose: each model is bound to the host instance that holds it (`model_bound`); at a resume a model its bound instance
no longer has is found again (reopened) or lost (4.5.1 step 6), a lost or reopened model is never reconciled, and every
model the run wrote is compared with the journal (step 8): a difference stops the run with `engine.host_state`, whose
answer is `accept` (a new baseline), `restore` (the last save returns, the steps after it run again) or `abandon`.
Units: none. Errors: `Stopped` (see `_inflight`), `ContractError` from a failing port call.
"""

from eng_contract.canonical import payload_sha256

from eng_harness.engine._inflight import Fold, Resume
from eng_harness.engine._inputs import Question
from eng_harness.journal import EventType, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.ports import HostModelState, HostPort, SavedModel, UnitsState


def bind(writer: JournalWriter, host: HostPort, key: str, host_key: str, instance_id: str, reason: str) -> None:
    """Journal `model_bound`: the model `key` is held by the instance `instance_id` (4.8)."""
    names = [path.name for path in host.model_files(key)]
    body = {"model_key": key, "host_key": host_key, "instance_id": instance_id, "reason": reason, "file_names": names}
    writer.append(EventType.MODEL_BOUND, body)


async def _units(rt: Resume, kind: str, key: str, instance_id: str, *, must_load: bool = False) -> UnitsState:
    """Read the units of `key` in `instance_id` as `@resume<n>.<kind>.<key>`; differing units stop the run (4.6 #9)."""
    units = await rt.host.read_units(key, instance_id)
    rt.note(kind, key, {"loaded": units.loaded, "ok": units.ok, "instance_id": instance_id})
    if not units.ok or (must_load and not units.loaded):
        rt.stop(f"the units of {key} are {units.present or 'not loaded'}, not {units.expected}", None, "units_mismatch")
    return units


async def locate_models(rt: Resume) -> set[str]:
    """Step 6 of a resume (4.5.1): read the units of each model the journal addressed in its bound instance.

    A model that instance lacks is bound again when another instance holds it (reopened) and is lost when none does.
    Returns the models not to reconcile: the lost ones, and the reopened ones whose file lacks writes (a reconciler
    could report `not_applied` for an edit that is only gone from memory).
    """
    f, lost = Fold(rt.events()), set[str]()
    for key in sorted({s.began.model_key for s in f.steps.values() if s.began.model_key in f.bound}):
        if (await _units(rt, "units", key, f.bound[key].instance_id)).loaded:
            continue
        if (found := await rt.host.locate(key)) is None:
            lost.add(key)
            continue
        bind(rt.writer, rt.host, key, f.bound[key].host_key, found.instance_id, "reopened")
        await _units(rt, "units_reopened", key, found.instance_id, must_load=True)
    f = Fold(rt.events())
    return lost | {key for key in f.written() if f.lacking(key)}


def _difference(rt: Resume, f: Fold, key: str, state: HostModelState) -> tuple[str, str] | None:
    """Why the host's state of `key` is not the journal's (reason, detail), or None when they agree (4.5.4).

    The state is compared with the last `model_saved`, or, when a write completed or was reconciled `applied` after
    it, with the identity and revision of the latest such result's `provenance.host` (`HostInfo` has no fingerprint;
    draft decision B-427); a result without `provenance.host` leaves the save as the comparison.
    """
    if not state.loaded:
        return "model_not_loaded", f"{key} is not loaded in its host"
    if lost := f.lacking(key):
        return "model_reopened", f"{key} was reopened from its last save, which lacks {len(lost)} write(s) after it"
    if key not in f.saved:
        return None  # nothing was saved: there is no state to compare with
    seq, saved = f.saved[key]
    want: tuple[str | None, int | None, str | None] = (saved.model_id, saved.revision, saved.fingerprint)
    since = max(seq, f.bound_at[key] if f.bound[key].reason == "reopened" else 0)  # a reopened file starts at its save
    results = [
        (s.closed_at, s.closing.result.ref) for s in f.writes(key)
        if isinstance(s.closing, ev.StepCompleted | ev.StepReconciled) and s.closing.result and s.closed_at > since
    ]  # fmt: skip
    if results and (info := rt.store.get(max(results)[1]).producer.host) is not None:
        want = (info.model_id, info.model_revision, None)
    found = (state.model_id, state.revision, state.fingerprint)
    if all(w in (None, n) for w, n in zip(want, found, strict=True)):
        return None
    return "model_differs", f"{key} is at revision {state.revision} ({state.fingerprint}), the journal has {want[1]}"


async def check(rt: Resume) -> None:
    """Step 8 of a resume (4.5.4): compare each model the run wrote with the journal; on a difference ask the engineer.

    The state is read from the bound instance as `@resume<n>.model_state.<key>`; a model never bound is left alone.
    """
    for key in Fold(rt.events()).written():
        f = Fold(rt.events())  # an earlier model's answer may have added events
        if key not in f.bound:
            continue
        state = await rt.host.model_state(key, f.bound[key].instance_id)
        rt.note("model_state", key, {"loaded": state.loaded, "revision": state.revision})
        if (found := _difference(rt, f, key, state)) is not None:
            await _resolve(rt, f, key, *found)


async def _resolve(rt: Resume, f: Fold, key: str, reason: str, detail: str) -> None:
    """Ask the engineer what to do with the model `key` (`accept` only if it differs; `restore` only if it is safe).

    The request id names the last save and the binding: an open request keeps its id at every resume, and a mismatch
    after an accept or a restore is a new request.
    """
    seq = f.saved[key][0] if key in f.saved else 0
    restorable = key in f.saved and not any(s.seq > seq and s.began.model_key != key for s in f.writes())
    offered = [o for o, ok in (("accept", reason == "model_differs"), ("restore", restorable), ("abandon", True)) if ok]
    question = Question(name="state", prompt="What to do with the model", options=tuple(offered))
    rid = "hst_" + payload_sha256([rt.run_id, key, seq, reason, f.bound_at[key]])[:32]
    title = f"A model changed while the run was stopped ({key})"
    if (await rt.ask(rid, title, question, detail, "engine.host_state"))[0] == "accept":
        saved = await rt.host.save(key, "baseline")  # the engineer's changes become the baseline
        rt.writer.append(EventType.MODEL_SAVED, {"model_key": key, **saved.model_dump(mode="json"), "role": "baseline"})
        return
    await _restore(rt, f, key, seq)


async def _restore(rt: Resume, f: Fold, key: str, seq: int) -> None:
    """Restore the last save of `key` (journaled at `seq`); the steps after it run again as new attempts.

    The cut is journaled first: a process that dies after the host restored the model finds the steps after the save
    undone whatever else was journaled, so none is reconciled against or compared with the restored model (4.5.4).
    """
    was, old = f.saved[key][1], f.bound[key]
    kept = was.model_dump(include={"model_id", "revision", "fingerprint", "file_sha256", "file_name"})
    instance = await rt.host.restore(key, SavedModel.model_validate(kept))
    # a second `run_resumed` with this resume's number cuts the steps after the save (the first came before the check)
    cut = {"resume_no": rt.number, "code_hash_changed": False, "servers": [], "restored_to_seq": seq}
    rt.writer.append(EventType.RUN_RESUMED, cut)
    if instance.instance_id != old.instance_id:  # an instance the server started for the restore
        rt.writer.append(EventType.HOST_STARTED, {"host_key": old.host_key, **instance.model_dump(mode="json")})
    bind(rt.writer, rt.host, key, old.host_key, instance.instance_id, "restored")
    await _units(rt, "units_restored", key, instance.instance_id, must_load=True)
    for step in f.pending():  # a write in flight after the save is never reconciled against the restored model
        if step.seq > seq and step.began.model_key == key:
            rt.writer.append(EventType.STEP_RERUN, {"reason": "restored"}, path=step.path, attempt=step.attempt)
