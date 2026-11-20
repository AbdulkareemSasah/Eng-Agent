"""`run` with a fake engine: the approval on the page, the report, the ports and the outcomes (spec 0006 AC7, AC71)."""

import json
from pathlib import Path
from typing import Any, cast

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from helpers.cli_deps import (
    FILE_FLOW,
    REGISTRY,
    WORKFLOW,
    FakeInput,
    FakeOutput,
    Placeholder,
    Rig,
    Script,
    Session,
    approves,
    approving_opener,
    client_for,
    completes,
)

from eng_harness.block import Registry, workflow
from eng_harness.cli import CliDeps, ExitCode
from eng_harness.cli._wiring import RunPortSet, default_engine_factory
from eng_harness.ctx import Preview, PreviewItem
from eng_harness.engine import Engine, EngineSettings, PermissionMode, RunOutcome, RunStatus
from eng_harness.errors import HarnessCode, JournalIntegrityError, NotImplementedGap, RunLocked, RunRefused
from eng_harness.journal import EventType, JournalReader
from eng_harness.journal import _events as ev
from eng_harness.ports import ApprovalPort, BasisPort, CalcPort, HostPort, InputPort, RunClass, ToolPort
from eng_harness.servers import ConfigError


def _events(rig: Rig, run_id: str) -> list[ev.Event]:
    reader = JournalReader(rig.runs / run_id)
    try:
        return reader.events()
    finally:
        reader.close()


def test_run_completes_and_writes_report(tmp_path: Path) -> None:
    rig = Rig(tmp_path, script=approves(wait=True))
    rig.open_with = approving_opener(rig)
    path = rig.input_file('{"note": "n"}', "utf-8-sig")  # a byte-order mark is read as without it (spec 4.7)
    assert rig.main("run", WORKFLOW, "--input", path, "--json", "--progress", "off") == ExitCode.OK
    result = json.loads(rig.out.getvalue())
    [run_id] = rig.run_ids()
    report = rig.runs / run_id / "report" / "report.html"
    assert result == {
        "run_id": run_id, "workflow": WORKFLOW, "status": "COMPLETED", "exit_code": 0, "pending": [],
        "escalation": None, "report": str(report),
    }  # fmt: skip
    assert report.read_text(encoding="utf-8").startswith("<!doctype html>")
    events = _events(rig, run_id)
    assert events[-1].type is EventType.RUN_COMPLETED
    assert [e.payload.by for e in events if isinstance(e.payload, ev.ApprovalResolved)] == ["engineer:ada"]
    assert "approval page opened in your browser" in rig.err.getvalue()
    assert all(rig.opened[0] not in text for text in (rig.out.getvalue(), rig.err.getvalue()))  # never on a stream
    request = rig.engines[0].run_request
    assert request is not None
    assert (request.input, request.mode, request.run_class) == (
        {"note": "n"},
        PermissionMode.WORK_ON_COPY,
        "production",
    )
    assert request.basis_ref == "res_" + "0" * 26  # a workflow without required basis fields (spec Q23, interim)


def test_ports_entered_around_engine_call(tmp_path: Path) -> None:
    rig = Rig(tmp_path / "returns", script=completes)
    assert rig.main("run", WORKFLOW, "--no-report", "--progress", "off") == ExitCode.OK
    assert rig.log == ["enter", "start", "exit"]

    async def locked(session: Session) -> RunOutcome:
        raise ContractError(ErrorCode.HOST_LOCKED, "another driver holds the host")

    async def broken(session: Session) -> RunOutcome:
        raise RuntimeError("boom")

    for name, script, code, text in [
        ("locked", locked, ExitCode.RUN_LOCKED, "HOST_LOCKED: another driver holds the host"),
        ("broken", broken, ExitCode.INTERNAL, "internal error err_"),
    ]:
        rig = Rig(tmp_path / name, script=script)
        assert rig.main("run", WORKFLOW, "--no-report", "--progress", "off") == code, name
        assert rig.log == ["enter", "start", "exit"], name  # the ports are left when the engine raises
        assert text in rig.err.getvalue(), name


