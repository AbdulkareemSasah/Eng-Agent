"""`run --answers` and `resume --answers` over the staged engine: a file answers data requests only (spec 0006 AC46,
AC64; plan 0006 T14c). The real-engine half is re-checked in plan T17c."""

import json
from pathlib import Path
from typing import Any

from helpers.cli_deps import WORKFLOW, Rig, Script, approves, asks, opens_choice

from eng_harness.cli import ExitCode
from eng_harness.journal import JournalReader
from eng_harness.journal import _events as ev

ASK = "ask_one"
VALUES = {"label": "x", "count": 2}
QUIET = ["--no-wait", "--no-report", "--progress", "off"]


def _rig(root: Path, script: Script, *, engineer: bool = True) -> Rig:
    rig = Rig(root, script=script)
    if engineer:
        rig.workspace.mkdir(parents=True)
        (rig.workspace / "harness.toml").write_text('[engine]\nengineer = "ada"\n', encoding="utf-8")
    return rig


def _file(rig: Rig, value: Any, encoding: str = "utf-8") -> str:
    path = rig.root / "answers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding=encoding)
    return str(path)


def _path(rig: Rig, answers: Any) -> str:
    """A path is used as it is, bytes are written as the file's text, anything else as JSON."""
    if isinstance(answers, str):
        return answers
    if isinstance(answers, bytes):
        (rig.root / "answers.json").write_bytes(answers)
        return str(rig.root / "answers.json")
    return _file(rig, answers)


def _events(rig: Rig, run_id: str) -> list[ev.Event]:
    reader = JournalReader(rig.runs / run_id)
    try:
        return reader.events()
    finally:
        reader.close()


def _provided(rig: Rig, run_id: str) -> list[ev.InputProvided]:
    return [e.payload for e in _events(rig, run_id) if isinstance(e.payload, ev.InputProvided)]


def _paused(rig: Rig) -> str:
    assert rig.main("run", WORKFLOW, *QUIET) == ExitCode.AWAITING_ENGINEER
    [run_id] = rig.run_ids()
    return run_id


def test_form_request_answers_file(tmp_path: Path) -> None:
    for name, shape, encoding in [("bare", VALUES, "utf-8"), ("keyed", {ASK: VALUES}, "utf-8-sig")]:
        rig = _rig(tmp_path / name, asks(ASK))
        run_id = _paused(rig)
        assert _provided(rig, run_id) == []
        answers = _file(rig, shape, encoding)
        assert rig.main("resume", run_id, "--answers", answers, "--no-report", "--progress", "off") == ExitCode.OK, name
        [given] = _provided(rig, run_id)
        assert (given.request_id, given.by) == (ASK, "engineer:ada"), name  # `by` is the configured engineer
        [answer] = rig.engines[-1].answers
        assert (answer.values, answer.by) == (VALUES, "ada"), name
        assert rig.opened == [], name  # a file serves no page

    def refused(name: str, script: Script, answers: Any, text: str, *, engineer: bool = True) -> None:
        rig = _rig(tmp_path / name, script, engineer=engineer)
        run_id = _paused(rig)
        before = _events(rig, run_id)
        path = _path(rig, answers)
        assert rig.main("resume", run_id, "--answers", path, "--no-report") == ExitCode.USAGE, name
        assert text in rig.err.getvalue(), (name, rig.err.getvalue())
        assert _events(rig, run_id) == before, name  # nothing journaled
        assert rig.engines[-1].answers == [], name

    refused("unset", asks(ASK), VALUES, "[engine] engineer", engineer=False)
    refused("unknown", approves(wait=False), {"ask_other": VALUES}, "no pending data request ask_other")
    refused("approval", approves(wait=False), {"apr_one": VALUES}, "no pending data request apr_one")
    refused("engine", opens_choice("engine.in_flight", "esc_one"), {"esc_one": {}}, "esc_one is not a data request")
    refused("missing", asks(ASK), str(tmp_path / "nope.json"), "cannot read the answers file nope.json")
    refused("syntax", asks(ASK), b"{not json", "cannot read the answers file")
    refused("list", asks(ASK), [1], "the answers file must hold one JSON object")
    refused("value", asks(ASK), {ASK: "not an object"}, f"the answer for {ASK} must be a JSON object")


def test_run_answers_first_data_request(tmp_path: Path) -> None:
    rig = _rig(tmp_path / "first", asks(ASK, "ask_two"))
    answers = _file(rig, VALUES, "utf-8-sig")  # a byte-order mark is read as without it (spec 4.7)
    assert rig.main("run", WORKFLOW, "--answers", answers, *QUIET) == ExitCode.AWAITING_ENGINEER
    [run_id] = rig.run_ids()
    [given] = _provided(rig, run_id)
    assert (given.request_id, given.by) == (ASK, "engineer:ada")
    assert [r.request_id for r in rig.engines[0].asked] == [ASK, "ask_two"]  # the later request is never answered
    assert [a.request_id for a in rig.engines[0].answers] == [ASK]
    assert rig.opened == []  # no page was served for the first request
    assert "not used" not in rig.err.getvalue()

    rig = _rig(tmp_path / "none", approves(wait=False))  # a run that opens no data request: outcome unchanged
    assert rig.main("run", WORKFLOW, "--answers", _file(rig, VALUES), *QUIET) == ExitCode.AWAITING_ENGINEER
    [run_id] = rig.run_ids()
    assert _provided(rig, run_id) == []  # an approval is never answered from the file
    assert rig.err.getvalue().count("the --answers file was not used") == 1

    rig = _rig(tmp_path / "bad", asks(ASK))  # values that fail the request's model are refused by the engine
    assert rig.main("run", WORKFLOW, "--answers", _file(rig, {"label": 1}), *QUIET) == ExitCode.AWAITING_ENGINEER
    [run_id] = rig.run_ids()
    assert _provided(rig, run_id) == []

    cases: list[tuple[str, Any, str, bool]] = [
        ("missing", str(tmp_path / "nope.json"), "cannot read the answers file nope.json", True),
        ("list", [1], "the answers file must hold one JSON object", True),
        ("unset", VALUES, "[engine] engineer", False),
    ]
    for name, answers, text, engineer in cases:
        rig = _rig(tmp_path / name, asks(ASK), engineer=engineer)
        path = _path(rig, answers)
        assert rig.main("run", WORKFLOW, "--answers", path, *QUIET) == ExitCode.USAGE, name
        assert text in rig.err.getvalue(), (name, rig.err.getvalue())
        assert (rig.run_ids(), rig.engines, rig.built) == ([], [], []), name


