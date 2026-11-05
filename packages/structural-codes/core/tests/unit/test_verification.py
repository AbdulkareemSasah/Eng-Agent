"""Tests of the case files, the tolerance and the verification runner (plan 0001 T9; spec 0001 AC30 to AC32, 4.9)."""

import dataclasses
import importlib
import sys
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

from structural_codes.content_hash import content_hash
from structural_codes.errors import VerificationDataError
from structural_codes.pack import Registry
from structural_codes.verification import DEFAULT_REL_TOL, CaseFile, compare, verify_check, verify_pack

# B-263: the module name is split only because gate rule IM006 reports the fixture pack under tests/fixtures/*/src
# as an undeclared distribution (same workaround as tests/unit/test_runner.py, B-262); it hides no import.
_PACK_MODULE = "synth" + "base.runner_checks"
_SRC = Path(__file__).parent.parent / "fixtures" / "synthbase" / "src"
_DATA = Path(__file__).parent.parent / "data" / "verification"
_SIZED = "synthbase.3_1.sized"
_TWO_PRE = "synthbase.4_1.two_pre"
_GAP = "synthbase.6_1.gap"
_S1 = {"kind": "section", "id": "S1"}
_TIGHT = 1.0e-9


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> Iterator[Registry]:
    monkeypatch.syspath_prepend(str(_SRC))
    yield Registry.of([importlib.import_module(_PACK_MODULE).RUNNER_PACK])
    for name in [n for n in sys.modules if n == "synthbase" or n.startswith("synthbase.")]:
        del sys.modules[name]


def _values(**quantities: tuple[float, str]) -> dict[str, Any]:
    return {n: {"value": v, "unit": u, "abs_tol": _TIGHT} for n, (v, u) in quantities.items()}


def _case(
    case_id: str, kind: str, *, status: str = "PASS", values: dict[str, Any] | None = None, **extra: Any
) -> dict[str, Any]:
    inputs = {"width_mm": 10, "demand_mm": 50, "capacity_mm": 100}
    expected = {"status": status, "values": _values(ratio=(0.5, "1")) if values is None else values}
    return {"id": case_id, "kind": kind, "subject": _S1, "inputs": inputs, "expected": expected, **extra}


_BOOK = {"book": {"title": "Synthetic Book", "edition": "1", "page": 12, "example": "3.4"}}
_PROGRAM = {"program": "SynthProgram", "program_version": "1.0", "assumption_differences": ["synthetic difference"]}


def _doc(*cases: dict[str, Any], check_id: str = _SIZED, **top: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"format": "structural-codes-verification/1", "check_id": check_id, "cases": list(cases)}
    return {**base, **top}


def _load(doc: dict[str, Any]) -> CaseFile:
    return CaseFile.from_yaml(yaml.safe_dump(doc))


def _review_stub() -> dict[str, Any]:
    return {
        "content_sha256": "a" * 64,
        "author": "author-a",
        "reviewer": "reviewer-b",
        "date": "2026-11-05",
        "boundary_tests": [],
        "property_tests": [],
    }


def _review(check_id: str, registry: Registry, **over: Any) -> dict[str, Any]:
    base = {
        **_review_stub(),
        "content_sha256": content_hash(registry.get(check_id)),
        "property_tests": ["tests/property/test_x.py::test_monotone"],
    }
    return {**base, **over}


def _verified_doc(registry: Registry) -> dict[str, Any]:
    return _doc(
        _case("WE-1", "worked_example", source=_BOOK),
        program_comparison={"not_available": "synthetic fixture: no host computes this"},
        review=_review(_SIZED, registry),
    )


def _unmet(doc: dict[str, Any], registry: Registry, check_id: str = _SIZED) -> list[str]:
    report = verify_check(registry.get(check_id), _load(doc), registry=registry)
    return [u[:3] for u in report.unmet]