def test_outcomes_map_to_exit_codes(tmp_path: Path) -> None:
    def returns(status: RunStatus, escalation: ev.RunEscalated | None = None) -> Script:
        async def script(session: Session) -> RunOutcome:
            return RunOutcome(session.run_id, status, escalation=escalation)

        return script

    escalation = ev.RunEscalated(reason="block_escalation", detail="d\x1b[2Jetail", evidence=[])

    async def input_pause(session: Session) -> RunOutcome:
        return session.paused("awaiting_input", ("in1",))

    async def stop_pause(session: Session) -> RunOutcome:
        return session.paused("stop_requested")

    for name, script, code, text in [
        ("failed", returns(RunStatus.FAILED), ExitCode.RUN_FAILED, ": FAILED"),
        (
            "escalated",
            returns(RunStatus.NEEDS_ENGINEER, escalation=escalation),
            ExitCode.NEEDS_ENGINEER,
            "needs the engineer: block_escalation: d",
        ),
        ("input", input_pause, ExitCode.AWAITING_ENGINEER, ": PAUSED"),
        ("stop", stop_pause, ExitCode.STOPPED, "resume with: eng-harness resume run_"),
    ]:
        rig = Rig(tmp_path / name, script=script)
        assert rig.main("run", WORKFLOW, "--no-report", "--progress", "off") == code, name
        assert text in rig.out.getvalue(), (name, rig.out.getvalue())
        assert "\x1b" not in rig.out.getvalue(), name  # untrusted text is shown without control characters


