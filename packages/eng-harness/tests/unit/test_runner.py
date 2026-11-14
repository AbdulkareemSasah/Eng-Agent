"""Engine start and resume: validation, the run header, the run class and the unreleased-tool record (plan 0001 T9b).

Covers spec 0001 AC16 (input and output validation), AC65 (run class) and AC68 (unreleased tools) at start and at
resume, the run header of section 4.4.2, the minimal `ctx.tool` and the settings of section 4.10. Fake ports and a real
SQLite journal in a temporary workspace (the rig of `tests/workflows/rig.py`); its call log shows which port calls an
engine made, and the fake host's ledger shows which calls reached the host. The replay tests are in `tests/replay/`.
"""

import asyncio
import re
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from eng_contract import CONTRACT_VERSION
from eng_contract.canonical import payload_sha256
from eng_contract.errors import ContractError, ErrorCode, ErrorDetail
from fakes.ports import failure
from pydantic import JsonValue, ValidationError
from workflows.chain import ChainInput, ChainOutput, bad_output, chain
from workflows.rig import BASIS_REF, make_rig, request, steps

from eng_harness import __version__
from eng_harness.block import workflow
from eng_harness.engine import EngineSettings, PermissionMode, RunRequest, RunStatus
from eng_harness.engine._steps import op_id
from eng_harness.errors import HarnessCode, RunRefused
from eng_harness.journal import EventType, JournalReader
from eng_harness.journal import _events as ev
from eng_harness.ports import RunClass, ServerCheck

T = EventType
RUN_ID = re.compile(r"^run_[0-7][0-9A-HJKMNP-TV-Z]{25}$")


@pytest.mark.parametrize(
    "bad", [{"count": "3"}, {"count": 1.5}, {"count": None}, {"label": 5}, {"count": float("nan")}]
)
def test_input_and_output_validation(tmp_path: Path, bad: dict[str, JsonValue]) -> None:
    rig = make_rig(tmp_path)
    engine = rig.engine(chain(steps("read_a")), bad_output)
    with pytest.raises(ContractError) as refused:  # the input is checked strictly: no string for an integer, no float
        asyncio.run(engine.start(request(values=bad)))
    assert refused.value.detail.code is ErrorCode.INVALID_ARGUMENT
    with pytest.raises(ContractError) as unknown:
        asyncio.run(engine.start(request("no_such_workflow")))
    assert unknown.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert rig.run_ids() == []  # no run folder
    assert rig.host.ledger == []  # and no tool was called
    outcome = asyncio.run(engine.start(request("bad_output", {"count": 1})))  # a valid input, a wrong return value
    assert outcome.status is RunStatus.NEEDS_ENGINEER
    assert outcome.output is None
    assert outcome.escalation is not None
    assert outcome.escalation.reason == "block_rule_violation"
    assert "ChainOutput" in outcome.escalation.detail
    assert "Impostor" in outcome.escalation.detail
    assert [e.type for e in rig.events(outcome.run_id)] == [T.RUN_STARTED, T.RUN_ESCALATED]  # and no output stored


