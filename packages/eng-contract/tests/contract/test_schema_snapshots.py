"""Schema snapshots (spec 4.12, AC51): the committed docs/schema files equal a fresh export."""

import json
from pathlib import Path

from eng_contract import _schema_export
from eng_contract.kinds import NEUTRAL_KINDS

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "docs" / "schema"
TOP = (
    "envelope", "result-record", "error-detail", "ref", "quantity", "cited", "verdict", "model-issue", "trace",
    "model-state",
)  # fmt: skip


def _files(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def test_fresh(tmp_path: Path) -> None:
    _schema_export.write_all(tmp_path)
    committed = _files(SCHEMA_DIR)
    fresh = _files(tmp_path)
    assert sorted(committed) == sorted(fresh)
    stale = [name for name in fresh if committed[name] != fresh[name]]
    assert stale == []


def test_file_set(tmp_path: Path) -> None:
    _schema_export.write_all(tmp_path)
    expected = {f"{n}.schema.json" for n in TOP} | {"units.json", "error-codes.json"}
    expected |= {"kinds/" + k.replace("/", "-") + ".schema.json" for k in NEUTRAL_KINDS}
    assert set(_files(tmp_path)) == expected
    assert "kinds/model.stories-1.schema.json" in expected


def test_format(tmp_path: Path) -> None:
    _schema_export.write_all(tmp_path)
    for name, data in _files(tmp_path).items():
        text = data.decode("utf-8")
        assert text == json.dumps(json.loads(text), indent=2, sort_keys=True, ensure_ascii=False) + "\n", name


def test_units_and_error_codes(tmp_path: Path) -> None:
    _schema_export.write_all(tmp_path)
    units = json.loads((tmp_path / "units.json").read_text(encoding="utf-8"))
    by_symbol = {u["symbol"]: u for u in units["units"]}
    assert by_symbol["m"]["factor"] == "1"
    assert by_symbol["mm"]["factor"] == "1/1000"
    assert by_symbol["in"]["factor"] == "127/5000"  # 0.0254 m exactly (NIST SP 811)
    assert by_symbol["deg"]["pi_power"] == 1
    assert by_symbol["degC"]["offset"] == "5463/20"  # 273.15 K
    codes = json.loads((tmp_path / "error-codes.json").read_text(encoding="utf-8"))
    rules = {c["code"]: c["retry"] for c in codes["codes"]}
    assert rules["HOST_BUSY"] == "always"
    assert rules["HOST_ERROR"] == "depends"
    assert rules["INVALID_ARGUMENT"] == "never"