def test_generated_options_reach_the_input(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    path = rig.input_file('{"note": "x", "count": 1}')
    argv = ["run", WORKFLOW, "--input", path, "--title", "T", "--count", "3", "--mode", "approve_each_write"]
    assert rig.main(*argv, "--run-class", "trial", "--no-report", "--progress", "off") == ExitCode.OK
    request = rig.engines[0].run_request
    assert request is not None
    assert request.input == {"note": "x", "title": "T", "count": 3}  # an option replaces the file's value
    assert (request.mode, request.run_class) == (PermissionMode.APPROVE_EACH_WRITE, RunClass.TRIAL)


def test_default_engine_factory_is_the_merged_engine(tmp_path: Path) -> None:
    assert CliDeps().engine_factory is default_engine_factory
    clock, root = FixedClock(0, 1), tmp_path / "ws"
    ids, workspace = SeededIdSource(b"x", clock), Workspace(root=root, classification=LocationClass.LOCAL)
    from eng_harness._kinds import HARNESS_KINDS

    ports = RunPortSet(
        tool=cast(ToolPort, Placeholder()), host=cast(HostPort, Placeholder()), calc=cast(CalcPort, Placeholder()),
        basis=cast(BasisPort, Placeholder()), approvals=cast(ApprovalPort, Placeholder()),
        inputs=cast(InputPort, Placeholder()),
    )  # fmt: skip
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    engine = default_engine_factory(workspace, REGISTRY, ports, store, EngineSettings(), clock, ids)
    assert isinstance(engine, Engine)


def test_engine_errors_map_to_exit_codes(tmp_path: Path) -> None:
    def raises(error: Exception) -> Script:
        async def script(session: Session) -> RunOutcome:
            raise error

        return script

    for name, error, code, text in [
        (
            "refused",
            RunRefused(HarnessCode.BASIS_INCOMPLETE, "no basis"),
            ExitCode.REFUSED,
            "BASIS_INCOMPLETE: no basis",
        ),
        ("locked", RunLocked("held"), ExitCode.RUN_LOCKED, "RUN_LOCKED: held"),
        ("journal", JournalIntegrityError("bad"), ExitCode.JOURNAL_INTEGRITY, "JOURNAL_INTEGRITY: bad"),
        ("argument", ContractError(ErrorCode.INVALID_ARGUMENT, "no"), ExitCode.USAGE, "INVALID_ARGUMENT: no"),
        ("config", ConfigError("servers.csi", "bad"), ExitCode.USAGE, "configuration error: servers.csi: bad"),
    ]:
        rig = Rig(tmp_path / name, script=raises(error))
        assert rig.main("run", WORKFLOW, "--no-report", "--progress", "off") == code, name
        assert rig.err.getvalue() == f"eng-harness: {text}\n", name


def test_progress_modes_and_streams(tmp_path: Path) -> None:
    def stderr_of(*options: str) -> str:
        rig = Rig(tmp_path / "".join(options).replace("-", ""))
        assert rig.main("run", WORKFLOW, "--no-report", *options) == ExitCode.OK
        return rig.err.getvalue()

    events = [json.loads(line) for line in stderr_of("--progress", "json").splitlines()]
    assert [e["event"] for e in events][:1] == ["run_started"]
    plain = stderr_of("--progress", "plain")
    assert plain.startswith("run_started") or "run" in plain.splitlines()[0]
    assert stderr_of("--progress", "off") == ""
    assert stderr_of() == plain  # `auto` is `plain` on a stream that is not a terminal
    assert "\x1b[" in stderr_of("--progress", "tty")


def test_no_browser_and_wait_timeout(tmp_path: Path) -> None:
    for name, options, opened in [("flag", ["--no-browser"], 0), ("failed", [], 1)]:
        rig = Rig(tmp_path / name, script=approves(wait=True), open_with=lambda _: False)
        argv = ["run", WORKFLOW, "--wait-timeout", "1", "--json", "--progress", "off", *options]
        assert rig.main(*argv) == ExitCode.AWAITING_ENGINEER, name  # nobody answered within the timeout
        assert "the launch address cannot be shown here" in rig.err.getvalue(), name
        assert len(rig.opened) == opened, name
        assert all(address not in rig.err.getvalue() + rig.out.getvalue() for address in rig.opened), name
        for address in rig.opened:
            with pytest.raises(OSError, match="refused"):
                client_for(address).get("/")  # the page server stopped when the command returned


def test_engine_mode_comes_from_the_configuration(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.workspace.mkdir(parents=True)
    (rig.workspace / "harness.toml").write_text('[engine]\ndefault_mode = "autonomous_logged"\n', encoding="utf-8")
    assert rig.main("run", WORKFLOW, "--no-report", "--progress", "off") == ExitCode.OK
    request = rig.engines[0].run_request
    assert request is not None
    assert request.mode is PermissionMode.AUTONOMOUS_LOGGED


def test_report_that_cannot_be_built_is_a_warning(tmp_path: Path) -> None:
    rig = Rig(tmp_path, keep_basis_ref=True)  # the Q23 reference names no stored result
    assert rig.main("run", WORKFLOW, "--json", "--progress", "off") == ExitCode.OK
    assert json.loads(rig.out.getvalue())["report"] is None
    assert "eng-harness: the report was not written: " in rig.err.getvalue()
    assert not (rig.runs / rig.run_ids()[0] / "report").exists()


REAL_FLOW = "real_flow"


@workflow(name=REAL_FLOW, version=1, description="A workflow with one approval, for the real engine.")
async def real_flow(ctx: Any, inp: FakeInput) -> FakeOutput:
    """One approval of one item, then done."""
    preview = Preview(items=(PreviewItem(id="i1", label="One change", refs=()),), diff_ref=None, models=())
    await ctx.approve("Apply the change", preview)
    return FakeOutput()


def test_page_ports_wait_unless_no_wait_real_engine(tmp_path: Path) -> None:
    """The merged engine asks `answer(wait=False)`; the process wait mode is the command's (spec 4.4.5 step 2)."""
    rig = Rig(tmp_path / "waits", real_engine=True)
    rig.open_with = approving_opener(rig, current=lambda: rig.shown[-1] if rig.shown else None)
    registry = Registry([real_flow])
    argv = ["run", REAL_FLOW, "--no-report", "--progress", "off", "--json"]
    assert rig.main(*argv, workflow_registry=registry) == ExitCode.OK  # answered on the page: the run waited for it
    [run_id] = rig.run_ids()
    events = _events(rig, run_id)
    assert events[-1].type is EventType.RUN_COMPLETED
    assert [e.payload.by for e in events if isinstance(e.payload, ev.ApprovalResolved)] == ["engineer:ada"]
    assert len(rig.opened) == 1

    other = Rig(tmp_path / "no_wait", real_engine=True)
    assert other.main(*argv, "--no-wait", workflow_registry=registry) == ExitCode.AWAITING_ENGINEER  # at once
    [paused_id] = other.run_ids()
    assert other.opened == []  # no page was served
    assert _events(other, paused_id)[-1].payload == ev.RunPaused(
        reason="awaiting_approval", request_ids=[json.loads(other.out.getvalue())["pending"][0]["request_id"]]
    )


def test_model_files_reach_the_port_builder(tmp_path: Path) -> None:
    rig = Rig(tmp_path / "ok", script=approves(wait=False))
    model = tmp_path / "models" / "plan.edb"
    model.parent.mkdir()
    model.write_bytes(b"x")
    second_model = model.with_name("second.edb")
    second_model.write_bytes(b"y")
    given = rig.input_file(
        json.dumps(
            {
                "model_file": str(model),
                "other_file": str(second_model),
                "ordinary_path": "notes.txt",
                "visible_host": True,
            }
        )
    )
    expected_files = {"plan.edb": model, "second.edb": second_model}
    argv = ["--no-wait", "--no-report", "--progress", "off"]
    assert rig.main("run", FILE_FLOW, "--input", given, *argv) == ExitCode.AWAITING_ENGINEER, rig.err.getvalue()
    assert rig.models == [(expected_files, True)]  # includes both model files and excludes the ordinary path
    assert all(isinstance(path, Path) for path in rig.models[0][0].values())
    [run_id] = rig.run_ids()
    model.unlink()  # a moved original is passed on unchecked at resume (spec 4.2.2 step 2)
    assert rig.main("resume", run_id, *argv) == ExitCode.AWAITING_ENGINEER
    assert rig.models[1] == (expected_files, True)  # from the run's stored input
    plain = Rig(tmp_path / "plain")
    assert plain.main("run", WORKFLOW, *argv) == ExitCode.OK
    assert plain.models == [({}, False)]  # no model file and no `visible_host` field

    other = tmp_path / "other" / "plan.edb"
    other.parent.mkdir()
    other.write_bytes(b"y")
    absent = tmp_path / "absent.edb"
    for name, values, text in [
        ("relative", {"model_file": "plan.edb"}, "plan.edb is not an absolute path"),
        ("missing", {"model_file": str(absent)}, f"{absent} is not an existing file"),
        ("repeated", {"model_file": str(model.parent / "plan.edb"), "other_file": str(other)}, "same base name"),
    ]:
        model.write_bytes(b"x")
        refused = Rig(tmp_path / name)
        assert refused.main("run", FILE_FLOW, "--input", refused.input_file(json.dumps(values))) == ExitCode.USAGE, name
        assert text in refused.err.getvalue(), (name, refused.err.getvalue())
        assert (refused.run_ids(), refused.built, refused.engines) == ([], [], []), name


def test_port_builder_gap_exits_2(tmp_path: Path) -> None:
    message = "H-G8: CLI tools are not wired: sasaah-cli"

    def gap(_: Path) -> None:
        raise NotImplementedGap(message)

    rig = Rig(tmp_path, on_build=gap)
    assert rig.main("run", WORKFLOW, "--no-report") == ExitCode.USAGE  # returned by the command itself
    assert f"eng-harness: {message}\n" in rig.err.getvalue()
    assert (rig.run_ids(), rig.engines, rig.log, rig.out.getvalue()) == ([], [], [], "")

    paused = Rig(tmp_path / "resume", script=approves(wait=False))
    assert paused.main("run", WORKFLOW, "--no-wait", "--no-report") == ExitCode.AWAITING_ENGINEER
    [run_id] = paused.run_ids()
    before = _events(paused, run_id)
    paused.on_build = gap
    paused.err.truncate(0)
    assert paused.main("resume", run_id, "--no-report") == ExitCode.USAGE
    assert f"eng-harness: {message}\n" in paused.err.getvalue()
    assert _events(paused, run_id) == before  # nothing was journaled


def test_run_header_records_decision_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC63: `run_started.decision_runtime` and `run_resumed.decision_runtime` track the assembled summary."""
    import keyring
    from fakes.credential_stores import MemoryKeyringBackend, backend_path

    import eng_harness.providers._credentials as credentials_mod
    from eng_harness.providers import KeyringCredentialStore, assemble_decision_runtime
    from eng_harness.providers._credentials import SERVICE_NAME

    fake_key = "-".join(("distinctive", "test", "credential", "9f4b2a"))
    memory = MemoryKeyringBackend()
    memory.set_password(SERVICE_NAME, "ref-secret-name", fake_key)
    monkeypatch.setattr(keyring, "get_keyring", lambda: memory)
    monkeypatch.setattr(
        credentials_mod,
        "DEFAULT_ALLOWED_BACKENDS",
        credentials_mod.DEFAULT_ALLOWED_BACKENDS | {backend_path(memory)},
    )
    stored_secret = KeyringCredentialStore().get("ref-secret-name")
    assert stored_secret is not None
    assert stored_secret.get_secret_value() == fake_key

    def write_cfg(rig: Rig, version: str) -> None:
        rig.workspace.mkdir(parents=True, exist_ok=True)
        (rig.workspace / "harness.toml").write_text(
            "[providers.decision]\n"
            'base_url = "https://endpoint-host.example.test/v1"\n'
            'model = "m"\n'
            f'model_version = "{version}"\n'
            'key_ref = "ref-secret-name"\n'
            "request_timeout_ms = 1500\n"
            '[decisions.shadow_released.pick_action]\npoint_version = 1\nbasis = "owner"\nrecord = "owner-rec"\n',
            encoding="utf-8",
        )

    rig = Rig(tmp_path, script=approves(wait=False))
    write_cfg(rig, "v1")
    assert (
        rig.main(
            "run",
            WORKFLOW,
            "--no-wait",
            "--no-report",
            "--progress",
            "off",
            decision_assembler=assemble_decision_runtime,
        )
        == ExitCode.AWAITING_ENGINEER
    )
    [run_id] = rig.run_ids()
    reader = JournalReader(rig.runs / run_id)
    try:
        header = reader.header()
    finally:
        reader.close()
    assert header.decision_runtime == {
        "providers": [
            {
                "name": "openrouter", "model": "m", "version": "v1", "is_local": False, "tier": 2,
                "status": "not_implemented",
            }
        ],
        "released": {},
        "dropped_releases": [{"point": "pick_action", "reason": "PR-G1"}],
    }  # fmt: skip

    write_cfg(rig, "v2")
    rig.script = approves(wait=True)
    rig.open_with = approving_opener(rig)
    assert rig.main("resume", run_id, "--no-report", "--progress", "off") == ExitCode.OK
    resumes = [e.payload for e in _events(rig, run_id) if isinstance(e.payload, ev.RunResumed)]
    assert len(resumes) == 1
    assert resumes[0].decision_runtime == {
        "providers": [
            {
                "name": "openrouter", "model": "m", "version": "v2", "is_local": False, "tier": 2,
                "status": "not_implemented",
            }
        ],
        "released": {},
        "dropped_releases": [{"point": "pick_action", "reason": "PR-G1"}],
    }  # fmt: skip

    assert (rig.runs / run_id / "journal.sqlite").is_file()
    all_bytes = b"".join(p.read_bytes() for p in (rig.runs / run_id).rglob("*") if p.is_file())
    stdout_bytes = rig.out.getvalue().encode("utf-8")
    stderr_bytes = rig.err.getvalue().encode("utf-8")
    for secret in (b"endpoint-host", b"ref-secret-name", b"base_url", b"key_ref", fake_key.encode("utf-8")):
        assert secret not in all_bytes
        assert secret not in stdout_bytes
        assert secret not in stderr_bytes


def test_run_completes_and_writes_report_real_engine(tmp_path: Path) -> None:
    """AC7 re-check with the real engine through the production port mapping (plan 0006 T17c).

    A confirmed basis is required: the Q23 interim `basis_ref` cannot be reported (plan T14), so the re-check uses a
    workflow with `basis_fields`, confirms the draft on the page, then answers the approval.
    """
    import contextlib
    import re
    import threading
    import time

    from eng_contract.cited import Cited
    from helpers.cli_deps import client_for

    from eng_harness.basis import FieldSpec
    from eng_harness.pages._answers import bound_sha256
    from eng_harness.pages._security import CSRF_FIELD

    draft_sha = re.compile(r'<input type="hidden" name="draft_sha256" value="([0-9a-f]{64})">')
    setup_link = re.compile(r'href="(/setup/[0-9A-HJKMNP-TV-Z]{26})"')
    fields = (
        FieldSpec(
            path="materials.concrete_fc_MPa",
            kind="quantity",
            label="Concrete fc",
            required=True,
            unit="MPa",
            min=Cited(value=20, unit="MPa", source="ACI 318-14 19.2.1"),
            max=Cited(value=80, unit="MPa", source="ACI 318-14 19.2.1"),
        ),
    )
    flow_name = "report_real_flow"

    @workflow(
        name=flow_name,
        version=1,
        description="Basis then one approval for the AC7 real-engine re-check.",
        basis_fields=fields,
    )
    async def report_real_flow(ctx: Any, inp: FakeInput) -> FakeOutput:
        preview = Preview(items=(PreviewItem(id="i1", label="One change", refs=()),), diff_ref=None, models=())
        await ctx.approve("Apply the change", preview)
        return FakeOutput()

    registry = Registry([report_real_flow])
    basis = tmp_path / "values.yaml"
    basis.write_text(
        "name: Engineer A\nvalues:\n  materials.concrete_fc_MPa:\n    value: 35\n    unit: MPa\n",
        encoding="utf-8",
        newline="\n",
    )
    rig = Rig(tmp_path, real_engine=True)

    def interact(address: str) -> None:
        with contextlib.suppress(Exception):
            client = client_for(address)
            client.open()
            end = time.monotonic() + 15
            setup_path = None
            while setup_path is None and time.monotonic() < end:
                found = setup_link.search(client.get("/").body)
                if found is not None:
                    setup_path = found.group(1)
                else:
                    time.sleep(0.02)
            assert setup_path is not None
            page = client.get(setup_path)
            match = draft_sha.search(page.body)
            assert match is not None
            client.post(
                setup_path,
                {
                    CSRF_FIELD: client.token(setup_path),
                    "draft_sha256": match.group(1),
                    "by": "Ada",
                    "decision": "confirm",
                    "confirm_materials": "on",
                },
            )
            while not rig.shown and time.monotonic() < end:
                time.sleep(0.02)
            request = rig.shown[-1]
            form = {
                CSRF_FIELD: client.token(f"/request/{request.request_id}"),
                "shown_sha256": bound_sha256(request),
                "by": "ada",
                "decision": "approve",
            }
            client.post(f"/answer/{request.request_id}", form)

    def opener(address: str) -> bool:
        rig.opened.append(address)
        threading.Thread(target=interact, args=(address,), daemon=True).start()
        return True

    rig.open_with = opener
    path = rig.input_file('{"note": "n"}', "utf-8-sig")
    assert (
        rig.main(
            "run",
            flow_name,
            "--input",
            path,
            "--basis",
            str(basis),
            "--json",
            "--progress",
            "off",
            workflow_registry=registry,
            basis_fields_of=lambda w: w.basis_fields,
        )
        == ExitCode.OK
    ), rig.err.getvalue()
    result = json.loads(rig.out.getvalue())
    [run_id] = rig.run_ids()
    report = rig.runs / run_id / "report" / "report.html"
    assert result == {
        "run_id": run_id, "workflow": flow_name, "status": "COMPLETED", "exit_code": 0, "pending": [],
        "escalation": None, "report": str(report),
    }  # fmt: skip
    assert report.read_text(encoding="utf-8").startswith("<!doctype html>")
    events = _events(rig, run_id)
    assert events[-1].type is EventType.RUN_COMPLETED
    assert [e.payload.by for e in events if isinstance(e.payload, ev.ApprovalResolved)] == ["engineer:ada"]
    assert "approval page opened in your browser" in rig.err.getvalue()
    assert all(rig.opened[0] not in text for text in (rig.out.getvalue(), rig.err.getvalue()))


def test_run_header_records_decision_runtime_real_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC63 re-check: the real engine's header through engine AC69 with a recording assembler (plan 0006 T17c)."""
    import keyring
    from fakes.credential_stores import MemoryKeyringBackend, backend_path

    import eng_harness.providers._credentials as credentials_mod
    from eng_harness.providers import KeyringCredentialStore, assemble_decision_runtime
    from eng_harness.providers._credentials import SERVICE_NAME

    fake_key = "-".join(("distinctive", "test", "credential", "9f4b2a"))
    memory = MemoryKeyringBackend()
    memory.set_password(SERVICE_NAME, "ref-secret-name", fake_key)
    monkeypatch.setattr(keyring, "get_keyring", lambda: memory)
    monkeypatch.setattr(
        credentials_mod,
        "DEFAULT_ALLOWED_BACKENDS",
        credentials_mod.DEFAULT_ALLOWED_BACKENDS | {backend_path(memory)},
    )
    stored_secret = KeyringCredentialStore().get("ref-secret-name")
    assert stored_secret is not None
    assert stored_secret.get_secret_value() == fake_key

    def write_cfg(rig: Rig, version: str) -> None:
        rig.workspace.mkdir(parents=True, exist_ok=True)
        (rig.workspace / "harness.toml").write_text(
            "[providers.decision]\n"
            'base_url = "https://endpoint-host.example.test/v1"\n'
            'model = "m"\n'
            f'model_version = "{version}"\n'
            'key_ref = "ref-secret-name"\n'
            "request_timeout_ms = 1500\n"
            '[decisions.shadow_released.pick_action]\npoint_version = 1\nbasis = "owner"\nrecord = "owner-rec"\n',
            encoding="utf-8",
        )

    registry = Registry([real_flow])
    rig = Rig(tmp_path, real_engine=True)
    write_cfg(rig, "v1")
    assert (
        rig.main(
            "run",
            REAL_FLOW,
            "--no-wait",
            "--no-report",
            "--progress",
            "off",
            workflow_registry=registry,
            decision_assembler=assemble_decision_runtime,
        )
        == ExitCode.AWAITING_ENGINEER
    )
    [run_id] = rig.run_ids()
    reader = JournalReader(rig.runs / run_id)
    try:
        header = reader.header()
    finally:
        reader.close()
    assert header.decision_runtime == {
        "providers": [
            {
                "name": "openrouter", "model": "m", "version": "v1", "is_local": False, "tier": 2,
                "status": "not_implemented",
            }
        ],
        "released": {},
        "dropped_releases": [{"point": "pick_action", "reason": "PR-G1"}],
    }  # fmt: skip

    write_cfg(rig, "v2")
    rig.open_with = approving_opener(rig, current=lambda: rig.shown[-1] if rig.shown else None)
    assert (
        rig.main(
            "resume",
            run_id,
            "--no-report",
            "--progress",
            "off",
            workflow_registry=registry,
            decision_assembler=assemble_decision_runtime,
        )
        == ExitCode.OK
    )
    resumes = [e.payload for e in _events(rig, run_id) if isinstance(e.payload, ev.RunResumed)]
    assert len(resumes) == 1
    assert resumes[0].decision_runtime == {
        "providers": [
            {
                "name": "openrouter", "model": "m", "version": "v2", "is_local": False, "tier": 2,
                "status": "not_implemented",
            }
        ],
        "released": {},
        "dropped_releases": [{"point": "pick_action", "reason": "PR-G1"}],
    }  # fmt: skip

    assert (rig.runs / run_id / "journal.sqlite").is_file()
    all_bytes = b"".join(p.read_bytes() for p in (rig.runs / run_id).rglob("*") if p.is_file())
    stdout_bytes = rig.out.getvalue().encode("utf-8")
    stderr_bytes = rig.err.getvalue().encode("utf-8")
    for secret in (b"endpoint-host", b"ref-secret-name", b"base_url", b"key_ref", fake_key.encode("utf-8")):
        assert secret not in all_bytes
        assert secret not in stdout_bytes
        assert secret not in stderr_bytes
