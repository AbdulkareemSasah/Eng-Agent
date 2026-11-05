"""Tests of the calculation-note renderer (plan 0001 T13; spec 0001 AC35, section 4.10)."""

import importlib
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.verdicts import VerdictSet

from structural_codes.notes import render_html
from structural_codes.pack import Registry

# B-267: split module name, see tests/golden/test_notes_golden.py.
_PACK_MODULE = "synth" + "base.runner_checks"
_SRC = Path(__file__).parent.parent / "fixtures" / "synthbase" / "src"
_DATA = Path(__file__).parent.parent / "data" / "golden" / "notes" / "payload.json"
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:e[+-]?\d+)?", re.IGNORECASE)


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> Iterator[Registry]:
    monkeypatch.syspath_prepend(str(_SRC))
    yield Registry.of([importlib.import_module(_PACK_MODULE).RUNNER_PACK])
    for name in [n for n in sys.modules if n == "synthbase" or n.startswith("synthbase.")]:
        del sys.modules[name]


def _raw() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(_DATA.read_text(encoding="utf-8"))
    return raw


def _visible_numbers(html: str) -> list[str]:
    text = re.sub(r"<style>.*?</style>|<[^>]*>", " ", html, flags=re.DOTALL)
    return _NUMBER.findall(text)


def test_escaping_watermark_and_values(registry: Registry) -> None:
    raw = _raw()
    raw["traces"][0]["steps"][0]["formula"] = "<script>alert(1)</script>"
    raw["draft"] = False
    html = render_html(VerdictSet.model_validate(raw), registry=registry)
    assert "<script" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "http" not in html
    assert "DRAFT" not in html
    assert 'class="watermark"' not in html
    allowed = json.dumps(raw) + " " + " ".join(registry.get("synthbase.3_1.sized").meta.clauses)
    for number in _visible_numbers(html):
        assert number in allowed


def test_draft_watermark_has_arabic_label(registry: Registry) -> None:
    html = render_html(VerdictSet.model_validate(_raw()), registry=registry)
    assert 'class="watermark">DRAFT <span lang="ar" dir="rtl">مسودة</span>' in html


def test_all_values_are_escaped(registry: Registry) -> None:
    raw = _raw()
    raw["traces"][0]["messages"] = ['"><img src=x onerror=1>']
    raw["verdicts"][0]["assumptions"] = ["<b>&"]
    html = render_html(VerdictSet.model_validate(raw), registry=registry)
    assert "<img" not in html
    assert "&quot;&gt;&lt;img src=x onerror=1&gt;" in html
    assert "&lt;b&gt;&amp;" in html


def test_numbers_are_unrounded_and_result_id_shown(registry: Registry) -> None:
    raw = _raw()
    raw["verdicts"][0]["demand"]["value"] = 0.1
    raw["verdicts"][0]["capacity"]["value"] = 0.3
    raw["verdicts"][0]["ratio"] = 0.30000000000000004
    html = render_html(VerdictSet.model_validate(raw), registry=registry, result_id="res_X1")
    assert "0.30000000000000004" in html
    assert "0.1 mm" in html
    assert "res_X1" in html


def test_unknown_check_is_not_found(registry: Registry) -> None:
    raw = _raw()
    raw["traces"][0]["calc_id"] = "synthbase.9_9.unknown"
    with pytest.raises(ContractError) as info:
        render_html(VerdictSet.model_validate(raw), registry=registry)
    assert info.value.detail.code is ErrorCode.NOT_FOUND


def test_verdict_without_trace_is_listed(registry: Registry) -> None:
    raw = _raw()
    raw["verdicts"].append(
        {
            "source": "host",
            "check_id": "host.check",
            "code": "Host",
            "subject": {"kind": "model", "id": "M"},
            "status": "NEEDS_ENGINEER",
        }
    )
    raw["counts"]["NEEDS_ENGINEER"] = 1
    html = render_html(VerdictSet.model_validate(raw), registry=registry)
    assert "Needs engineer" in html
    assert "يحتاج إلى مهندس" in html
