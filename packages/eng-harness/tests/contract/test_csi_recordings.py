"""Contract tests on recordings of the Sasaah CSI server (plan 0002 T17; spec 0002 AC34, sections 4.8.2, 4.8.3).

Every recording runs through the adapter (parse, map, envelope, kinds, the model-state read) and the synthetic fake
answers the recorded requests with the same reply shape and error codes (fake fidelity, process/05 section 4).
The recordings are the folders under `acceptance/recordings/` that hold a manifest (the owner commits them, spec
section 4.8.1), and the synthetic recording of the synthetic fake itself, made here through record mode. Under
spec 0002 AC34 (amendment B-573), these tests run on every applicable committed recording and on that synthetic
recording; the synthetic case keeps the code of both checks and of record mode exercised, while the real server is
verified only once the owner commits a recording (spec section 12 item 13). A real recording whose reply field names
differ from what the mappers read fails here, which is where the field names that local-testing item 5c lists get
pinned (OQ-G10).
"""

import hashlib
import json
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio
import pytest
from fakes.recorded import RecordedHost, UnmatchedRequestError
from fakes.recorded._checks import (
    adapter_problems,
    committed_recordings,
    fidelity_problems,
    shape,
    shape_differences,
)
from fakes.recorded._session import USER, record_synthetic

from eng_harness.adapters.csi import csi_allowlist
from eng_harness.servers import CallEffect, Sanitizer, verify_manifest

Change = Callable[[dict[str, Any]], None]


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The scripted session on the synthetic fake, recorded through record mode."""
    base = tmp_path_factory.mktemp("recorded")
    (base / "run").mkdir()
    record_synthetic(base / "recording", base / "run", tool_names=csi_allowlist().for_product("ETABS").tool_names)
    return base / "recording"


@pytest.fixture(
    params=[
        pytest.param(None, id="synthetic", marks=pytest.mark.synthetic),
        *(pytest.param(path, id=path.name, marks=pytest.mark.recorded) for path in committed_recordings()),
    ]
)
def recording(request: pytest.FixtureRequest, generated: Path) -> Path:
    """Each committed recording, and the synthetic fake's own."""
    return generated if request.param is None else Path(request.param)


def test_adapter_on_recordings(recording: Path, tmp_path: Path) -> None:
    """AC34: the adapter reads every recorded reply, the recorded tool list has the allowlist's fingerprint."""
    assert adapter_problems(RecordedHost(recording), tmp_path / "workspace") == []


def test_synthetic_matches_recordings(recording: Path, tmp_path: Path) -> None:
    """AC34: the synthetic fake gives the recorded reply shape and error code for every recorded operation."""
    run_dir = tmp_path / "fake"
    run_dir.mkdir()
    assert fidelity_problems(RecordedHost(recording), run_dir) == []


