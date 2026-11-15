"""The command-line tool adapter against the Python stand-in of the scripts (plan 0002 T16; spec 0002 AC6, AC31, AC32).

The stand-in (`tests/fakes/sasaah_cli/`) is started by the harness's own launcher through a shell wrapper that takes
the PowerShell switches, in a tool job. Each stand-in echoes the arguments it received into its output file, so the
expectations are derived by hand from spec 4.7: millimetres reach the tool as metres (5 mm is 0.005 m), file inputs are
hashed with SHA-256 before the run, the configuration copy carries the attempt folder as `outputFolder` and absolute
`dxf` and `templateE2k` paths. The adapter imports are inside the tests so a missing module fails the test.
"""

import hashlib
import json
import shutil
import stat
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import anyio
import pytest
from eng_contract.envelope import FailureEnvelope, Provenance, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace

from eng_harness.servers import ServersConfig

FAKES = Path(__file__).resolve().parents[2] / "fakes" / "sasaah_cli"
OP = "op_0123456789abcdef0123456789abcdef"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class Rig:
    """The adapter port over the stand-ins, with the files a test arms and reads."""

    port: Any
    launcher: Any
    config: ServersConfig
    store: ResultStore
    root: Path
    run_dir: Path
    tools: Path
    artifact: Path

    def arm(self, **fault: object) -> None:
        (self.tools / "control.json").write_text(json.dumps(fault))

    def value(self, name: str, number: float) -> dict[str, str]:
        producer = Provenance(
            tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0
        )
        record = self.store.put("harness.run_input/1", {"value": {name: number}}, producer)
        return {"$ref": f"{record.result_id}#/value/{name}"}

    def attempt(self, op_id: str = OP) -> Path:
        return self.run_dir / "tools" / op_id


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    from eng_harness._kinds import HARNESS_KINDS
    from eng_harness.adapters.cli import CLI_KINDS, CliToolPort
    from eng_harness.servers._launcher import PosixLauncher

    tools = tmp_path / "tools"
    shutil.copytree(FAKES, tools)
    shell = tmp_path / "pwsh"  # takes the PowerShell switches, runs the script in Python
    shell.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{tools / "pwsh.py"}" "$@"\n')
    shell.chmod(shell.stat().st_mode | stat.S_IXUSR)
    artifact = tmp_path / "prep.exe"
    artifact.write_bytes(b"cached-cli-v1")
    pin = {"path": str(artifact), "sha256": _sha(artifact)}

    def entry(script: str, outputs: list[str], timeout_s: int = 20) -> dict[str, Any]:
        return {
            "shell": str(shell), "script": str(tools / script), "outputs": outputs, "timeout_s": timeout_s,
            "build_artifacts": [pin],
        }  # fmt: skip

    config = ServersConfig.model_validate(
        {
            "cli_tools": {
                "dxf-prep/prepare": entry("run_prepare.py", ["prepared.json"]),
                "dxf-prep/inspect": entry("run_inspect.py", ["inspection.json"], timeout_s=1),  # the timeout test
                "etabs-model/build": entry("run_build.py", ["model.json"]),
            }
        }
    )
    clock = FixedClock(1_767_225_600_000, 1)
    ids = SeededIdSource(b"cli", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    store = ResultStore(workspace, HARNESS_KINDS.extend(CLI_KINDS), ids, clock)
    run_dir = tmp_path / "run"
    launcher = PosixLauncher()
    port = CliToolPort(config=config, store=store, launcher=launcher, run_dir=run_dir, clock=clock)
    return Rig(port, launcher, config, store, tmp_path, run_dir, tools, artifact)


def test_prepare_outputs_hashed(rig: Rig) -> None:
    """AC31: the input is hashed, the tool runs in a fresh attempt folder and its declared output is hashed."""
    dxf = rig.root / "plan.dxf"
    dxf.write_bytes(b"0\nSECTION\n")

    async def body() -> SuccessEnvelope:
        args = {"dxf": str(dxf), "SnapTol_mm": rig.value("SnapTol_mm", 5.0)}
        envelope = await rig.port.call("dxf-prep/prepare", args, op_id=OP, model=None)
        assert isinstance(envelope, SuccessEnvelope), envelope
        return envelope

    envelope = anyio.run(body)
    attempt = rig.attempt()
    output = attempt / "prepared.json"
    assert envelope.kind == "harness.cli_run/1"
    assert envelope.provenance.tool == "dxf-prep/prepare"
    assert [(f.name, f.sha256, f.size_bytes) for f in envelope.provenance.files] == [("plan.dxf", _sha(dxf), 10)]
    payload = rig.store.get(envelope.result_id).payload or {}
    assert payload["exit_code"] == 0
    assert payload["outputs"] == [
        {"name": "prepared.json", "sha256": _sha(output), "size_bytes": output.stat().st_size}
    ]
    assert payload["stdout_tail"] == "prepare done\n"
    assert "stdout_tail" not in envelope.summary
    echoed = json.loads(output.read_text())["args"]
    assert echoed == {"OutDir": str(attempt), "Dxf": str(dxf), "SnapTol": "0.005"}  # 5 mm is 0.005 m


def test_build_config_and_pins(rig: Rig) -> None:
    """AC32: the configuration copy is rewritten, an existing output is kept, a changed pinned artifact fails."""
    folder = rig.root / "inputs"
    folder.mkdir()
    (folder / "plan.dxf").write_bytes(b"dxf")
    (folder / "tpl.e2k").write_bytes(b"template")
    original = folder / "build.json"
    original.write_text(json.dumps({"dxf": "plan.dxf", "templateE2k": "tpl.e2k", "outputFolder": "elsewhere", "n": 3}))
    before = original.read_bytes()

    async def build(op_id: str) -> Any:
        return await rig.port.call("etabs-model/build", {"config": str(original)}, op_id=op_id, model="m")

    ok = anyio.run(build, OP)
    assert isinstance(ok, SuccessEnvelope), ok
    attempt = rig.attempt()
    config = json.loads((attempt / "model.json").read_text())["config"]
    assert config == {
        "dxf": str(folder / "plan.dxf"), "templateE2k": str(folder / "tpl.e2k"), "outputFolder": str(attempt), "n": 3
    }  # fmt: skip
    assert original.read_bytes() == before  # the engineer's file is never touched
    hashed = {f.name: f.sha256 for f in ok.provenance.files}
    assert hashed == {
        "build.json": _sha(original),
        "plan.dxf": _sha(folder / "plan.dxf"),
        "tpl.e2k": _sha(folder / "tpl.e2k"),
    }

    kept = (attempt / "model.json").read_bytes()
    again = anyio.run(build, OP)  # the same attempt folder again: nothing is overwritten
    assert isinstance(again, FailureEnvelope)
    assert again.error.code is ErrorCode.CONFLICT
    assert (attempt / "model.json").read_bytes() == kept

    rig.arm(touch_artifact=str(rig.artifact))  # the wrapper rebuilds its cached executable during the call
    changed = anyio.run(build, "op_fedcba9876543210fedcba9876543210")
    assert isinstance(changed, FailureEnvelope)
    assert changed.error.code is ErrorCode.HOST_ERROR
    assert changed.error.host_code == "BUILD_CHANGED"
    assert "prep.exe" in changed.error.message


def test_timeout_no_effect(rig: Rig) -> None:
    """AC6: a tool that outlives `timeout_s` is ended with its job and the step fails `TIMEOUT_NO_EFFECT`."""
    dxf = rig.root / "plan.dxf"
    dxf.write_bytes(b"x")
    rig.arm(sleep=60)

    async def body() -> FailureEnvelope:
        envelope = await rig.port.call("dxf-prep/inspect", {"dxf": str(dxf)}, op_id=OP, model=None)
        assert isinstance(envelope, FailureEnvelope), envelope
        return envelope

    began = time.monotonic()
    failure = anyio.run(body)
    assert time.monotonic() - began < 30  # the sleeping stand-in was ended, not waited for
    assert failure.error.code is ErrorCode.TIMEOUT_NO_EFFECT
    assert not (rig.attempt() / "complete.json").exists()


def _call(rig: Rig, tool: str, args: dict[str, Any], op_id: str = OP) -> Any:
    async def body() -> Any:
        return await rig.port.call(tool, args, op_id=op_id, model=None)

    return anyio.run(body)


def _fail_code(envelope: Any) -> tuple[ErrorCode, str | None]:
    assert isinstance(envelope, FailureEnvelope), envelope
    return envelope.error.code, envelope.error.host_code


@pytest.mark.parametrize(
    ("tool", "exit_code", "expected"),
    [
        ("dxf-prep/inspect", 1, (ErrorCode.INVALID_ARGUMENT, None)),  # S-12 section 12: usage
        ("dxf-prep/inspect", 2, (ErrorCode.INVALID_ARGUMENT, None)),  # unreadable input
        ("dxf-prep/inspect", 3, (ErrorCode.HOST_ERROR, "3")),  # failed
        ("etabs-model/build", 1, (ErrorCode.HOST_ERROR, "1")),  # failure
        ("etabs-model/build", 2, (ErrorCode.INVALID_ARGUMENT, None)),  # usage
    ],
)
def test_exit_codes_map(rig: Rig, tool: str, exit_code: int, expected: tuple[ErrorCode, str | None]) -> None:
    """Spec 4.7: the documented failure exits of each tool map to the codes of the table."""
    (rig.root / "plan.dxf").write_bytes(b"x")
    (rig.root / "b.json").write_text("{}")
    args = {"config": str(rig.root / "b.json")} if tool.startswith("etabs") else {"dxf": str(rig.root / "plan.dxf")}
    rig.arm(exit=exit_code)
    envelope = _call(rig, tool, args)
    assert _fail_code(envelope) == expected
    assert isinstance(envelope, FailureEnvelope)
    assert envelope.error.hint == "stand-in failure\n"  # the stderr tail reaches the engineer
    assert not (rig.attempt() / "complete.json").exists()


def test_bad_input_leaves_no_attempt_folder(rig: Rig) -> None:
    """A refused input is not an attempt: the folder is not created, so the same `op_id` can be retried."""
    for args in ({"dxf": "relative.dxf"}, {"dxf": str(rig.root / "missing.dxf")}, {"dxf": str(rig.root), "x": 1}):
        envelope = _call(rig, "dxf-prep/inspect", args)
        assert _fail_code(envelope)[0] is ErrorCode.INVALID_ARGUMENT
    assert not rig.attempt().exists()
    literal = {"dxf": str(rig.root), "SnapTol_mm": 5.0}  # an engineering quantity is a reference, never a literal
    assert _fail_code(_call(rig, "dxf-prep/prepare", literal))[0] is ErrorCode.INVALID_ARGUMENT
    assert not rig.attempt().exists()


def test_bad_build_configuration(rig: Rig) -> None:
    """A configuration that is not an object, names a missing input or a non-path is refused before any run."""
    cases = ["[]", "not json", json.dumps({"dxf": 3}), json.dumps({"dxf": "absent.dxf"})]
    for text in cases:
        path = rig.root / "bad.json"
        path.write_text(text)
        envelope = _call(rig, "etabs-model/build", {"config": str(path)})
        assert _fail_code(envelope)[0] is ErrorCode.INVALID_ARGUMENT
    assert not rig.attempt().exists()


def test_pin_checked_before_the_run(rig: Rig) -> None:
    """An artifact that already differs from its pin stops the step before anything runs."""
    rig.artifact.write_bytes(b"other")
    (rig.root / "plan.dxf").write_bytes(b"x")
    envelope = _call(rig, "dxf-prep/inspect", {"dxf": str(rig.root / "plan.dxf")})
    assert _fail_code(envelope) == (ErrorCode.HOST_ERROR, "BUILD_CHANGED")
    assert not rig.attempt().exists()
    rig.artifact.unlink()  # a missing artifact is a changed one
    envelope = _call(rig, "dxf-prep/inspect", {"dxf": str(rig.root / "plan.dxf")})
    assert _fail_code(envelope) == (ErrorCode.HOST_ERROR, "BUILD_CHANGED")


def test_describe_and_reconcile(rig: Rig) -> None:
    """Tool infos, the unreleased list, reconciliation by the completion record and the absent read-back."""
    from eng_harness.adapters.cli import CliToolPort

    async def body() -> None:
        prepare, build = await rig.port.describe("dxf-prep/prepare"), await rig.port.describe("etabs-model/build")
        assert (prepare.effect, prepare.action, prepare.host_key) == ("read", "plain", "dxf-prep")
        assert prepare.engineering_params == ("SnapTol_mm", "BeamSpacing_mm", "ColumnGrow_mm")
        assert (build.effect, build.host_key, build.engineering_params) == ("write", "etabs-model", ())
        assert rig.port.unreleased_tools() == {}
        assert rig.port.supports_reconcile("etabs-model/build")
        assert not rig.port.supports_reconcile("dxf-prep/prepare")
        assert not rig.port.supports_reconcile("nothing/here")
        assert (await rig.port.reconcile("etabs-model/build", {}, OP)).outcome == "not_applied"
        rig.attempt().mkdir(parents=True)
        (rig.attempt() / "complete.json").write_text("{}")
        assert (await rig.port.reconcile("etabs-model/build", {}, OP)).outcome == "applied"
        assert await rig.port.read_back("etabs-model/build", {}) is None
        calls: list[Callable[[], Awaitable[Any]]] = [
            lambda: rig.port.describe("x/y"),
            lambda: rig.port.reconcile("dxf-prep/prepare", {}, OP),
            lambda: rig.port.read_back("x/y", {}),
        ]
        for call in calls:
            with pytest.raises(ContractError) as raised:
                await call()
            assert raised.value.detail.code is ErrorCode.INVALID_ARGUMENT
        with pytest.raises(ContractError):
            await rig.port.call("x/y", {}, op_id=OP, model=None)

    anyio.run(body)
    with pytest.raises(ValueError, match="no command-line adapter for other/tool"):
        CliToolPort(
            config=ServersConfig.model_validate(
                {"cli_tools": {"other/tool": {"shell": "/s", "script": "/t", "timeout_s": 1}}}
            ),
            store=rig.store, launcher=rig.launcher, run_dir=rig.run_dir, clock=FixedClock(0, 1),
        )  # fmt: skip


def test_launch_failure_is_an_envelope(rig: Rig, tmp_path: Path) -> None:
    """A shell that cannot be started fails the step with `LAUNCH_FAILED`."""
    from eng_harness.adapters.cli import CliToolPort

    tool = {"shell": str(tmp_path / "absent"), "script": str(rig.tools / "run_inspect.py"), "timeout_s": 5}
    port = CliToolPort(
        config=ServersConfig.model_validate({"cli_tools": {"dxf-prep/inspect": tool}}),
        store=rig.store, launcher=rig.launcher, run_dir=rig.run_dir, clock=FixedClock(0, 1),
    )  # fmt: skip
    (tmp_path / "plan.dxf").write_bytes(b"x")
    envelope = anyio.run(
        lambda: port.call("dxf-prep/inspect", {"dxf": str(tmp_path / "plan.dxf")}, op_id=OP, model=None)
    )
    assert _fail_code(envelope) == (ErrorCode.HOST_ERROR, "LAUNCH_FAILED")


def test_surviving_host_process_is_a_warning(rig: Rig) -> None:
    """A host-program process that appears during the step and outlives it is reported, never killed."""
    from eng_harness.adapters.cli import CliToolPort
    from eng_harness.servers._procinfo import ProcessIdentity, ProcessInspector

    class Inspector:
        def __init__(self) -> None:
            self.calls = 0

        def snapshot(self, exe_names: list[str]) -> list[ProcessIdentity]:
            self.calls += 1
            assert exe_names == ["ETABS.exe"]
            rows = [ProcessIdentity(pid=100, started_at="a", exe_name="ETABS.exe")]
            return rows if self.calls == 1 else [*rows, ProcessIdentity(pid=7, started_at="b", exe_name="ETABS.exe")]

    base = rig.config.model_dump()
    config = ServersConfig.model_validate({**base, "host_programs": {"etabs": {"executables": ["ETABS.exe"]}}})
    port = CliToolPort(
        config=config, store=rig.store, launcher=rig.launcher, run_dir=rig.run_dir,
        clock=FixedClock(0, 1), inspector=cast("ProcessInspector", Inspector()),
    )  # fmt: skip
    (rig.root / "plan.dxf").write_bytes(b"x")
    envelope = anyio.run(
        lambda: port.call("dxf-prep/prepare", {"dxf": str(rig.root / "plan.dxf")}, op_id=OP, model=None)
    )
    assert isinstance(envelope, SuccessEnvelope), envelope
    assert [(w.code.value, w.message) for w in envelope.warnings] == [
        ("HOST_WARNING", "host-program processes outlived the tool: pid 7")
    ]
