"""Schema snapshots (spec 4.12, AC51): the committed docs/schema files equal a fresh export."""

import json
import runpy
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from eng_contract import _schema_export
from eng_contract.kinds import NEUTRAL_KINDS


def _find_schema_dir() -> Path:
    """First ancestor holding docs/schema: the package root, or the copy root when run from mutants/."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "docs" / "schema").is_dir():
            return parent / "docs" / "schema"
    raise AssertionError("committed docs/schema folder not found")


SCHEMA_DIR = _find_schema_dir()
TOP = (
    "envelope", "result-record", "error-detail", "ref", "quantity", "cited", "verdict", "model-issue", "trace",
    "model-state",
)  # fmt: skip


def _files(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def test_fresh(tmp_path: Path) -> None:
    _schema_export.write_all(tmp_path)
    committed = _files(SCHEMA_DIR)
    assert committed, "docs/schema is empty"
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


def test_content(tmp_path: Path) -> None:
    _schema_export.write_all(tmp_path)

    def load(name: str) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads((tmp_path / name).read_text(encoding="utf-8")))

    for name, model in _schema_export._MODELS.items():
        assert load(f"{name}.schema.json") == model.model_json_schema(), name
    for kind, kmodel in NEUTRAL_KINDS.items():
        assert load("kinds/" + kind.replace("/", "-") + ".schema.json") == kmodel.model_json_schema(), kind
    units = load("units.json")["units"]
    assert units
    for entry in units:
        assert set(entry) == {"symbol", "dimension", "factor", "pi_power", "offset", "source"}


@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_main_regenerates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["_schema_export", str(tmp_path)])
    runpy.run_module("eng_contract._schema_export", run_name="__main__")
    assert (tmp_path / "envelope.schema.json").is_file()
    assert (tmp_path / "units.json").is_file()