def test_run_class_recorded_and_checked(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    workflow_def = chain(steps("read_a"))
    for asked, calc_class in ((RunClass.TRIAL, RunClass.PRODUCTION), (RunClass.PRODUCTION, RunClass.TRIAL)):
        with pytest.raises(RunRefused) as refused:
            asyncio.run(rig.engine(workflow_def, calc_class=calc_class).start(request(run_class=asked)))
        assert refused.value.code is HarnessCode.RUN_CLASS_MISMATCH
        assert asked.value in refused.value.message
        assert calc_class.value in refused.value.message
    assert rig.run_ids() == []  # no run folder
    assert rig.host.ledger == []
    for run_class in RunClass:
        outcome = asyncio.run(rig.engine(workflow_def, calc_class=run_class).start(request(run_class=run_class)))
        assert outcome.status is RunStatus.COMPLETED
        assert rig.header(outcome.run_id).run_class == run_class.value
        reader = JournalReader(rig.run_dir(outcome.run_id))
        assert reader.run().run_class == run_class.value  # the reader shows the recorded class
        reader.close()
    # a resume is refused the same way, before any other port call and before anything is journaled (4.5.1 step 3)
    for run_class in RunClass:
        other = RunClass.TRIAL if run_class is RunClass.PRODUCTION else RunClass.PRODUCTION
        rig.host.script("read_a", failure(ErrorCode.HOST_BUSY))
        stopped = asyncio.run(rig.engine(workflow_def, calc_class=run_class).start(request(run_class=run_class)))
        assert stopped.status is RunStatus.NEEDS_ENGINEER  # the run waits for the engineer: it can be resumed
        before, logged = rig.events(stopped.run_id), list(rig.log)
        with pytest.raises(RunRefused) as mismatch:
            asyncio.run(rig.engine(workflow_def, calc_class=other).resume(stopped.run_id))
        assert mismatch.value.code is HarnessCode.RUN_CLASS_MISMATCH
        assert (other.value in mismatch.value.message, run_class.value in mismatch.value.message) == (True, True)
        assert rig.log == logged
        assert rig.events(stopped.run_id) == before
        resumed = asyncio.run(rig.engine(workflow_def, calc_class=run_class).resume(stopped.run_id))
        assert resumed.status is RunStatus.COMPLETED  # the matching calc port resumes it


def test_unreleased_tools_recorded(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, {"write_b": "B-1", "read_c": "B-2"})
    outcome = asyncio.run(rig.engine(chain(steps("read_a"))).start(request()))
    assert rig.header(outcome.run_id).unreleased_tools == {"write_b": "B-1", "read_c": "B-2"}
    reader = JournalReader(rig.run_dir(outcome.run_id))
    assert dict(reader.run().unreleased_tools) == {"write_b": "B-1", "read_c": "B-2"}
    reader.close()
    released = make_rig(tmp_path / "released")  # no tool is unreleased: the record is empty
    done = asyncio.run(released.engine(chain(steps("read_a"))).start(request()))
    assert released.header(done.run_id).unreleased_tools == {}
    # at a resume the mapping is recorded in `run_resumed` only when it differs from the last recorded one (AC68)
    rig = make_rig(tmp_path / "resumed", {"write_b": "B-1"})
    rig.host.script("read_c", *[failure(ErrorCode.HOST_BUSY)] * 4)  # the run and three resumes stop at the second step
    engine = rig.engine(chain(steps("read_a", "read_c")))
    run_id = asyncio.run(engine.start(request())).run_id
    asyncio.run(engine.resume(run_id))  # the same mapping: nothing is recorded
    rig.host.unreleased = {"read_c": "B-2"}
    asyncio.run(engine.resume(run_id))  # another mapping: recorded
    asyncio.run(engine.resume(run_id))  # the same as the last recorded one (not as the union): nothing is recorded
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED
    resumes = [e.payload for e in rig.events(run_id) if isinstance(e.payload, ev.RunResumed)]
    assert [r.unreleased_tools for r in resumes] == [None, {"read_c": "B-2"}, None, None]
    reader = JournalReader(rig.run_dir(run_id))
    assert dict(reader.run().unreleased_tools) == {"write_b": "B-1", "read_c": "B-2"}  # the union over the whole run
    assert reader.run().run_class == "production"
    reader.close()


def test_start_journals_header_and_output(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    workflow_def = chain([("read_a", {"n": 0}), ("write_b", {"n": 1, "model": "m1"})], always_ask=("write_b",))
    settings = EngineSettings(step_retry_limit=3)
    given: dict[str, JsonValue] = {"label": "a", "count": 2}
    asked = request(values=given, mode=PermissionMode.AUTONOMOUS_LOGGED)
    outcome = asyncio.run(rig.engine(workflow_def, settings=settings).start(asked))
    run_id = outcome.run_id
    assert outcome.status is RunStatus.COMPLETED
    assert (outcome.pending, outcome.escalation) == ((), None)
    assert isinstance(outcome.output, ChainOutput)
    assert RUN_ID.fullmatch(run_id)
    assert rig.run_ids() == [run_id]
    assert {p.name for p in rig.run_dir(run_id).iterdir()} >= {"journal.sqlite", "run.lock"}
    events = rig.events(run_id)
    assert [e.type for e in events] == [
        T.RUN_STARTED,
        T.STEP_STARTED,
        T.STEP_COMPLETED,
        T.MODEL_BOUND,  # the first step addressed to m1: its binding, then its units, then the step itself
        T.STEP_STARTED,
        T.STEP_COMPLETED,
        T.CHECK_ENFORCED,
        T.STEP_STARTED,
        T.STEP_COMPLETED,
        T.STEP_STARTED,
        T.STEP_COMPLETED,
        T.CHECK_ENFORCED,
        T.RUN_COMPLETED,
    ]  # fmt: skip
    head = rig.header(run_id)
    assert (head.run_id, head.workflow) == (run_id, "chain")
    assert head.block == ev.BlockRef(name="chain", version="1", code_sha256=workflow_def.code_sha256)
    assert (head.mode, head.run_class, head.basis_ref) == ("autonomous_logged", "production", BASIS_REF)
    assert (head.engine_version, head.contract_version) == (__version__, CONTRACT_VERSION)
    assert head.settings_sha256 == payload_sha256(settings.model_dump(mode="json"))
    assert head.settings_sha256 != payload_sha256(EngineSettings().model_dump(mode="json"))
    assert (head.servers, head.always_ask, head.unreleased_tools, head.decision_runtime) == ([], ["write_b"], {}, {})
    assert rig.store.payload(head.input_ref) == {"value": given}  # the input is stored, not copied into the journal
    assert head.input_sha256 == payload_sha256(given)
    read, read_done, bind, units, _units_done, units_enforced = events[1:7]
    write, write_done, end_check, _end_check_done, enforced, done = events[7:]
    assert (read.path, read.attempt, write.path, write.attempt) == ("0", 1, "1", 1)
    assert bind.payload == ev.ModelBound(
        model_key="m1", host_key="csi", instance_id="rig-1", reason="first_use", file_names=["m1.edb"]
    )  # journaled before the first step addressed to m1, and its units are read before that step (spec 4.8, 4.6 #9)
    assert (units.path, units_enforced.path) == ("1~pre.units.m1", "1~pre.units.m1")
    assert units_enforced.payload == ev.CheckEnforced(invariant=9, model_key="m1", outcome="pass")
    started_read, started_write = read.payload, write.payload
    assert isinstance(started_read, ev.StepStarted)
    assert isinstance(started_write, ev.StepStarted)
    assert (started_read.kind, started_read.name, started_read.args, started_read.effect) == (
        "tool",
        "read_a",
        {"n": 0},
        "read",
    )
    assert started_read.args_sha256 == payload_sha256({"n": 0})
    assert (started_read.op_id, started_read.host_key, started_read.model_key) == (None, "csi", None)
    assert started_write.effect == "write"
    assert (started_write.op_id, started_write.model_key) == (op_id(run_id, "1", 1), "m1")
    assert isinstance(end_check.payload, ev.StepStarted)
    assert (end_check.path, end_check.attempt) == ("~end.check_model.m1", 1)
    assert (end_check.payload.kind, end_check.payload.name, end_check.payload.effect, end_check.payload.model_key) == (
        "read",
        "check_model",
        "read",
        "m1",
    )
    assert enforced.payload == ev.CheckEnforced(invariant=1, model_key="m1", outcome="pass")
    assert [(c.tool, c.op_id, c.model) for c in rig.host.ledger] == [
        ("read_a", op_id(run_id, "0", 1), None), ("write_b", op_id(run_id, "1", 1), "m1"),
    ]  # fmt: skip
    for closing, ref in ((read_done, outcome.output.refs[0]), (write_done, outcome.output.refs[1])):
        assert isinstance(closing.payload, ev.StepCompleted)
        assert closing.payload.result is not None
        assert closing.payload.result.ref == ref
        assert (closing.payload.result.warnings, closing.payload.result.complete) == ([], True)
        assert closing.payload.duration_ms >= 0
    assert isinstance(done.payload, ev.RunCompleted)
    stored = {"refs": outcome.output.refs}
    assert rig.store.payload(done.payload.output_ref) == {"value": stored}
    assert done.payload.output_sha256 == payload_sha256(stored)
    assert done.payload.draft is False
    for port in (rig.approvals, rig.inputs):  # task T9 presents no approval and no input request
        assert (port.presented, port.waits) == ([], [])


def test_a_failed_step_stops_the_run_for_the_engineer(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.host.script("read_c", failure(ErrorCode.NOT_FOUND, "no such object"))
    outcome = asyncio.run(rig.engine(chain(steps("read_a", "read_c", "read_a"))).start(request()))
    assert outcome.status is RunStatus.NEEDS_ENGINEER  # the failure leaves the block, so the run waits for the engineer
    assert outcome.output is None
    assert outcome.escalation is not None
    assert outcome.escalation.reason == "unhandled_error"
    assert outcome.escalation.detail == "no such object"
    assert [e.type for e in rig.events(outcome.run_id)] == [
        T.RUN_STARTED, T.STEP_STARTED, T.STEP_COMPLETED, T.STEP_STARTED, T.STEP_FAILED, T.RUN_ESCALATED,
    ]  # fmt: skip
    failed = rig.events(outcome.run_id)[4]
    assert (failed.path, failed.attempt) == ("1", 1)
    assert isinstance(failed.payload, ev.StepFailed)
    assert isinstance(failed.payload.error, ErrorDetail)
    assert failed.payload.error.code is ErrorCode.NOT_FOUND
    assert failed.payload.retryable is False
    assert [c.tool for c in rig.host.ledger] == ["read_a", "read_c"]  # the third step never ran


def test_request_defaults_and_validation() -> None:
    plain = RunRequest(workflow="chain", input={}, basis_ref=BASIS_REF)
    assert (plain.mode, plain.run_class) == (PermissionMode.WORK_ON_COPY, RunClass.PRODUCTION)
    with pytest.raises(ValidationError):
        RunRequest.model_validate({"workflow": "chain", "input": {}, "basis_ref": "not a ref"})
    with pytest.raises(ValidationError):
        RunRequest.model_validate({"workflow": "chain", "input": {}, "basis_ref": BASIS_REF, "extra": 1})
    with pytest.raises(ValidationError):
        plain.__setattr__("workflow", "other")  # the request is frozen


def test_settings_and_enums() -> None:
    settings = EngineSettings()
    assert (settings.max_parallel_children, settings.max_concurrent_hosts, settings.max_concurrent_decisions) == (
        8,
        1,
        4,
    )
    assert (settings.max_attempts_cap, settings.step_retry_limit) == (10, 2)
    for name in (
        "max_parallel_children",
        "max_concurrent_hosts",
        "max_concurrent_decisions",
        "max_attempts_cap",
        "step_retry_limit",
    ):
        with pytest.raises(ValidationError):
            EngineSettings.model_validate({name: 0})
    with pytest.raises(ValidationError):
        settings.__setattr__("max_attempts_cap", 3)  # the model is frozen
    assert {m.value for m in PermissionMode} == {"work_on_copy", "approve_each_write", "autonomous_logged"}
    assert {s.value for s in RunStatus} == {"COMPLETED", "PAUSED", "NEEDS_ENGINEER", "FAILED"}


@pytest.mark.parametrize("bad", ["", "run_x", "../x", "run_" + "0" * 26, "run_" + "0" * 26 + "/.."])
def test_resume_of_an_unknown_run(tmp_path: Path, bad: str) -> None:
    rig = make_rig(tmp_path)
    with pytest.raises(ContractError) as refused:
        asyncio.run(rig.engine(chain(steps("read_a"))).resume(bad))
    assert refused.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert rig.log == []


@workflow(name="checked", version=1, description="needs a server build", min_server_builds={"csi": "build-1"})
async def _checked(ctx: Any, inp: ChainInput) -> ChainOutput:
    return ChainOutput(refs=[(await ctx.tool("read_a", {"n": 0})).ref.ref])


def _meta_run_id(run_dir: Path) -> str:
    with sqlite3.connect(run_dir / "journal.sqlite") as db:
        return str(db.execute("SELECT value FROM meta WHERE key = 'run_id'").fetchone()[0])


def _tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def test_caller_chosen_run_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path)
    twin = make_rig(tmp_path / "twin")  # the same seed: the first id its source draws is the first one the rig draws
    drawn = f"run_{twin.ids.new_ulid()}"
    chosen = f"run_{twin.ids.new_ulid()}"
    assert chosen != drawn
    engine = rig.engine(_checked)

    # the server checks of invariant 8 write under the run folder before the engine creates it
    async def preflight(min_builds: Mapping[str, str]) -> list[ServerCheck]:
        (rig.run_dir(chosen) / "servers").mkdir(parents=True)
        return [
            ServerCheck(
                server="csi",
                build="build-1",
                min_build="build-1",
                fingerprint="f",
                expected_fingerprint="f",
                ok=True,
                reason=None,
            )
        ]

    monkeypatch.setattr(rig.host, "preflight", preflight)
    outcome = asyncio.run(engine.start(request("checked").model_copy(update={"run_id": chosen})))
    assert (outcome.status, outcome.run_id) == (RunStatus.COMPLETED, chosen)
    assert rig.run_ids() == [chosen]
    assert (rig.run_dir(chosen) / "servers").is_dir()  # what the server checks wrote stays
    assert rig.header(chosen).run_id == chosen
    assert _meta_run_id(rig.run_dir(chosen)) == chosen
    assert "host.preflight" in rig.log
    assert [c.tool for c in rig.host.ledger] == ["read_a"]
    assert [c.op_id for c in rig.host.ledger] == [op_id(chosen, "0", 1)]
    # a run folder that exists, and a malformed id, are refused before any port call and nothing is created
    log, before = list(rig.log), _tree(rig.workspace.root)
    for bad in (chosen, "../x", "run_x", "", "run_" + "0" * 26 + "/..", "run_" + "8" * 26, "run_" + "0" * 26 + "\n"):
        with pytest.raises(ContractError) as refused:
            asyncio.run(engine.start(request("checked").model_copy(update={"run_id": bad})))
        assert refused.value.detail.code is ErrorCode.INVALID_ARGUMENT
        assert refused.value.detail.received == bad
        assert rig.log == log
        assert _tree(rig.workspace.root) == before
    assert rig.run_ids() == [chosen]
    # no run id: the engine draws one from its id source
    fresh = make_rig(tmp_path / "fresh")
    plain = asyncio.run(fresh.engine(chain(steps("read_a"))).start(request()))
    assert plain.run_id == drawn
    assert RUN_ID.fullmatch(plain.run_id)
    assert request().run_id is None
    assert fresh.run_ids() == [drawn]