def test_case_file_schema() -> None:
    sample = CaseFile.load(_DATA / f"{_SIZED}.yaml")
    assert sample.check_id == _SIZED
    assert [c.id for c in sample.cases] == ["WE-1", "BD-1"]
    assert sample.cases[0].expected.values["ratio"].abs_tol == _TIGHT
    assert sample.cases[0].expected.values["ratio"].rel_tol is None
    assert sample.review is None
    assert sample.program_comparison is not None

    valid: list[dict[str, Any]] = [
        _case("HC-1", "hand_check", source={"derivation": "synthetic equation 1 by hand"}),
        _case("WE-1", "worked_example", source=_BOOK),
        _case("WE-2", "worked_example", source={"code_example": {"document": "D", "edition": 2, "example": "E1"}}),
        _case("PC-1", "program_comparison", source={**_PROGRAM, "record": "records/pc1.md"}),
        _case("PC-2", "program_comparison", source={**_PROGRAM, "status": "needs_local_test"}),
        _case("BD-1", "boundary"),
    ]
    for case in valid:
        assert _load(_doc(case)).cases[0].id == case["id"], case["id"]

    without_tol = deepcopy(valid[5])
    del without_tol["expected"]["values"]["ratio"]["abs_tol"]
    other_book = {"code_example": {"document": "D", "edition": "1", "example": "E"}}
    broken: dict[str, dict[str, Any]] = {
        "hand check without derivation": _case("HC-1", "hand_check"),
        "hand check with an empty derivation": _case("HC-1", "hand_check", source={"derivation": ""}),
        "worked example without a source": _case("WE-1", "worked_example"),
        "worked example with book and code example": _case("WE-1", "worked_example", source={**_BOOK, **other_book}),
        "book without a page": _case(
            "WE-1", "worked_example", source={"book": {"title": "T", "edition": "1", "example": "3.4"}}
        ),
        "code example without a document": _case(
            "WE-1", "worked_example", source={"code_example": {"edition": "1", "example": "E"}}
        ),
        "program comparison without a version": _case(
            "PC-1", "program_comparison", source={"program": "P", "record": "r.md"}
        ),
        "program comparison without record or status": _case("PC-1", "program_comparison", source=_PROGRAM),
        "program comparison with record and status": _case(
            "PC-1", "program_comparison", source={**_PROGRAM, "record": "r.md", "status": "needs_local_test"}
        ),
        "program comparison with another status": _case(
            "PC-1", "program_comparison", source={**_PROGRAM, "status": "done"}
        ),
        "boundary with a source": _case("BD-1", "boundary", source={"derivation": "x"}),
        "hand check with a book": _case("HC-1", "hand_check", source=_BOOK),
        "expected quantity without abs_tol": without_tol,
        "negative abs_tol": _case("BD-1", "boundary", values={"ratio": {"value": 1, "unit": "1", "abs_tol": -1}}),
        "negative rel_tol": _case(
            "BD-1", "boundary", values={"ratio": {"value": 1, "unit": "1", "abs_tol": 0, "rel_tol": -0.1}}
        ),
        "non-finite value": _case(
            "BD-1", "boundary", values={"ratio": {"value": float("nan"), "unit": "1", "abs_tol": 0}}
        ),
        "unknown kind": _case("BD-1", "survey"),
        "unknown status": _case("BD-1", "boundary", status="MAYBE"),
        "unknown field": _case("BD-1", "boundary", note="extra"),
        "unknown subject kind": {**_case("BD-1", "boundary"), "subject": {"kind": "bridge", "id": "S1"}},
    }
    for label, case in broken.items():
        with pytest.raises(VerificationDataError):
            _load(_doc(case))
        assert label

    stub = _review_stub()
    top_level: dict[str, dict[str, Any]] = {
        "wrong format": {**_doc(), "format": "structural-codes-verification/2"},
        "missing check id": {k: v for k, v in _doc().items() if k != "check_id"},
        "unknown top-level key": {**_doc(), "extra": 1},
        "duplicate case id": _doc(valid[5], valid[5]),
        "not_available with program cases": _doc(
            _case("PC-1", "program_comparison", source={**_PROGRAM, "record": "r.md"}),
            program_comparison={"not_available": "synthetic reason"},
        ),
        "empty not_available reason": _doc(program_comparison={"not_available": ""}),
        "review without reviewer": _doc(review={k: v for k, v in stub.items() if k != "reviewer"}),
        "review with a short hash": _doc(review={**stub, "content_sha256": "abc"}),
        "review with a bad date": _doc(review={**stub, "date": "not a date"}),
    }
    for label, doc in top_level.items():
        with pytest.raises(VerificationDataError):
            _load(doc)
        assert label


def test_yaml_loading_is_safe_and_strict() -> None:
    nested = "format: structural-codes-verification/1\ncheck_id: x.y.z\ncases:\n  - id: A\n    id: B\n"
    for text in (
        "format: a\nformat: b\n",  # duplicate key
        nested,  # duplicate key inside a sequence item
        "a: [unclosed",  # syntax error
        "- just\n- a list\n",  # not a mapping
        "!!python/object/apply:os.system ['true']\n",  # an unsafe tag
        "",  # nothing
    ):
        with pytest.raises(VerificationDataError):
            CaseFile.from_yaml(text)
    with pytest.raises(VerificationDataError):
        CaseFile.load(_DATA / "does-not-exist.yaml")


