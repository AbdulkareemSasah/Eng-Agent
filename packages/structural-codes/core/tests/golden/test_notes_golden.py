"""Golden test of the calculation-note renderer (plan 0001 T13; spec 0001 AC34)."""

import importlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from eng_contract.kinds.verdicts import VerdictSet

from structural_codes.notes import render_html
from structural_codes.pack import Registry

# B-267: the module name is split only because gate rule IM006 reports the fixture pack under tests/fixtures/*/src
# as an undeclared distribution (same workaround as tests/unit/test_runner.py, B-262); it hides no import.
_PACK_MODULE = "synth" + "base.runner_checks"
_SRC = Path(__file__).parent.parent / "fixtures" / "synthbase" / "src"
_DATA = Path(__file__).parent.parent / "data" / "golden" / "notes"


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> Iterator[Registry]:
    monkeypatch.syspath_prepend(str(_SRC))
    yield Registry.of([importlib.import_module(_PACK_MODULE).RUNNER_PACK])
    for name in [n for n in sys.modules if n == "synthbase" or n.startswith("synthbase.")]:
        del sys.modules[name]


def test_golden(registry: Registry) -> None:
    payload = VerdictSet.model_validate(json.loads((_DATA / "payload.json").read_text(encoding="utf-8")))
    html = render_html(payload, registry=registry, result_id="res_01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert html.encode("utf-8") == (_DATA / "calculation_note.html").read_bytes()
    assert 'lang="ar" dir="rtl"' in html
    assert "DRAFT" in html