def test_form_request_answers_file_real_engine(tmp_path: Path) -> None:
    """AC46 re-check with the real engine through the production port mapping (plan 0006 T17c)."""
    from helpers.cli_deps import FakeInput, FakeOutput
    from pydantic import BaseModel, ConfigDict

    from eng_harness.block import Registry, workflow

    class Section(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")

        label: str
        count: int

    flow_name = "ask_real_flow"

    @workflow(name=flow_name, version=1, description="One data request for the real-engine answers-file re-check.")
    async def ask_real_flow(ctx: Any, inp: FakeInput) -> FakeOutput:
        answered = await ctx.ask(Section, title="Give the values")
        assert answered.value == Section(label="x", count=2)
        return FakeOutput()

    registry = Registry([ask_real_flow])
    for name, encoding, keyed in [("bare", "utf-8", False), ("keyed", "utf-8-sig", True)]:
        rig = Rig(tmp_path / name, real_engine=True)
        rig.workspace.mkdir(parents=True)
        (rig.workspace / "harness.toml").write_text('[engine]\nengineer = "ada"\n', encoding="utf-8")
        assert rig.main("run", flow_name, *QUIET, workflow_registry=registry) == ExitCode.AWAITING_ENGINEER, name
        [run_id] = rig.run_ids()
        assert _provided(rig, run_id) == [], name
        request_id = next(
            e.payload.request_id for e in _events(rig, run_id) if isinstance(e.payload, ev.InputRequested)
        )
        payload: Any = {request_id: VALUES} if keyed else VALUES
        answers = _file(rig, payload, encoding)
        assert (
            rig.main(
                "resume",
                run_id,
                "--answers",
                answers,
                "--no-report",
                "--progress",
                "off",
                workflow_registry=registry,
            )
            == ExitCode.OK
        ), name
        [given] = _provided(rig, run_id)
        assert (given.request_id, given.by) == (request_id, "engineer:ada"), name
        assert rig.opened == [], name


def test_run_answers_first_data_request_real_engine(tmp_path: Path) -> None:
    """AC64 re-check with the real engine through the production port mapping (plan 0006 T17c)."""
    from helpers.cli_deps import FakeInput, FakeOutput
    from pydantic import BaseModel, ConfigDict

    from eng_harness.block import Registry, workflow
    from eng_harness.ctx import Preview, PreviewItem

    class Section(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")

        label: str
        count: int

    flow_name = "ask_two_real_flow"
    seen: list[str] = []

    @workflow(name=flow_name, version=1, description="Two data requests; only the first is pre-answered.")
    async def ask_two_real_flow(ctx: Any, inp: FakeInput) -> FakeOutput:
        first = await ctx.ask(Section, title="First values")
        seen.append(first.value.label)
        await ctx.ask(Section, title="Second values")
        return FakeOutput()

    registry = Registry([ask_two_real_flow])
    rig = Rig(tmp_path / "first", real_engine=True)
    rig.workspace.mkdir(parents=True)
    (rig.workspace / "harness.toml").write_text('[engine]\nengineer = "ada"\n', encoding="utf-8")
    answers = _file(rig, VALUES, "utf-8-sig")
    assert (
        rig.main("run", flow_name, "--answers", answers, *QUIET, workflow_registry=registry)
        == ExitCode.AWAITING_ENGINEER
    )
    [run_id] = rig.run_ids()
    [given] = _provided(rig, run_id)
    assert given.by == "engineer:ada"
    requested = [e.payload for e in _events(rig, run_id) if isinstance(e.payload, ev.InputRequested)]
    assert len(requested) == 2
    assert given.request_id == requested[0].request_id
    assert rig.opened == []
    assert "not used" not in rig.err.getvalue()
    assert seen == ["x"]

    approve_name = "approve_only_real"

    @workflow(name=approve_name, version=1, description="An approval only: --answers is unused.")
    async def approve_only(ctx: Any, inp: FakeInput) -> FakeOutput:
        preview = Preview(items=(PreviewItem(id="i1", label="One change", refs=()),), diff_ref=None, models=())
        await ctx.approve("Apply the change", preview)
        return FakeOutput()

    registry2 = Registry([approve_only])
    unused = Rig(tmp_path / "none", real_engine=True)
    unused.workspace.mkdir(parents=True)
    (unused.workspace / "harness.toml").write_text('[engine]\nengineer = "ada"\n', encoding="utf-8")
    assert (
        unused.main("run", approve_name, "--answers", _file(unused, VALUES), *QUIET, workflow_registry=registry2)
        == ExitCode.AWAITING_ENGINEER
    )
    [unused_id] = unused.run_ids()
    assert _provided(unused, unused_id) == []
    assert unused.err.getvalue().count("the --answers file was not used") == 1