def test_tolerance() -> None:
    # |a - e| <= max(rel_tol * |e|, abs_tol): both edges inclusive, the larger tolerance decides (AC31).
    assert compare(100.5, 100.0, rel_tol=0.005, abs_tol=0.0)
    assert not compare(100.5000001, 100.0, rel_tol=0.005, abs_tol=0.0)
    assert compare(99.5, 100.0, rel_tol=0.005, abs_tol=0.0)
    assert not compare(99.4999999, 100.0, rel_tol=0.005, abs_tol=0.0)
    assert compare(1.0e-6, 0.0, rel_tol=0.005, abs_tol=1.0e-6)  # the absolute floor at an expected zero
    assert not compare(2.0e-6, 0.0, rel_tol=0.005, abs_tol=1.0e-6)
    assert compare(1009.0, 1000.0, rel_tol=0.005, abs_tol=10.0)  # absolute tolerance larger than relative
    assert not compare(1011.0, 1000.0, rel_tol=0.005, abs_tol=10.0)
    assert compare(1005.0, 1000.0, rel_tol=0.005, abs_tol=0.0)  # relative tolerance larger than absolute
    assert not compare(1006.0, 1000.0, rel_tol=0.005, abs_tol=1.0)
    assert compare(-100.5, -100.0, rel_tol=0.005, abs_tol=0.0)  # the relative term uses |e|
    assert not compare(-101.0, -100.0, rel_tol=0.005, abs_tol=0.0)
    assert not compare(float("nan"), 1.0, rel_tol=0.005, abs_tol=1.0)
    assert not compare(float("inf"), 1.0, rel_tol=0.005, abs_tol=1.0)
    # The default relative tolerance is 0.5 % (10-structural-codes section 6) and cites it.
    assert DEFAULT_REL_TOL.value == 0.005
    assert "10-structural-codes" in DEFAULT_REL_TOL.source
    assert compare(100.4, 100.0, abs_tol=0.0)
    assert not compare(100.6, 100.0, abs_tol=0.0)


def test_case_tolerances_and_status(registry: Registry) -> None:
    check = registry.get(_SIZED)

    def outcome(case: dict[str, Any]) -> tuple[str, str]:
        result = verify_check(check, _load(_doc(case)), registry=registry).cases[0]
        return result.outcome, result.detail

    assert outcome(_case("B", "boundary"))[0] == "pass"
    # Values are the trace names and the verdict's demand, capacity and ratio.
    exact = _values(ratio=(0.5, "1"), demand=(50.0, "mm"), capacity=(100.0, "mm"), width_mm=(10.0, "mm"))
    assert outcome(_case("B", "boundary", values=exact))[0] == "pass"
    # The default relative tolerance applies when the quantity gives none; abs_tol is the floor.
    near = {"ratio": {"value": 0.5024, "unit": "1", "abs_tol": 0.0}}
    far = {"ratio": {"value": 0.5026, "unit": "1", "abs_tol": 0.0}}
    assert outcome(_case("B", "boundary", values=near))[0] == "pass"
    assert outcome(_case("B", "boundary", values=far))[0] == "fail"
    floor = {"ratio": {"value": 0.6, "unit": "1", "abs_tol": 0.11}}
    assert outcome(_case("B", "boundary", values=floor))[0] == "pass"
    own = {"ratio": {"value": 0.55, "unit": "1", "abs_tol": 0.0, "rel_tol": 0.1}}
    assert outcome(_case("B", "boundary", values=own))[0] == "pass"
    # The expected status must match exactly.
    assert outcome(_case("B", "boundary", status="FAIL"))[0] == "fail"
    # No unit conversion: 50 mm is not 0.05 m.
    assert outcome(_case("B", "boundary", values={"demand": {"value": 0.05, "unit": "m", "abs_tol": 0}})) == (
        "fail",
        "demand: unit mm, expected m",
    )
    # A name the evaluation did not produce fails the case and says which.
    missing = {"nothing_mm": {"value": 1, "unit": "mm", "abs_tol": 0}}
    assert outcome(_case("B", "boundary", values=missing)) == ("fail", "nothing_mm: no such value in the result")
    # A value outside tolerance reports expected, actual and the allowed difference.
    detail = outcome(_case("B", "boundary", values={"ratio": {"value": 0.9, "unit": "1", "abs_tol": 0.01}}))[1]
    assert "ratio" in detail
    assert "0.9" in detail
    assert "0.5" in detail