def _edited(directory: Path, tool: str, change: Change | None) -> Path:
    """A copy of `directory` whose first reply of `tool` has its body changed by `change`, or is removed (`None`)."""
    copy = directory.parent / f"{directory.name}-{tool}-{'drop' if change is None else 'edit'}"
    shutil.copytree(directory, copy, dirs_exist_ok=True)
    manifest = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    path = next(p for p in sorted(copy.glob("[0-9]*.json")) if p.name.endswith(f"-{tool}.json"))
    if change is None:
        path.unlink()
        del manifest["files"][path.name]
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        block = data["reply"]["content"][0]
        body = json.loads(block["text"])
        change(body)
        block["text"] = json.dumps(body)
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest["files"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return copy


def test_the_synthetic_recording(generated: Path) -> None:
    """The scripted session as recorded: all of it, sanitized, with a manifest that verifies and the pinned build."""
    assert verify_manifest(generated) == []
    host = RecordedHost(generated)
    tools = [e.tool for e in host.calls]
    assert tools[:4] == ["csi_status", "csi_launch", "csi_open_model", "csi_model_info"]
    assert tools.count("csi_model_info") == 2  # the model-state read reads the units before and after
    assert tools.count("csi_db_table_read") == 6  # and the Project Information read of the script is not among them
    assert tools[-3:] == ["csi_run_analysis", "csi_design_results", "csi_analysis_status"]
    assert host.manifest["tool_fingerprint"] == csi_allowlist().for_product("ETABS").tool_fingerprint
    assert host.manifest["adapter"] == "sasaah-csi-mcp"
    text = "".join(p.read_text(encoding="utf-8") for p in sorted(generated.glob("[0-9]*.json")))
    assert USER not in text
    assert "Tower" not in text
    assert "Project Information" not in text
    assert host.calls[2].arguments["path"] == "<path>/<model-1>.EDB"
    errors = {
        e.tool: json.loads(e.result["content"][0]["text"])["code"]
        for e in host.calls
        if e.result and e.result.get("isError")
    }
    assert errors == {"csi_run_analysis": "confirmation_required", "csi_design_results": "csi_error"}


def test_committed_recordings_are_the_folders_with_a_manifest(tmp_path: Path) -> None:
    for name, manifest in (("csi-b", True), ("csi-a", True), ("notes", False)):
        (tmp_path / name).mkdir()
        if manifest:
            (tmp_path / name / "manifest.json").write_text("{}", encoding="utf-8")
    assert committed_recordings(tmp_path) == [tmp_path / "csi-a", tmp_path / "csi-b"]
    assert committed_recordings(tmp_path / "missing") == []


def test_recorded_host_serves_in_recorded_order(generated: Path) -> None:
    """Equal requests are served in recorded order; one more than recorded is refused; the rest stays unused."""
    host = RecordedHost(generated)
    first, second = (e for e in host.calls if e.tool == "csi_model_info")
    assert host.take("csi_model_info", first.arguments) is first
    assert host.take("csi_model_info", first.arguments) is second
    with pytest.raises(UnmatchedRequestError, match="no recorded csi_model_info with arguments"):
        host.take("csi_model_info", first.arguments)
    assert {e.seq for e in host.unused()} == {e.seq for e in host.calls} - {first.seq, second.seq}


def test_recorded_host_serves_the_recorded_reply(generated: Path) -> None:
    host = RecordedHost(generated)
    reaction = next(e for e in host.calls if e.tool == "csi_results_joint_reactions")

    async def ask() -> Any:
        return await host.host_call("csi_results_joint_reactions", reaction.arguments, CallEffect.READ)

    assert anyio.run(ask)["items"][0]["joint"] == "J1"
    failing = next(e for e in host.calls if e.tool == "csi_run_analysis")

    async def refused() -> Any:
        return await host.call("csi", "main", "csi_run_analysis", failing.arguments, CallEffect.WRITE)

    assert anyio.run(refused).is_error is True


def test_recorded_host_refuses_an_unrecorded_request(generated: Path) -> None:
    host = RecordedHost(generated)

    async def ask() -> Any:
        return await host.call("csi", "main", "csi_launch", {"product": "SAFE"}, CallEffect.WRITE)

    with pytest.raises(
        UnmatchedRequestError, match=re.escape('no recorded csi_launch with arguments {"product":"SAFE"}')
    ):
        anyio.run(ask)


def test_recorded_host_sanitizes_live_arguments(generated: Path, tmp_path: Path) -> None:
    """With a sanitizer, a request that names the real path of the model is matched with the recorded one."""
    host = RecordedHost(generated, sanitizer=Sanitizer(tmp_path, user=USER, home="/home/" + USER))
    opened = host.calls[2]
    live = {**opened.arguments, "path": f"/home/{USER}/Clients/Acme Tower/Tower-A.EDB"}
    assert host.take("csi_open_model", live) is opened


def test_recorded_host_refuses_a_broken_manifest(generated: Path, tmp_path: Path) -> None:
    broken = tmp_path / "broken"
    shutil.copytree(generated, broken)
    (broken / "001-initialize.json").write_text("{}", encoding="utf-8")
    with pytest.raises(AssertionError, match=r"\['001-initialize.json: SHA-256 differs'\]"):
        RecordedHost(broken)


def test_recorded_error_raises_as_the_session_does(generated: Path, tmp_path: Path) -> None:
    from mcp import MCPError

    data = json.loads((generated / "001-initialize.json").read_text(encoding="utf-8"))
    data.pop("reply")
    data["error"] = {"code": -32602, "message": "bad"}
    data["method"], data["tool"] = "tools/call", "csi_status"
    data["request"] = {"name": "csi_status", "arguments": {}}
    copy = tmp_path / "copy"
    shutil.copytree(generated, copy)
    path = copy / "001-initialize.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    manifest = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    host = RecordedHost(copy)

    async def ask() -> Any:
        return await host.call("csi", "main", "csi_status", {}, CallEffect.READ)

    with pytest.raises(MCPError, match="bad"):
        anyio.run(ask)
    problems = adapter_problems(host, tmp_path / "workspace")
    assert "1 csi_status: recorded as a JSON-RPC error {'code': -32602, 'message': 'bad'}" in problems


def test_adapter_problems_are_found(generated: Path, tmp_path: Path) -> None:
    """A reply field a mapper needs, an unknown error code, an error without its data, a field of the status."""

    def problems(tool: str, change: Change | None) -> list[str]:
        return adapter_problems(RecordedHost(_edited(generated, tool, change)), tmp_path / f"w-{tool}")

    assert problems("csi_results_joint_reactions", lambda body: body.pop("items")) == [
        "21 csi_results_joint_reactions: the adapter cannot read the reply: "
        "HOST_ERROR: the host reply field items is not usable"
    ]
    assert problems("csi_analysis_status", lambda body: body["cases"][0].pop("status_code")) == [
        "24 csi_analysis_status: the adapter cannot read the reply: "
        "HOST_ERROR: analysis_status: the host reply has no field status_code"
    ]
    assert problems("csi_run_analysis", lambda body: body.update(code="brand_new_code")) == [
        "22 csi_run_analysis: the host error code brand_new_code is not in the error table"
    ]
    assert problems("csi_design_results", lambda body: body.pop("data")) == [
        "23 csi_design_results: an error reply without code, message and data"
    ]
    assert problems("csi_model_info", lambda body: body.update(units="kN_mm_C")) == [
        "model-state read: PRECONDITION_FAILED: the model's units changed during the read"
    ]
    [unmatched] = problems("csi_list_grids", None)
    assert unmatched.startswith("model-state read: no recorded csi_list_grids with arguments ")


def test_adapter_problems_of_the_tool_list(generated: Path, tmp_path: Path) -> None:
    """The manifest's fingerprint must be that of the recorded tool list, and the allowlist's."""
    copy = tmp_path / "copy"
    shutil.copytree(generated, copy)
    manifest = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    manifest["tool_fingerprint"] = "0" * 64
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert adapter_problems(RecordedHost(copy), tmp_path / "workspace") == [
        "the manifest's tool fingerprint is not that of the recorded tool list",
        "the recorded tool fingerprint is not the allowlist's",
    ]


def test_adapter_problem_of_a_tool_outside_the_allowlist(generated: Path, tmp_path: Path) -> None:
    copy = tmp_path / "copy"
    shutil.copytree(generated, copy)
    path = copy / "003-csi_status.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["tool"] = data["request"]["name"] = "csi_run_script"
    path.write_text(json.dumps(data), encoding="utf-8")
    manifest = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert adapter_problems(RecordedHost(copy), tmp_path / "workspace") == ["3 csi_run_script: not an allowlisted tool"]


def test_fidelity_problems_are_found(generated: Path, tmp_path: Path) -> None:
    """A recorded field the fake lacks, a recorded error code the fake does not give, and a recorded failure."""

    def problems(tool: str, change: Change) -> list[str]:
        run_dir = tmp_path / f"fake-{tool}"
        run_dir.mkdir()
        return fidelity_problems(RecordedHost(_edited(generated, tool, change)), run_dir)

    def extra_fields(body: dict[str, Any]) -> None:
        body["recorded_only"] = "x"
        body["items"][0]["extra"] = 1.0

    assert problems("csi_results_joint_reactions", extra_fields) == [
        "21 csi_results_joint_reactions.items[].extra: missing in the synthetic reply",
        "21 csi_results_joint_reactions.recorded_only: missing in the synthetic reply",
    ]
    assert problems("csi_run_analysis", lambda body: body.update(code="model_locked")) == [
        "22 csi_run_analysis: error code model_locked recorded, confirmation_required synthetic"
    ]


def test_fidelity_problem_when_only_one_side_failed(generated: Path, tmp_path: Path) -> None:
    copy = tmp_path / "copy"
    shutil.copytree(generated, copy)
    path = copy / "022-csi_run_analysis.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["reply"]["isError"] = False
    path.write_text(json.dumps(data), encoding="utf-8")
    manifest = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    run_dir = tmp_path / "fake"
    run_dir.mkdir()
    assert fidelity_problems(RecordedHost(copy), run_dir) == [
        "22 csi_run_analysis: recorded isError False, synthetic True"
    ]


@pytest.mark.parametrize(
    ("recorded", "synthetic", "expected"),
    [
        ({"a": 1}, {"a": 2.5}, []),
        ({"a": 1}, {"a": "x"}, [".a: recorded number, synthetic str"]),
        ({"a": True}, {"a": 1}, [".a: recorded bool, synthetic number"]),
        ({"a": None}, {"a": "x"}, [".a: recorded null, synthetic str"]),
        ({"a": 1, "b": 2}, {"a": 1}, [".b: missing in the synthetic reply"]),
        ({"a": 1}, {"a": 1, "c": 2}, [".c: not in the recorded reply"]),
        ({"rows": []}, {"rows": [{"x": 1}]}, []),
        ({"rows": [{"x": 1}]}, {"rows": []}, []),
        ({"rows": [{"x": 1}]}, {"rows": [{"x": "s"}]}, [".rows[].x: recorded number, synthetic str"]),
        ({"a": {"b": [1]}}, {"a": {"b": ["s"]}}, [".a.b[]: recorded number, synthetic str"]),
        ({"a": []}, {"a": {}}, [".a: recorded [], synthetic {}"]),
    ],
)
def test_shape_differences(recorded: object, synthetic: object, expected: list[str]) -> None:
    assert shape_differences(recorded, synthetic) == expected


def test_shape() -> None:
    assert shape({"a": [1, 2], "b": [], "c": None, "d": True, "e": 1.5, "f": "s", "g": {"h": []}}) == {
        "a": ["number"], "b": [], "c": "null", "d": "bool", "e": "number", "f": "str", "g": {"h": []},
    }  # fmt: skip


def _script() -> Any:
    """The owner's record script, loaded by path (it is not a package module)."""
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "acceptance" / "scripts" / "record_csi.py"
    spec = importlib.util.spec_from_file_location("record_csi", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _config(tmp_path: Path, control: Path) -> Path:
    """A `harness.toml` whose CSI server is the synthetic fake, pinned to the allowlist's commit."""
    import sys

    from fakes.recorded._session import SERVER

    quoted = json.dumps
    with Path(sys.executable).open("rb") as handle:
        exe = hashlib.file_digest(handle, "sha256").hexdigest()
    text = f"""
[servers.csi]
adapter = "sasaah-csi-mcp"
product = "ETABS"
command = {quoted(sys.executable)}
args = [{quoted(str(SERVER))}, "--disable-script"]
client_grace_s = 5
shutdown_grace_s = 5
host_key = "csi"
env = {{ SASAAH_CSI_FAKE_CONTROL = {quoted(str(control))} }}
build = {{ sasaah_commit = {quoted(csi_allowlist().sasaah_commit)}, exe_sha256 = {quoted(exe)} }}
roles = {{ main = {{ classes = ["session", "call"], call_timeout_s = 30 }} }}
"""
    path = tmp_path / "harness.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_record_script_on_the_synthetic_fake(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The owner's script, run against the fake, writes a recording that the two checks accept."""
    from fakes.recorded._session import SEED

    control = tmp_path / "control.json"
    control.write_text(json.dumps({"faults": [], "seed": SEED}), encoding="utf-8")
    model = tmp_path / "copy-of-Tower-A.EDB"
    model.write_bytes(b"")
    out, run_dir = tmp_path / "recordings", tmp_path / "run"
    config = _config(tmp_path, control)
    code = _script().main(
        ["--config", str(config), "--model", str(model), "--out", str(out), "--run-dir", str(run_dir), "--analysis"]
    )
    assert code == 0
    [folder] = committed_recordings(out)
    assert folder.name.startswith(f"sasaah-csi-mcp-{csi_allowlist().sasaah_commit[:12]}+")
    assert str(run_dir) in capsys.readouterr().out
    host = RecordedHost(folder)
    assert [e.tool for e in host.calls][-6:] == [
        "csi_run_analysis", "csi_analysis_status", "csi_results_joint_reactions", "csi_results_frame_forces",
        "csi_results_story_drifts", "csi_exit",
    ]  # fmt: skip
    assert "Tower-A" not in "".join(p.read_text(encoding="utf-8") for p in folder.glob("[0-9]*.json"))
    assert "Tower-A" in (run_dir / "recording-names.json").read_text(encoding="utf-8")
    assert adapter_problems(host, tmp_path / "workspace") == []
    (tmp_path / "fake").mkdir()
    assert fidelity_problems(host, tmp_path / "fake") == []


def test_record_script_reports_a_refusal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A refused step ends the script with exit code 1, and the recording is written all the same."""
    control = tmp_path / "control.json"
    control.write_text(
        json.dumps({"faults": [{"fault": "timeout_before_apply", "tool": "csi_model_info"}], "seed": {}})
    )
    model = tmp_path / "copy.EDB"
    model.write_bytes(b"")
    out = tmp_path / "recordings"
    code = _script().main(["--config", str(_config(tmp_path, control)), "--model", str(model), "--out", str(out)])
    assert code == 1
    assert "refused: csi_model_info" in capsys.readouterr().err
    [folder] = committed_recordings(out)
    assert verify_manifest(folder) == []


def test_record_script_usage(tmp_path: Path) -> None:
    control = tmp_path / "control.json"
    control.write_text(json.dumps({"faults": [], "seed": {}}))
    with pytest.raises(SystemExit) as stopped:
        _script().main(["--config", str(_config(tmp_path, control)), "--model", str(tmp_path / "missing.EDB")])
    assert stopped.value.code == 2


# --- SAFE product (plan 0008 T8; spec 0008 AC28, amendment B-573) ---


def _safe_recording_params() -> list[pytest.ParameterSet]:
    """Synthetic SAFE recording plus every committed recording whose fingerprint is SAFE's (B-573)."""
    try:
        from fakes.recorded._checks import applicable_recordings

        committed = applicable_recordings("SAFE")
    except ImportError:
        committed = []
    return [
        pytest.param(None, id="synthetic", marks=pytest.mark.synthetic),
        *(pytest.param(path, id=path.name, marks=pytest.mark.recorded) for path in committed),
    ]


@pytest.fixture(scope="module")
def generated_safe(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The scripted SAFE session on the synthetic fake, recorded through record mode."""
    from fakes.recorded._session import record_synthetic

    base = tmp_path_factory.mktemp("recorded-safe")
    (base / "run").mkdir()
    # product= is added in the feat commit; without it the base run fails for the right reason (TF004).
    record_synthetic(
        base / "recording",
        base / "run",
        tool_names=csi_allowlist().for_product("SAFE").tool_names,
        product="SAFE",
    )
    return base / "recording"


@pytest.fixture(params=_safe_recording_params())
def safe_recording(request: pytest.FixtureRequest, generated_safe: Path) -> Path:
    """Each committed SAFE recording, and the synthetic SAFE fake's own (AC28, B-573)."""
    return generated_safe if request.param is None else Path(request.param)


def test_safe_adapter_on_recordings(safe_recording: Path, tmp_path: Path) -> None:
    """AC28: the adapter reads every SAFE recorded reply; the recorded tool list has the SAFE fingerprint."""
    assert adapter_problems(RecordedHost(safe_recording), tmp_path / "workspace", product="SAFE") == []


def test_safe_synthetic_matches_recordings(safe_recording: Path, tmp_path: Path) -> None:
    """AC28: the synthetic SAFE fake gives the recorded reply shape and error codes for every recorded operation."""
    run_dir = tmp_path / "fake"
    run_dir.mkdir()
    assert fidelity_problems(RecordedHost(safe_recording), run_dir, product="SAFE") == []


# --- SAP2000 product (plan 0012 T7; spec 0012 AC19, amendment B-573) ---


def _sap2000_recording_params() -> list[pytest.ParameterSet]:
    """Synthetic SAP2000 recording plus every committed recording whose fingerprint is SAP2000's (B-573)."""
    try:
        from fakes.recorded._checks import applicable_recordings

        committed = applicable_recordings("SAP2000")
    except ImportError:
        committed = []
    return [
        pytest.param(None, id="synthetic", marks=pytest.mark.synthetic),
        *(pytest.param(path, id=path.name, marks=pytest.mark.recorded) for path in committed),
    ]


@pytest.fixture(scope="module")
def generated_sap2000(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The scripted SAP2000 session on the synthetic fake, recorded through record mode."""
    # SAP2000_SEED lands in the feat commit; missing name fails at the base (TF004).
    from fakes.recorded._session import SAP2000_SEED, record_synthetic

    assert "frames" in SAP2000_SEED
    base = tmp_path_factory.mktemp("recorded-sap2000")
    (base / "run").mkdir()
    record_synthetic(
        base / "recording",
        base / "run",
        tool_names=csi_allowlist().for_product("SAP2000").tool_names,
        product="SAP2000",
    )
    return base / "recording"


@pytest.fixture(params=_sap2000_recording_params())
def sap2000_recording(request: pytest.FixtureRequest, generated_sap2000: Path) -> Path:
    """Each committed SAP2000 recording, and the synthetic SAP2000 fake's own (AC19, B-573)."""
    return generated_sap2000 if request.param is None else Path(request.param)


def test_sap2000_adapter_on_recordings(sap2000_recording: Path, tmp_path: Path) -> None:
    """AC19: the adapter reads every SAP2000 recorded reply; the recorded tool list has the SAP2000 fingerprint."""
    assert adapter_problems(RecordedHost(sap2000_recording), tmp_path / "workspace", product="SAP2000") == []


def test_sap2000_synthetic_matches_recordings(sap2000_recording: Path, tmp_path: Path) -> None:
    """AC19: the synthetic SAP2000 fake gives the recorded reply shape and error codes for every recorded operation."""
    run_dir = tmp_path / "fake"
    run_dir.mkdir()
    assert fidelity_problems(RecordedHost(sap2000_recording), run_dir, product="SAP2000") == []
