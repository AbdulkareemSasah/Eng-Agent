"""Engine start: validation, the run header, the run class and the unreleased-tool record (plan 0001 T9).

Covers spec 0001 AC16 (input and output validation), AC65 (run class), AC68 (unreleased tools), the run header of
section 4.4.2 and the settings of section 4.10. Fake ports and a real SQLite journal in a temporary workspace; the
fake host's ledger shows which calls reached it.
"""

import asyncio
from pathlib import Path

import pytest
from eng_contract import CONTRACT_VERSION
from eng_contract.canonical import payload_sha256
from eng_contract.errors import ContractError, ErrorCode
from fakes.ports import failure
from pydantic import JsonValue, ValidationError
from workflows.chain import ChainOutput, bad_output, chain
from workflows.rig import BASIS_REF, make_rig, request, steps

from eng_harness import __version__
from eng_harness.engine import EngineSettings, PermissionMode, RunStatus
from eng_harness.engine._steps import op_id
from eng_harness.errors import HarnessCode, RunRefused
from eng_harness.journal import EventType, JournalReader
from eng_harness.journal import _events as ev
from eng_harness.ports import RunClass

T = EventType


def test_input_and_output_validation(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    engine = rig.engine(chain(steps("read_a")), bad_output)
    for bad in ({"count": "3"}, {"count": 1.5}):  # a string and a float for an integer: the input is checked strictly
        with pytest.raises(ContractError) as refused:
            asyncio.run(engine.start(request(values=bad)))
        assert refused.value.detail.code is ErrorCode.INVALID_ARGUMENT
    with pytest.raises(ContractError) as unknown:
        asyncio.run(engine.start(request("no_such_workflow")))
    assert unknown.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert rig.run_ids() == []  # no run folder
    assert rig.log == []  # and no port was called
    outcome = asyncio.run(engine.start(request("bad_output", {"count": 1})))
    assert outcome.status is RunStatus.NEEDS_ENGINEER
    assert outcome.output is None
    assert outcome.escalation is not None
    assert outcome.escalation.reason == "block_rule_violation"
    assert "ChainOutput" in outcome.escalation.detail
    assert rig.types(outcome.run_id) == [T.RUN_STARTED, T.RUN_ESCALATED]


def test_run_class_recorded_and_checked(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)  # the calc port of the default engine is a production one
    workflow = chain(steps("read_a", "read_c"))
    rig.host.script("read_c", failure(ErrorCode.HOST_BUSY))  # the first run stops here and can be resumed
    with pytest.raises(RunRefused) as refused:
        asyncio.run(rig.engine(workflow).start(request(run_class=RunClass.TRIAL)))
    assert refused.value.code is HarnessCode.RUN_CLASS_MISMATCH
    assert rig.run_ids() == []
    assert rig.log == []
    trial = rig.engine(workflow, calc_class=RunClass.TRIAL)
    first = asyncio.run(trial.start(request(run_class=RunClass.TRIAL)))
    assert first.status is RunStatus.NEEDS_ENGINEER
    head = rig.events(first.run_id)[0].payload
    assert isinstance(head, ev.RunHeader)
    assert head.run_class == "trial"
    before, logged = rig.events(first.run_id), list(rig.log)
    with pytest.raises(RunRefused) as mismatch:
        asyncio.run(rig.engine(workflow).resume(first.run_id))  # a production calc port
    assert mismatch.value.code is HarnessCode.RUN_CLASS_MISMATCH
    assert rig.log == logged  # refused before any other port call
    assert rig.events(first.run_id) == before  # and before anything was journaled
    assert asyncio.run(trial.resume(first.run_id)).status is RunStatus.COMPLETED


def test_unreleased_tools_recorded(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.host.unreleased = {"write_b": "B-1"}
    rig.host.script("read_c", *[failure(ErrorCode.HOST_BUSY)] * 4)  # the run and three resumes stop at the second step
    engine = rig.engine(chain(steps("read_a", "read_c")))
    run_id = asyncio.run(engine.start(request())).run_id
    head = rig.events(run_id)[0].payload
    assert isinstance(head, ev.RunHeader)
    assert head.unreleased_tools == {"write_b": "B-1"}
    asyncio.run(engine.resume(run_id))  # the same mapping: nothing is recorded
    rig.host.unreleased = {"read_c": "B-2"}
    asyncio.run(engine.resume(run_id))  # another mapping: recorded
    asyncio.run(engine.resume(run_id))  # the same as the last recorded one (not as the union): nothing is recorded
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED
    resumed = [e.payload for e in rig.events(run_id) if isinstance(e.payload, ev.RunResumed)]
    assert [r.unreleased_tools for r in resumed] == [None, {"read_c": "B-2"}, None, None]
    reader = JournalReader(rig.run_dir(run_id))
    assert dict(reader.run().unreleased_tools) == {"write_b": "B-1", "read_c": "B-2"}  # the union (AC68)
    assert reader.run().run_class == "production"
    reader.close()


def test_start_journals_header_and_output(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    workflow = chain([("read_a", {"n": 0}), ("write_b", {"n": 1, "model": "m1"})])
    given: dict[str, JsonValue] = {"label": "a", "count": 2}
    outcome = asyncio.run(rig.engine(workflow).start(request(values=given, mode=PermissionMode.AUTONOMOUS_LOGGED)))
    run_id = outcome.run_id
    assert outcome.status is RunStatus.COMPLETED
    assert (outcome.pending, outcome.escalation) == ((), None)
    assert isinstance(outcome.output, ChainOutput)
    assert run_id.startswith("run_")
    events = rig.events(run_id)
    assert [e.type for e in events] == [
        T.RUN_STARTED, T.STEP_STARTED, T.STEP_COMPLETED, T.STEP_STARTED, T.STEP_COMPLETED, T.RUN_COMPLETED,
    ]  # fmt: skip
    head = events[0].payload
    assert isinstance(head, ev.RunHeader)
    assert (head.run_id, head.workflow) == (run_id, "chain")
    assert head.block == ev.BlockRef(name="chain", version="1", code_sha256=workflow.code_sha256)
    assert (head.mode, head.run_class, head.basis_ref) == ("autonomous_logged", "production", BASIS_REF)
    assert (head.engine_version, head.contract_version) == (__version__, CONTRACT_VERSION)
    assert head.settings_sha256 == payload_sha256(EngineSettings().model_dump(mode="json"))
    assert (head.servers, head.always_ask, head.unreleased_tools, head.decision_runtime) == ([], [], {}, {})
    assert rig.store.payload(head.input_ref) == {"value": given}  # the input is stored, not copied into the journal
    assert head.input_sha256 == payload_sha256(given)
    read, read_done, write, write_done, done = events[1:]
    assert (read.path, read.attempt, write.path, write.attempt) == ("0", 1, "1", 1)
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
