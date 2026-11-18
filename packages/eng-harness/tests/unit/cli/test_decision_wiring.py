"""Decision layer wiring in `run` and `resume` (spec 0006 AC62, section 4.2.2 steps 1 and 5; plan 0006 T14b)."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import keyring
import pytest
from eng_contract.ids import Clock, IdSource
from eng_contract.store import Workspace
from fakes.credential_stores import MemoryKeyringBackend
from helpers.cli_deps import WORKFLOW, Rig, Session, approves
from pydantic import JsonValue

from eng_harness.cli import CliDeps, ExitCode
from eng_harness.cli._config import HarnessConfig
from eng_harness.decisions._policy import DecisionPolicy, DecisionSettings, ShadowRelease
from eng_harness.decisions.interfaces import DecisionAnswer, DecisionCall, PendingAnswer
from eng_harness.engine import RunOutcome
from eng_harness.providers import DecisionRuntime, KeyringCredentialStore, ProvidersConfig, load_providers_config

NO_RUN = "run_" + "0" * 26


class _FakeDecisionPort:
    def __init__(self, summary: Mapping[str, JsonValue]) -> None:
        self._summary = dict(summary)

    async def decide(self, call: DecisionCall) -> DecisionAnswer | PendingAnswer:
        raise AssertionError("not called in wiring test")

    async def decide_many(self, calls: Sequence[DecisionCall]) -> list[DecisionAnswer | PendingAnswer]:
        raise AssertionError("not called in wiring test")

    def runtime_summary(self) -> Mapping[str, JsonValue]:
        return self._summary


def test_providers_loader_default_is_load_providers_config() -> None:
    assert CliDeps().providers_loader is load_providers_config


def test_providers_read_and_runtime_assembled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Refused `[providers.*]` tables fail in step 1 with exit 2 naming the key; no run, assembler, or store call.
    sentinel = "-".join(("never", "printed", "value"))
    bad_key = "_".join(("api", "key"))
    bad_toml = (
        "[providers.decision]\n"
        f'{bad_key} = "{sentinel}"\n'
        'base_url = "https://endpoint.example.test/v1"\n'
        'model = "m"\nmodel_version = "1"\nrequest_timeout_ms = 1500\n'
    )
    expected_bad_tables = {
        "decision": {
            bad_key: sentinel,
            "base_url": "https://endpoint.example.test/v1",
            "model": "m",
            "model_version": "1",
            "request_timeout_ms": 1500,
        }
    }
    loaded_tables: list[Mapping[str, Any] | None] = []
    assembled: list[tuple[ProvidersConfig, DecisionSettings, Workspace, Mapping[str, DecisionPolicy]]] = []
    cred_calls: list[str] = []
    spy_backend = MemoryKeyringBackend()

    def spy_get_keyring() -> Any:
        cred_calls.append("get_keyring")
        return spy_backend

    def spy_store_init(self: Any, *args: Any, **kwargs: Any) -> None:
        cred_calls.append("KeyringCredentialStore.__init__")

    def spy_store_get(self: Any, key_ref: str) -> Any:
        cred_calls.append(f"KeyringCredentialStore.get:{key_ref}")
        return None

    monkeypatch.setattr(keyring, "get_keyring", spy_get_keyring)
    monkeypatch.setattr(KeyringCredentialStore, "__init__", spy_store_init)
    monkeypatch.setattr(KeyringCredentialStore, "get", spy_store_get)

    def recording_loader(tables: Mapping[str, Any] | None) -> ProvidersConfig:
        loaded_tables.append(tables)
        return load_providers_config(tables)

    def recorder(
        providers: ProvidersConfig,
        settings: DecisionSettings,
        workspace: Workspace,
        policies: Mapping[str, DecisionPolicy],
    ) -> DecisionRuntime:
        assembled.append((providers, settings, workspace, policies))
        return DecisionRuntime(warnings=("warn: test release finding",), summary={"providers": ["ok"]})

    rig = Rig(tmp_path / "bad_run")
    rig.workspace.mkdir(parents=True)
    (rig.workspace / "harness.toml").write_text(bad_toml, encoding="utf-8")
    assert (
        rig.main("run", WORKFLOW, "--no-report", providers_loader=recording_loader, decision_assembler=recorder)
        == ExitCode.USAGE
    )
    assert "providers.decision.api_key" in rig.err.getvalue()
    assert sentinel not in rig.err.getvalue() + rig.out.getvalue()
    assert (rig.run_ids(), rig.engines, assembled, cred_calls) == ([], [], [], [])
    assert loaded_tables == [expected_bad_tables]

    loaded_tables.clear()
    rig_bad_resume = Rig(tmp_path / "bad_resume")
    rig_bad_resume.workspace.mkdir(parents=True)
    (rig_bad_resume.workspace / "harness.toml").write_text(bad_toml, encoding="utf-8")
    assert (
        rig_bad_resume.main(
            "resume", NO_RUN, "--no-report", providers_loader=recording_loader, decision_assembler=recorder
        )
        == ExitCode.USAGE
    )
    assert "providers.decision.api_key" in rig_bad_resume.err.getvalue()
    assert sentinel not in rig_bad_resume.err.getvalue() + rig_bad_resume.out.getvalue()
    assert (rig_bad_resume.run_ids(), rig_bad_resume.engines, assembled, cred_calls) == ([], [], [], [])
    assert loaded_tables == [expected_bad_tables]

    # 2. Step-2 refusal must not reach step 5's assembler.
    loaded_tables.clear()
    rig_step2 = Rig(tmp_path / "step2")
    assert (
        rig_step2.main("run", "missing_workflow", providers_loader=recording_loader, decision_assembler=recorder)
        == ExitCode.REFUSED
    )
    assert loaded_tables == [{}]
    assert assembled == []

    # 3. Valid config (and absent `[providers.*]`) reads providers once in step 1, assembles once in step 5.
    built_ports: list[tuple[DecisionRuntime, _FakeDecisionPort]] = []
    seen_ports: list[Any] = []

    async def capture_ports(session: Session) -> RunOutcome:
        seen_ports.append(session.ports.decision)
        return session.completed()

    def port_factory(
        runtime: DecisionRuntime, config: HarnessConfig, workspace: Workspace, clock: Clock, ids: IdSource
    ) -> _FakeDecisionPort:
        port = _FakeDecisionPort(runtime.summary)
        built_ports.append((runtime, port))
        return port

    good_toml = (
        "[providers.decision]\n"
        'base_url = "https://endpoint.example.test/v1"\n'
        'model = "m"\nmodel_version = "1"\nkey_ref = "ref-a"\nrequest_timeout_ms = 1500\n'
    )
    expected_good_tables = {
        "decision": {
            "base_url": "https://endpoint.example.test/v1",
            "model": "m",
            "model_version": "1",
            "key_ref": "ref-a",
            "request_timeout_ms": 1500,
        }
    }
    rig_ok = Rig(tmp_path / "ok", script=approves(wait=False))
    rig_ok.workspace.mkdir(parents=True)
    (rig_ok.workspace / "harness.toml").write_text(good_toml, encoding="utf-8")
    policies = {"pick_action": DecisionPolicy()}
    loaded_tables.clear()
    assert (
        rig_ok.main(
            "run",
            WORKFLOW,
            "--no-wait",
            "--no-report",
            "--progress",
            "off",
            providers_loader=recording_loader,
            decision_assembler=recorder,
            decision_port_factory=port_factory,
            point_policies=policies,
        )
        == ExitCode.AWAITING_ENGINEER
    )
    assert loaded_tables == [expected_good_tables]
    assert len(assembled) == 1
    assert assembled[0][0].decision is not None
    assert assembled[0][0].decision.model == "m"
    assert assembled[0][3] == policies
    assert len(built_ports) == 1
    assert built_ports[0][0].summary == {"providers": ["ok"]}
    assert "eng-harness: warn: test release finding\n" in rig_ok.err.getvalue()
    assert rig_ok.engines[0].ports.decision is built_ports[0][1]

    # Resume with `[providers.*]` reads the provider tables once, assembles once, and passes the decision port.
    [run_id] = rig_ok.run_ids()
    loaded_tables.clear()
    assembled.clear()
    built_ports.clear()
    rig_ok.script = capture_ports
    assert (
        rig_ok.main(
            "resume",
            run_id,
            "--no-report",
            "--progress",
            "off",
            providers_loader=recording_loader,
            decision_assembler=recorder,
            decision_port_factory=port_factory,
            point_policies=policies,
        )
        == ExitCode.OK
    )
    assert loaded_tables == [expected_good_tables]
    assert len(assembled) == 1
    assert assembled[0][0].decision is not None
    assert assembled[0][0].decision.model == "m"
    assert assembled[0][3] == policies
    assert seen_ports == [built_ports[0][1]]

    # Resume with no `[providers.*]` table still reads once (empty) and assembles the runtime once.
    rig_empty = Rig(tmp_path / "empty", script=approves(wait=False))
    rig_empty.workspace.mkdir(parents=True)
    (rig_empty.workspace / "harness.toml").write_text("", encoding="utf-8")
    assert (
        rig_empty.main(
            "run",
            WORKFLOW,
            "--no-wait",
            "--no-report",
            "--progress",
            "off",
            providers_loader=recording_loader,
            decision_assembler=recorder,
            decision_port_factory=port_factory,
            point_policies={},
        )
        == ExitCode.AWAITING_ENGINEER
    )
    [empty_run_id] = rig_empty.run_ids()
    loaded_tables.clear()
    assembled.clear()
    built_ports.clear()
    seen_ports.clear()
    rig_empty.script = capture_ports
    assert (
        rig_empty.main(
            "resume",
            empty_run_id,
            "--no-report",
            "--progress",
            "off",
            providers_loader=recording_loader,
            decision_assembler=recorder,
            decision_port_factory=port_factory,
            point_policies={},
        )
        == ExitCode.OK
    )
    assert loaded_tables == [{}]
    assert len(assembled) == 1
    assert assembled[0][0] == ProvidersConfig()
    assert seen_ports == [built_ports[0][1]]

    # 4. Missing decision collaborators keep `run` and `resume` unavailable (exit 2).
    for argv in (["run", WORKFLOW], ["resume", NO_RUN]):
        unavail = Rig(tmp_path / f"unavail_{argv[0]}")
        for missing in ("decision_assembler", "decision_port_factory", "point_policies"):
            assert unavail.main(*argv, **{missing: None}) == ExitCode.USAGE
            assert f"command {argv[0]} is not available in this build" in unavail.err.getvalue()
        assert (unavail.run_ids(), unavail.engines, unavail.runs.exists()) == ([], [], False)


def test_decisions_section_reaches_assembler(tmp_path: Path) -> None:
    seen: list[DecisionSettings] = []

    def recorder(
        providers: ProvidersConfig,
        settings: DecisionSettings,
        workspace: Workspace,
        policies: Mapping[str, DecisionPolicy],
    ) -> DecisionRuntime:
        seen.append(settings)
        return DecisionRuntime()

    rig = Rig(tmp_path / "good")
    rig.workspace.mkdir(parents=True)
    (rig.workspace / "harness.toml").write_text(
        "[decisions]\nmax_options = 12\nlocal_only = true\n\n"
        '[decisions.shadow_released.pick_action]\npoint_version = 2\nbasis = "owner"\nrecord = "B-100"\n',
        encoding="utf-8",
    )
    assert rig.main("run", WORKFLOW, "--no-report", "--progress", "off", decision_assembler=recorder) == ExitCode.OK
    assert seen == [
        DecisionSettings(
            max_options=12,
            local_only=True,
            shadow_released={"pick_action": ShadowRelease(point_version=2, basis="owner", record="B-100")},
        )
    ]

    for name, body, key in [
        ("bad_bound", "[decisions]\nmax_options = 0\n", "decisions.max_options"),
        ("bad_key", "[decisions]\nbogus = 1\n", "decisions.bogus"),
    ]:
        bad = Rig(tmp_path / name)
        bad.workspace.mkdir(parents=True)
        (bad.workspace / "harness.toml").write_text(body, encoding="utf-8")
        assert bad.main("run", WORKFLOW, "--no-report") == ExitCode.USAGE, name
        assert key in bad.err.getvalue(), (name, bad.err.getvalue())


def test_default_engine_factory_carries_decision_port(tmp_path: Path) -> None:
    import asyncio
    from typing import cast

    from eng_contract.ids import FixedClock, SeededIdSource
    from eng_contract.store import LocationClass, ResultStore
    from helpers.cli_deps import FakeCalc, FakeInput, FakeOutput, Placeholder
    from workflows.rig import Host

    from eng_harness._kinds import HARNESS_KINDS
    from eng_harness.basis import StoreBasisPort
    from eng_harness.block import Registry, workflow
    from eng_harness.cli._wiring import RunPortSet, default_engine_factory
    from eng_harness.engine import EngineSettings, RunRequest
    from eng_harness.journal import JournalReader
    from eng_harness.ports import ApprovalPort, CalcPort, InputPort, RunClass

    @workflow(name="noop_typed", version=1, description="Empty typed flow.")
    async def noop_typed(ctx: Any, inp: FakeInput) -> FakeOutput:
        return FakeOutput()

    clock = FixedClock(1_767_225_600_000, 1)
    ids = SeededIdSource(b"df", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    host = Host(ids, clock, workspace.root / "runs")

    ports = RunPortSet(
        tool=cast(Any, host),
        host=cast(Any, host),
        calc=cast(CalcPort, FakeCalc((), RunClass.TRIAL)),
        basis=StoreBasisPort(store),
        approvals=cast(ApprovalPort, Placeholder()),
        inputs=cast(InputPort, Placeholder()),
        decision=_FakeDecisionPort({"providers": ["real_engine"]}),
    )
    engine = default_engine_factory(workspace, Registry([noop_typed]), ports, store, EngineSettings(), clock, ids)
    outcome = asyncio.run(
        engine.start(RunRequest(workflow="noop_typed", input={}, basis_ref="res_" + "0" * 26, run_class=RunClass.TRIAL))
    )
    reader = JournalReader(workspace.root / "runs" / outcome.run_id)
    try:
        assert reader.header().decision_runtime == {"providers": ["real_engine"]}
    finally:
        reader.close()
