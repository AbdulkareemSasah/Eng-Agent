"""Registration of the footing calcs (plan 0010 T3; spec 0010 AC12): metadata, lock entry, record and constants."""

import importlib
import tomllib
from pathlib import Path
from types import ModuleType

import pytest
from eng_contract.cited import Cited
from eng_harness.calcs.footing import FOOTING_CALCS
from eng_harness.calcs.footing import subjects as subjects_module

from eng_harness._calc import _hash
from eng_harness.calc import CalcStatus
from eng_harness.calcs import REGISTRY

ROOT = Path(__file__).resolve().parents[3]
CALCS = {  # calc id -> (module, output kind, spec section naming its method)
    "harness.footing_subjects": (subjects_module, "harness.footing_subjects/1", "§4.4.1"),
}


def test_the_footing_calcs_are_the_registered_ones() -> None:
    assert sorted(c.id for c in FOOTING_CALCS) == sorted(CALCS)
    assert sorted(i for i in REGISTRY if i.startswith("harness.footing_")) == sorted(CALCS)


@pytest.mark.parametrize("calc_id", sorted(CALCS))
def test_metadata_and_constants(calc_id: str) -> None:
    module, kind, section = CALCS[calc_id]
    definition = REGISTRY[calc_id]
    assert (definition.version, definition.output_kind, definition.verification) == (1, kind, "draft")
    assert "spec 0010" in definition.method_source
    assert section in definition.method_source
    assert definition.fn.__module__ == module.__name__
    # a verification record, with the calc's hash
    record = (ROOT / "docs" / "verification" / "calcs" / f"{calc_id}.md").read_text(encoding="utf-8")
    assert REGISTRY.content_hash(calc_id) in record
    assert "Status: draft" in record
    # a lock entry
    entries = [e for e in _hash.read_lock()["calcs"] if e["id"] == calc_id]
    assert entries == [{"id": calc_id, "version": 1, "content_sha256": REGISTRY.content_hash(calc_id)}]
    # only cited constants: every upper-case module name is a Cited with a source, and no approval is recorded
    constants = {n: v for n, v in vars(module).items() if n.isupper() and not n.startswith("_")}
    cited = {n: v for n, v in constants.items() if isinstance(v, Cited)}
    assert cited
    assert all(v.source.strip() for v in cited.values())
    assert [n for n, v in constants.items() if not isinstance(v, Cited | tuple)] == []


def test_the_calcs_are_draft_in_the_shipped_approvals() -> None:
    text = (ROOT / "src" / "eng_harness" / "calcs" / "approvals.yaml").read_text(encoding="utf-8")
    assert "footing" not in text
    assert all(REGISTRY[i].verification == CalcStatus.DRAFT for i in CALCS)


def test_the_calc_modules_are_importable_by_their_public_names() -> None:
    modules: list[ModuleType] = [importlib.import_module(f"eng_harness.calcs.footing.{n}") for n in ("subjects",)]
    assert [m.__name__ for m in modules] == ["eng_harness.calcs.footing.subjects"]
    public = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["eng-gate"]["public_modules"]
    assert {"eng_harness.calcs", "eng_harness.calcs.footing", "eng_harness.calcs.footing.subjects"} <= set(public)
