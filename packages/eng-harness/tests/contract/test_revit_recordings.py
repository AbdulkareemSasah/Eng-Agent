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
    from eng_harness.adapters.revit import revit_allowlist
    from fakes.recorded._session import record_revit_synthetic

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
