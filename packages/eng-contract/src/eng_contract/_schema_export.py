"""JSON Schema snapshot exporter (spec 4.12).

Purpose: writes the schema of every public model and kind, the unit table and the error codes into a folder.
Run `uv run python -m eng_contract._schema_export docs/schema` to regenerate; AC51 fails when the files are stale.
Errors: `OSError` when the folder cannot be written.
"""

import json
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from eng_contract.cited import Cited
from eng_contract.errors import RETRY_RULES, ErrorDetail
from eng_contract.issues import ModelIssue
from eng_contract.kinds import NEUTRAL_KINDS
from eng_contract.mcp import output_schema
from eng_contract.quantity import Quantity
from eng_contract.records import ResultRecord
from eng_contract.refs import Ref
from eng_contract.store import ModelState
from eng_contract.trace import Trace
from eng_contract.units import UNITS
from eng_contract.verdicts import Verdict

_MODELS: dict[str, type[BaseModel]] = {
    "result-record": ResultRecord,
    "error-detail": ErrorDetail,
    "ref": Ref,
    "quantity": Quantity,
    "cited": Cited,
    "verdict": Verdict,
    "model-issue": ModelIssue,
    "trace": Trace,
    "model-state": ModelState,
}
_SOURCE = "docs/verification/units.md"  # per-factor citations live in the comments of _unit_table.py (gap G-4)


def _frac(value: Fraction) -> str:
    return str(value)


def _dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_bytes(text.encode("utf-8"))


def write_all(folder: Path) -> None:
    """Write every snapshot file into `folder` (created if absent): sorted keys, two-space indent, final newline."""
    _dump(folder / "envelope.schema.json", output_schema())
    for name, model in _MODELS.items():
        _dump(folder / f"{name}.schema.json", model.model_json_schema())
    for kind, model in NEUTRAL_KINDS.items():
        _dump(folder / "kinds" / f"{kind.replace('/', '-')}.schema.json", model.model_json_schema())
    units = [
        {
            "symbol": u.symbol,
            "dimension": u.dimension._asdict(),
            "factor": _frac(u.factor),
            "pi_power": u.pi_power,
            "offset": _frac(u.offset),
            "source": _SOURCE,
        }
        for u in sorted(UNITS.values(), key=lambda x: x.symbol)
    ]
    _dump(folder / "units.json", {"units": units})
    codes = [{"code": str(c), "retry": str(r)} for c, r in sorted(RETRY_RULES.items(), key=lambda x: str(x[0]))]
    _dump(folder / "error-codes.json", {"codes": codes})


if __name__ == "__main__":
    write_all(Path(sys.argv[1]))
