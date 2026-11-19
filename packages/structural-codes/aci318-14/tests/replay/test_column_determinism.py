"""Replay test: the column payloads do not depend on the hash seed (plan 0004 T5; CK-AC6)."""

import os
import subprocess  # B-334: the test runs this interpreter with a fixed environment
import sys
from pathlib import Path

_CASES = Path(__file__).parents[1] / "data" / "golden" / "verification"
_SCRIPT = """
import sys
from pathlib import Path
from eng_contract.canonical import canonical_json
from structural_codes import evaluate
from structural_codes.pack import Registry
from structural_codes.verification import CaseFile
from aci318_14 import PACK

registry = Registry.of([PACK])
for check_id in sys.argv[2:]:
    case = next(c for c in CaseFile.load(Path(sys.argv[1]) / (check_id + ".yaml")).cases if c.id == "HC-1")
    payload = evaluate(check_id, case.inputs, subject=case.subject, registry=registry).payload
    sys.stdout.buffer.write(canonical_json(payload.model_dump(mode="json")) + b"\\n")
"""
_IDS = [
    "aci318_14.22_4_2_1.max_axial_strength",
    "aci318_14.22_4_1_1.axial_flexure_uniaxial",
    "aci318_14.10_6_1_1.longitudinal_reinforcement_limits",
]


def _run(seed: str) -> bytes:
    env = {**os.environ, "PYTHONHASHSEED": seed}
    done = subprocess.run(  # noqa: S603  # B-334: fixed arguments, no shell, no untrusted input
        [sys.executable, "-c", _SCRIPT, str(_CASES), *_IDS], env=env, capture_output=True, check=True
    )
    return done.stdout


def test_identical_across_hash_seeds() -> None:
    """Canonical JSON of the three column payloads is byte-identical under PYTHONHASHSEED 0 and 1 (CK-AC6)."""
    first = _run("0")
    assert len(first.splitlines()) == len(_IDS)
    assert first == _run("1")
