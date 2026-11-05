"""Replay test: the payloads do not depend on the hash seed (plan 0002 T9; PK-AC7)."""

import os
import subprocess  # noqa: S404  # B-278: the test runs this interpreter with a fixed environment
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
for check in PACK.checks:
    case = next(c for c in CaseFile.load(Path(sys.argv[1]) / (check.meta.check_id + ".yaml")).cases if c.id == "HC-1")
    payload = evaluate(check.meta.check_id, case.inputs, subject=case.subject, registry=registry).payload
    sys.stdout.write(canonical_json(payload.model_dump(mode="json")) + "\\n")
"""


def _run(seed: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": seed}
    done = subprocess.run(  # noqa: S603  # B-278: fixed arguments, no shell, no untrusted input
        [sys.executable, "-c", _SCRIPT, str(_CASES)], env=env, capture_output=True, text=True, check=True
    )
    return done.stdout


def test_identical_across_hash_seeds() -> None:
    """Canonical JSON of all six payloads is byte-identical under PYTHONHASHSEED 0 and 1 (PK-AC7)."""
    first = _run("0")
    assert len(first.splitlines()) == 6
    assert first == _run("1")
