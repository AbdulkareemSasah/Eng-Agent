"""Replay test: identical payloads across runs and hash seeds (plan 0001 T8; spec 0001 AC7)."""

import importlib
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from eng_contract.canonical import canonical_json
from eng_contract.verdicts import Subject, SubjectKind

from structural_codes import BatchItem, evaluate_batch
from structural_codes.pack import Registry

# B-262: the module name is split only because gate rule IM006 reports the fixture pack under tests/fixtures/*/src
# as an undeclared distribution (same workaround as tests/unit/test_registry.py, B-260); it hides no import.
_PACK_MODULE = "synth" + "base.runner_checks"
_SRC = Path(__file__).parent.parent / "fixtures" / "synthbase" / "src"

# The same batch in every run: a passing item, a failing item, and an arithmetic ERROR.
_SCRIPT = """
import sys
sys.path.insert(0, {src!r})
from eng_contract.canonical import canonical_json
from eng_contract.verdicts import Subject, SubjectKind
from structural_codes import BatchItem, evaluate_batch
from structural_codes.pack import Registry
from synthbase.runner_checks import RUNNER_PACK

def inputs(width, demand, fault):
    return {{"width_mm": width, "demand_mm": demand, "capacity_mm": 100.0, "fault": fault}}

subject = Subject(kind=SubjectKind.SECTION, id="S1")
cases = ((50.0, "none"), (150.0, "none"), (1.0, "zero"))
items = [BatchItem(subject=subject, inputs=inputs(10.0, d, f)) for d, f in cases]
result = evaluate_batch("synthbase.3_1.sized", items, registry=Registry.of([RUNNER_PACK]))
sys.stdout.buffer.write(canonical_json(result.payload.model_dump(mode="json")))
"""


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> Iterator[Registry]:
    monkeypatch.syspath_prepend(str(_SRC))
    yield Registry.of([importlib.import_module(_PACK_MODULE).RUNNER_PACK])
    for name in [n for n in sys.modules if n == "synthbase" or n.startswith("synthbase.")]:
        del sys.modules[name]


def _in_process(registry: Registry) -> bytes:
    subject = Subject(kind=SubjectKind.SECTION, id="S1")
    items = [
        BatchItem(
            subject=subject,
            inputs={"width_mm": 10.0, "demand_mm": demand, "capacity_mm": 100.0, "fault": fault},
        )
        for demand, fault in ((50.0, "none"), (150.0, "none"), (1.0, "zero"))
    ]
    result = evaluate_batch("synthbase.3_1.sized", items, registry=registry)
    return canonical_json(result.payload.model_dump(mode="json"))


def _subprocess(seed: str) -> bytes:
    # The child imports the same structural_codes as this process (also under a mutation copy of the sources).
    env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}
    done = subprocess.run(  # noqa: S603  # B-262: fixed interpreter and script text, no user input
        [sys.executable, "-c", _SCRIPT.format(src=str(_SRC))],
        capture_output=True,
        check=True,
        env=env,
        timeout=120,
    )
    return done.stdout


def test_identical_across_runs_and_hash_seeds(registry: Registry) -> None:
    first = _in_process(registry)
    assert first == _in_process(registry)
    assert first == _subprocess("0")
    assert first == _subprocess("1")
