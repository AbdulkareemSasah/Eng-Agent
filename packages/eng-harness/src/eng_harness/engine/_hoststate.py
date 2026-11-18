"""Instance binding, lost and reopened models, and the host-state check before live execution (spec 0001 4.5.4, 4.8).

Purpose: each model is bound to the host instance that holds it (`model_bound`); at a resume a model its bound instance
no longer has is found again (reopened) or lost (4.5.1 step 6), a lost or reopened model is never reconciled, and every
model the run wrote is compared with the journal (step 8): a difference stops the run with `engine.host_state`, whose
answer is `accept` (a new baseline), `restore` (the last save returns, the steps after it run again) or `abandon`.
Units: none. Errors: `Stopped` (see `_inflight`), `ContractError` from a failing port call.
"""

from typing import cast

from eng_contract.canonical import payload_sha256
from pydantic import JsonValue

from eng_harness.engine._inflight import Fold, Resume
from eng_harness.engine._inputs import Question
from eng_harness.engine._invariants import path_key
from eng_harness.engine._steps import inserted_path
from eng_harness.journal import EventType, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.ports import HostModelState, HostPort, SavedModel, UnitsState

_Obj = dict[str, JsonValue]


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
    draft decision B-427); a result without `provenance.host` leaves the save as the comparison. A new-file save's
    `saved_file.sha256` must also be the live file hash (spec 4.6 "Tool saves", EC2).
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
        (s.closed_at, s.closing.result) for s in f.content(key)
        if isinstance(s.closing, ev.StepCompleted | ev.StepReconciled) and s.closing.result and s.closed_at > since
    ]  # fmt: skip
    digest: JsonValue = None
    if results:
        latest = max(results, key=lambda r: r[0])[1]
        file = latest.summary.get("saved_file")
        digest = file.get("sha256") if isinstance(file, dict) else None
        if (info := rt.store.get(latest.ref).producer.host) is not None:
            want = (info.model_id, info.model_revision, None)
    found = (state.model_id, state.revision, state.fingerprint)
    if all(w in (None, n) for w, n in zip(want, found, strict=True)) and digest in (None, state.file_sha256):
        return None
    return "model_differs", f"{key} is at revision {state.revision} ({state.fingerprint}), the journal has {want[1]}"


async def check(rt: Resume) -> None:
    """Step 8 of a resume (4.5.4): compare each model the run wrote with the journal; on a difference ask the engineer.

    The state is read from the bound instance as `@resume<n>.model_state.<key>`; a model never bound is left alone.
    """
    for key in Fold(rt.events()).written():
        f = Fold(rt.events())  # an earlier model's answer may have added events
        if key not in f.bound or handed_off(f, key):
            continue
        state = await rt.host.model_state(key, f.bound[key].instance_id)
        rt.note("model_state", key, {"loaded": state.loaded, "revision": state.revision})
        if (found := _difference(rt, f, key, state)) is not None:
            await _resolve(rt, f, key, *found)
        else:
            await _revision(rt, f, key, state)


def handed_off(f: Fold, key: str) -> bool:
    """Whether the journal proves the EC1 handoff of the original `key` to its working copy (4.5.4, B-562).

    Its latest write is an open recorded as changing no model content that completed or was applied, every write on it
    is such an open, none was cut by a restore, and the open's `~post.working_copy` completed after the open's outcome
    with a distinct copy whose `model_saved` (role `working_copy`) lies within that step, before any later binding.
    """
    writes = sorted(f.writes(key, live=False), key=lambda s: s.seq)
    if not writes or f.content(key) or any(s.rerun is not None for s in writes):
        return False
    opened = writes[-1]
    copy = f.steps.get(inserted_path(opened.path, "post", "working_copy", path_key(key)))
    if copy is None or not isinstance(done := copy.closing, ev.StepCompleted) or done.result is None:
        return False
    if copy.rerun is not None or not opened.closed_at < copy.seq or f.bound_at.get(key, 0) > copy.seq:
        return False
    target = done.result.summary.get("copy")
    if done.result.summary.get("model") != key or not isinstance(target, str) or target == key:
        return False
    return any(p == copy.path and saved.model_key == target and copy.seq < seq < copy.closed_at
               for seq, p, saved in f.copies)  # fmt: skip


def _saved_paths(rt: Resume) -> set[str | None]:
    return {e.path for e in rt.events() if isinstance(e.payload, ev.ModelSaved)}


async def _revision(rt: Resume, f: Fold, key: str, state: HostModelState) -> None:
    """Step 8a of a resume (4.5.1): the latest write on `key` is a tool save, completed or reconciled `applied`, that
    has no `model_saved` (the process stopped between the two, or it was reconciled): append it, role `revision`, from
    the check's own read `state`. A result without `provenance.host`, or a new-file save without `saved_file`, gets none
    and raises nothing (spec 4.6 "Tool saves", EC2)."""
    last = max(f.content(key), key=lambda s: s.seq, default=None)  # a content-free open hides no save (B-562)
    if last is None or last.began.kind != "tool" or last.began.action not in ("save", "open"):
        return  # no port call for any other step: only a save, or an open that may save to a new file, is asked about
    done = last.closing.result if isinstance(last.closing, ev.StepCompleted | ev.StepReconciled) else None
    if done is None or any(e.path == last.path for e in rt.events() if isinstance(e.payload, ev.ModelSaved)):
        return
    info, args = await rt.tool.describe(last.began.name), last.began.args
    new = info.saves_new_file(
        args if args is not None else cast(_Obj, rt.store.payload(last.began.args_ref or "")["value"])
    )
    if not (info.action == "save" or new) or (new and not isinstance(done.summary.get("saved_file"), dict)):
        return
    if (host := rt.store.get(done.ref).producer.host) is None:
        return
    body = {"model_key": key, "model_id": host.model_id, "revision": host.model_revision, "role": "revision"}
    body |= state.model_dump(include={"fingerprint", "file_sha256"}) | {"file_name": rt.host.model_files(key)[0].name}
    rt.writer.append(EventType.MODEL_SAVED, body, path=last.path)


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