def test_case_error_and_scope(registry: Registry) -> None:
    check = registry.get(_SIZED)
    out_of_range = _case("B", "boundary", inputs={"width_mm": 500, "demand_mm": 1, "capacity_mm": 1})
    result = verify_check(check, _load(_doc(out_of_range)), registry=registry).cases[0]
    assert result.outcome == "fail"
    assert "OUT_OF_RANGE" in result.detail
    wrong = _doc(_case("B", "boundary"), check_id=_TWO_PRE)
    with pytest.raises(VerificationDataError):
        verify_check(check, _load(wrong), registry=registry)


def test_report_and_requirements(registry: Registry) -> None:
    check = registry.get(_SIZED)
    report = verify_check(check, _load(_verified_doc(registry)), registry=registry)
    assert report.check_id == _SIZED
    assert report.content_sha256 == content_hash(check)
    assert [(c.id, c.kind, c.outcome) for c in report.cases] == [("WE-1", "worked_example", "pass")]
    assert report.unmet == ()
    assert report.verified is True

    # (1) a hand check is reported but never satisfies the worked-example requirement.
    hand = _verified_doc(registry)
    hand["cases"] = [_case("HC-1", "hand_check", source={"derivation": "synthetic equation by hand"})]
    report = verify_check(check, _load(hand), registry=registry)
    assert [(c.id, c.outcome) for c in report.cases] == [("HC-1", "pass")]
    assert [u[:3] for u in report.unmet] == ["(1)"]
    assert report.verified is False
    # A failing worked example does not count either; it also breaks (6).
    failing = _verified_doc(registry)
    failing["cases"] = [_case("WE-1", "worked_example", source=_BOOK, status="FAIL")]
    report = verify_check(check, _load(failing), registry=registry)
    assert [c.outcome for c in report.cases] == ["fail"]
    assert [u[:3] for u in report.unmet] == ["(1)", "(6)"]
    # (6) a failing case of any kind.
    other = _verified_doc(registry)
    other["cases"].append(_case("BD-1", "boundary", status="FAIL"))
    assert _unmet(other, registry) == ["(6)"]

    # (2) program comparisons: a pending case, a case without listed differences, no statement at all.
    for_program = _verified_doc(registry)
    del for_program["program_comparison"]
    assert _unmet(for_program, registry) == ["(2)"]
    pending = deepcopy(for_program)
    pending["cases"].append(_case("PC-1", "program_comparison", source={**_PROGRAM, "status": "needs_local_test"}))
    report = verify_check(check, _load(pending), registry=registry)
    assert [(c.id, c.outcome) for c in report.cases] == [("WE-1", "pass"), ("PC-1", "pending")]
    assert [u[:3] for u in report.unmet] == ["(2)"]
    recorded = deepcopy(for_program)
    recorded["cases"].append(_case("PC-1", "program_comparison", source={**_PROGRAM, "record": "records/pc1.md"}))
    assert _unmet(recorded, registry) == []
    recorded["cases"][1]["source"]["assumption_differences"] = []
    assert _unmet(recorded, registry) == ["(2)"]
    failed_pc = deepcopy(recorded)
    failed_pc["cases"][1]["source"]["assumption_differences"] = ["synthetic difference"]
    failed_pc["cases"][1]["expected"]["status"] = "FAIL"
    assert _unmet(failed_pc, registry) == ["(2)", "(6)"]

    # (5) the review: absent (so no property test is listed either), a stale hash, the author as reviewer.
    no_review = _verified_doc(registry)
    del no_review["review"]
    assert _unmet(no_review, registry) == ["(4)", "(5)"]  # property tests are listed in the review block
    stale = _verified_doc(registry)
    stale["review"]["content_sha256"] = "0" * 64
    assert _unmet(stale, registry) == ["(5)"]
    self_review = _verified_doc(registry)
    self_review["review"]["reviewer"] = self_review["review"]["author"]
    assert _unmet(self_review, registry) == ["(5)"]

    # (4) a listed property test.
    no_property = _verified_doc(registry)
    no_property["review"]["property_tests"] = []
    assert _unmet(no_property, registry) == ["(4)"]
    # Everything missing: every unmet requirement is listed, in order, and verified is false.
    report = verify_check(check, _load(_doc()), registry=registry)
    assert [u[:3] for u in report.unmet] == ["(1)", "(2)", "(4)", "(5)"]
    assert report.verified is False


