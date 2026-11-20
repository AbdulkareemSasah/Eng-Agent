"""Contract tests on recordings of the Sasaah Revit server (plan 0011 T13; spec 0011 AC31, section 4.13).

Every recording runs through the adapter (parse, map, kinds, the model-state read) and the synthetic fake answers the
recorded requests with the same reply shape and error codes (fake fidelity, process/05 section 4). The recordings are
the folders under `acceptance/recordings/` whose tool fingerprint is the Revit allowlist's (the owner commits them,
spec section 12 item L15; amendment B-573), and the synthetic recording of the synthetic Revit fake itself, made here
through record mode. Under AC31 (amendment B-573), these tests run on every applicable committed recording and on that
synthetic recording; the real server is verified only once the owner commits a recording.
"""

from pathlib import Path

import pytest
from fakes.recorded import RecordedHost


def _revit_recording_params() -> list[pytest.ParameterSet]:
    """Synthetic Revit recording plus every committed recording whose fingerprint is Revit's write role (B-573)."""
    try:
        from fakes.recorded._checks import applicable_revit_recordings

        committed = applicable_revit_recordings()
    except ImportError:
        committed = []
    return [
        pytest.param(None, id="synthetic", marks=pytest.mark.synthetic),
        *(pytest.param(path, id=path.name, marks=pytest.mark.recorded) for path in committed),
    ]


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The scripted session on the synthetic Revit fake, recorded through record mode."""
    from fakes.recorded._session import record_revit_synthetic

    from eng_harness.adapters.revit import revit_allowlist

    base = tmp_path_factory.mktemp("recorded-revit")
    (base / "run").mkdir()
    # record_revit_synthetic is added in the feat commit; without it the base run fails for the right reason (TF004).
    record_revit_synthetic(
        base / "recording",
        base / "run",
        tool_names=revit_allowlist(role="write").tool_names,
    )
    return base / "recording"


@pytest.fixture(params=_revit_recording_params())
def recording(request: pytest.FixtureRequest, generated: Path) -> Path:
    """Each committed Revit recording, and the synthetic Revit fake's own (AC31, B-573)."""
    return generated if request.param is None else Path(request.param)


def test_adapter_on_recordings(recording: Path, tmp_path: Path) -> None:
    """AC31: the adapter reads every recorded reply; the recorded tool list has the allowlist fingerprint."""
    from fakes.recorded._checks import revit_adapter_problems

    assert revit_adapter_problems(RecordedHost(recording), tmp_path / "workspace") == []


def test_synthetic_matches_recordings(recording: Path, tmp_path: Path) -> None:
    """AC31: the synthetic Revit fake gives the recorded reply shape and error codes for every recorded operation."""
    from fakes.recorded._checks import revit_fidelity_problems

    run_dir = tmp_path / "fake"
    run_dir.mkdir()
    assert revit_fidelity_problems(RecordedHost(recording), run_dir) == []


def test_the_synthetic_recording(generated: Path) -> None:
    """The scripted Revit session as recorded: sanitized, with a manifest that verifies and the pinned build."""
    from fakes.recorded._session import USER

    from eng_harness.adapters.revit import revit_allowlist
    from eng_harness.servers import verify_manifest

    assert verify_manifest(generated) == []
    host = RecordedHost(generated)
    tools = [e.tool for e in host.calls]
    assert tools[0] == "revit_open_model"
    assert "revit_connection_status" in tools
    assert tools.count("revit_get_model_metadata") >= 1
    assert host.manifest["tool_fingerprint"] == revit_allowlist(role="write").tool_fingerprint
    assert host.manifest["adapter"] == "sasaah-revit-mcp"
    text = "".join(p.read_text(encoding="utf-8") for p in sorted(generated.glob("[0-9]*.json")))
    assert USER not in text
    assert "Acme" not in text
    assert "Tower" not in text
    opened = next(e for e in host.calls if e.tool == "revit_open_model")
    assert opened.arguments["path"] == "<path>/<model-1>.rvt"


def test_committed_revit_recordings_are_fingerprint_filtered(tmp_path: Path) -> None:
    from fakes.recorded._checks import applicable_revit_recordings

    from eng_harness.adapters.revit import revit_allowlist

    write_fp = revit_allowlist(role="write").tool_fingerprint
    for name, fingerprint in (("revit-a", write_fp), ("revit-b", "other"), ("notes", None)):
        folder = tmp_path / name
        folder.mkdir()
        if fingerprint is not None:
            (folder / "manifest.json").write_text(
                f'{{"tool_fingerprint": "{fingerprint}", "files": {{}}}}', encoding="utf-8"
            )
    assert applicable_revit_recordings(tmp_path) == [tmp_path / "revit-a"]
