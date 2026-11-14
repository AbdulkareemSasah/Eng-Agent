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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.envelope import FailureEnvelope, Provenance, SuccessEnvelope
from eng_contract.errors import ErrorCode
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
    port = CliToolPort(config=config, store=store, launcher=PosixLauncher(), run_dir=run_dir, clock=clock)
    return Rig(port, store, tmp_path, run_dir, tools, artifact)


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
    payload = rig.store.get(envelope.result_id).payload
    assert payload["exit_code"] == 0
    assert payload["outputs"] == [
        {"name": "prepared.json", "sha256": _sha(output), "size_bytes": output.stat().st_size}
    ]
    assert payload["stdout_tail"].strip() == "prepare done"
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