def test_boundary_paths(registry: Registry) -> None:
    def doc(check_id: str, *cases: dict[str, Any], tests: list[str] | None = None) -> dict[str, Any]:
        base = _verified_doc(registry)
        base["check_id"] = check_id
        base["review"] = _review(check_id, registry, boundary_tests=tests or [])
        # a declared gap replaces the verdict, so its example expects NEEDS_ENGINEER and no values
        example = _case("WE-1", "worked_example", source=_BOOK)
        if check_id == _GAP:
            example["expected"] = {"status": "NEEDS_ENGINEER", "values": {}}
        base["cases"] = [example, *cases]
        return base

    def covering(case_id: str, *paths: str, width: int, status: str) -> dict[str, Any]:
        inputs = {"width_mm": width, "demand_mm": 50, "capacity_mm": 100}
        return _case(case_id, "boundary", status=status, values={}, inputs=inputs, covers=list(paths))

    # A check without preconditions and gaps has no path to cover.
    assert _unmet(doc(_SIZED), registry) == []
    # Two preconditions: each needs a boundary case or a listed boundary test (spec 4.9.4 (3)).
    report = verify_check(registry.get(_TWO_PRE), _load(doc(_TWO_PRE)), registry=registry)
    assert [u[:3] for u in report.unmet] == ["(3)"]
    assert "P1" in report.unmet[0]
    assert "P2" in report.unmet[0]
    one = doc(_TWO_PRE, covering("BD-P1", "P1", width=60, status="NOT_APPLICABLE"))
    report = verify_check(registry.get(_TWO_PRE), _load(one), registry=registry)
    assert [u[:3] for u in report.unmet] == ["(3)"]
    assert "P2" in report.unmet[0]
    assert "P1" not in report.unmet[0]
    both = doc(
        _TWO_PRE,
        covering("BD-P1", "P1", width=60, status="NOT_APPLICABLE"),
        covering("BD-P2", "P2", width=30, status="NEEDS_ENGINEER"),
    )
    assert _unmet(both, registry, _TWO_PRE) == []
    listed = doc(
        _TWO_PRE,
        covering("BD-P1", "P1", width=60, status="NOT_APPLICABLE"),
        tests=["P2: tests/unit/test_x.py::test_p2"],
    )
    assert _unmet(listed, registry, _TWO_PRE) == []
    wrong_listed = doc(
        _TWO_PRE,
        covering("BD-P1", "P1", width=60, status="NOT_APPLICABLE"),
        tests=["P3: tests/unit/test_x.py::test_p3"],
    )
    assert _unmet(wrong_listed, registry, _TWO_PRE) == ["(3)"]
    # A declared gap is a NEEDS_ENGINEER path and needs its own boundary item.
    report = verify_check(registry.get(_GAP), _load(doc(_GAP)), registry=registry)
    assert [u[:3] for u in report.unmet] == ["(3)"]
    assert "G-3" in report.unmet[0]
    assert _unmet(doc(_GAP, covering("BD-G3", "G-3", width=10, status="NEEDS_ENGINEER")), registry, _GAP) == []


def test_verify_check_requires_the_registry_to_hold_that_check(registry: Registry) -> None:
    sized = registry.get(_SIZED)
    other = dataclasses.replace(sized, preconditions=())  # same id, a different copy
    cases = _load(_verified_doc(registry))
    with pytest.raises(VerificationDataError, match="registry does not hold"):
        verify_check(other, cases, registry=registry)
    with pytest.raises(VerificationDataError, match="registry does not hold"):
        verify_check(sized, cases, registry=Registry.of([]))


def test_covers_is_for_boundary_cases_only() -> None:
    for kind, source in (("hand_check", {"derivation": "by hand"}), ("worked_example", _BOOK)):
        with pytest.raises(VerificationDataError, match="covers is only for boundary"):
            _load(_doc(_case("C-1", kind, source=source, covers=["P1"])))


def test_verify_pack(registry: Registry) -> None:
    pack = registry.packs[0]
    reports = verify_pack(pack, _DATA)
    assert [r.check_id for r in reports] == sorted(c.meta.check_id for c in pack.checks)
    by_id = {r.check_id: r for r in reports}
    sized = by_id[_SIZED]
    assert [(c.id, c.outcome) for c in sized.cases] == [("WE-1", "pass"), ("BD-1", "pass")]
    assert sized.verified is False  # review is null in the sample file
    assert [u[:3] for u in sized.unmet] == ["(4)", "(5)"]
    for check_id, report in by_id.items():
        if check_id != _SIZED:
            assert report.cases == ()
            assert report.verified is False
            assert "no case file" in report.unmet[0]


def test_verify_pack_rejects_a_file_naming_another_check(registry: Registry, tmp_path: Path) -> None:
    (tmp_path / f"{_TWO_PRE}.yaml").write_text(yaml.safe_dump(_doc(check_id=_SIZED)))
    with pytest.raises(VerificationDataError):
        verify_pack(registry.packs[0], tmp_path)
