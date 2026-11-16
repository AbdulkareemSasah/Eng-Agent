"""Calc 4, design results summary (plan 0003 T10; spec 0003 4.9, AC35 to AC38, AC50): order, members, status."""

import json
from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.calc import CalcInput, InputMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.kinds.calcs import DesignSummary

CALC_ID = "harness.design_summary"
CHECK = "host.csi.steel"
MDL = "mdl_00000000000000000000000000"
SRC = "engineer:synthetic@2026-01-01T00:00:00.000Z"
STATUSES = ("PASS", "FAIL", "NOT_APPLICABLE", "NEEDS_ENGINEER", "ERROR")
TOP_HINT = "set and confirm report.top_n in the design basis"
GOLDEN_DIR = Path(__file__).resolve().parents[2] / "data" / "golden" / "calcs"


def _verdict(
    fid: str,
    ratio: float | None,
    status: str,
    *,
    kind: str = "frame",
    check: str = CHECK,
    station: float | None = None,
    case: str | None = None,
    limit: float = 1.0,
) -> dict[str, Any]:
    return {
        "source": "host",
        "check_id": check,
        "code": "synthetic",
        "subject": {"kind": kind, "id": fid, "station_mm": station, "case": case},
        "ratio": ratio,
        "ratio_limit": limit,
        "status": status,
    }


def _set(*verdicts: dict[str, Any]) -> dict[str, Any]:
    counts = {s: sum(v["status"] == s for v in verdicts) for s in STATUSES}
    return {"verdicts": list(verdicts), "traces": [], "counts": counts, "draft": False}


def _basis(value: Any = 3, *, unit: str | None = None, confirmed: bool = True) -> dict[str, Any]:
    field = {"value": value, "unit": unit, "source": SRC, "confirmed": confirmed, "citation": None}
    return {"template": None, "fields": {"report.top_n": field}}


def _ref(n: int, kind: str, *, complete: bool = True, revision: int | None = None) -> dict[str, Any]:
    return {
        "result_id": f"res_{n:026d}",
        "kind": kind,
        "complete": complete,
        "model_id": MDL if revision is not None else None,
        "model_revision": revision,
        "parents": [],
        "producer_tool": "csi" if revision is not None else "harness",
    }


def _refs(**extra: Any) -> dict[str, Any]:
    return {"verdicts": _ref(1, "verdicts.set/1", revision=5), "basis": _ref(9, "basis.design_basis/1")} | extra


def _run(
    fields: dict[str, Any], refs: dict[str, Any] | None = None, trace: TraceBuilder | None = None
) -> dict[str, Any]:
    definition = REGISTRY[CALC_ID]
    input_type = definition.input_type
    assert isinstance(input_type, type)
    assert issubclass(input_type, CalcInput)
    inp = input_type.model_validate({"basis": _basis(), **fields})
    meta = InputMeta.model_validate({"refs": _refs() if refs is None else refs})
    return definition(inp, meta, trace or TraceBuilder()).model_dump(mode="json")


def _steps(fields: dict[str, Any], refs: dict[str, Any] | None = None) -> dict[str, Any]:
    trace = TraceBuilder()
    _run(fields, refs, trace)
    return {s.name: s for s in trace.build(REGISTRY[CALC_ID], "ab" * 32).steps}


def _keys(rows: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return [(r["subject_kind"], r["subject_id"], r["check_id"], r["station_mm"], r["case"], r["ratio"]) for r in rows]


def test_empty() -> None:
    """AC38: an empty verdict set gives NEEDS_ENGINEER with the message "no design results"."""
    trace = TraceBuilder()
    out = _run({"verdicts": _set()}, trace=trace)
    assert out["status"] == "NEEDS_ENGINEER"
    assert out["counts"] == dict.fromkeys(STATUSES, 0)
    assert (out["governing"], out["governing_by_group"], out["failing"], out["attention"]) == (None, [], [], [])
    assert out["top"] == {"n": 0, "of_total": 0, "rows": [], "label": "top 0 of 0 by ratio"}
    assert (out["members"], out["failing_members"], out["not_designed"], out["complete"]) == ([], [], [], True)
    steps = {s.name: s for s in trace.build(REGISTRY[CALC_ID], "ab" * 32).steps}
    assert steps["status_reasons"].value == "no design results"
    assert steps["status"].value == "NEEDS_ENGINEER"


def test_order_key_ties_and_nulls() -> None:
    """S2: ratio descending, then kind, id, check, station and case ascending with null first, then canonical bytes."""
    verdicts = [
        _verdict("F1", 0.5, "PASS", station=100.0, case="B"),
        _verdict("F1", 0.5, "PASS", station=100.0, case="A"),
        _verdict("F1", 0.5, "PASS", station=100.0),
        _verdict("F1", 0.5, "PASS", station=20.0, case="A"),
        _verdict("F1", 0.5, "PASS", case="Z"),
        _verdict("F1", 0.5, "PASS", check="host.csi.a"),
        _verdict("F0", 0.5, "PASS", check="host.csi.z"),
        _verdict("A9", 0.5, "PASS", kind="area"),
        _verdict("F9", 0.6, "PASS"),
        _verdict("A0", None, "NOT_APPLICABLE", kind="area"),
    ]
    out = _run({"verdicts": _set(*verdicts), "basis": _basis(20)})
    assert _keys(out["top"]["rows"]) == [
        ("frame", "F9", CHECK, None, None, 0.6),
        ("area", "A9", CHECK, None, None, 0.5),
        ("frame", "F0", "host.csi.z", None, None, 0.5),
        ("frame", "F1", "host.csi.a", None, None, 0.5),
        ("frame", "F1", CHECK, None, "Z", 0.5),
        ("frame", "F1", CHECK, 20.0, "A", 0.5),
        ("frame", "F1", CHECK, 100.0, None, 0.5),
        ("frame", "F1", CHECK, 100.0, "A", 0.5),
        ("frame", "F1", CHECK, 100.0, "B", 0.5),
        ("area", "A0", CHECK, None, None, None),
    ]
    assert out["top"]["label"] == "top 10 of 10 by ratio"
    # equal on the whole key: the canonical JSON bytes decide, whatever the input order
    a, b = _verdict("F1", 0.5, "PASS", limit=1.0), _verdict("F1", 0.5, "PASS", limit=0.8)
    for given in ([a, b], [b, a]):
        rows = _run({"verdicts": _set(*given)})["top"]["rows"]
        assert [r["ratio_limit"] for r in rows] == [0.8, 1.0]
    steps = _steps({"verdicts": _set(a, b), "basis": _basis(1)})
    assert steps["top_rows"].value == 1


def test_ratio_exact_comparison() -> None:
    """S2: ratios compare exactly; a ratio one binary64 step above another ranks first."""
    above = 0.5000000000000001
    out = _run({"verdicts": _set(_verdict("F1", 0.5, "PASS"), _verdict("F2", above, "PASS")), "basis": _basis(1)})
    assert out["governing"]["subject_id"] == "F2"
    assert out["top"]["rows"] == [out["governing"]]


def test_governing_needs_a_ratio() -> None:
    """S2, S3: verdicts without a ratio never govern; a group without a ratio has no governing row."""
    verdicts = [_verdict("F1", None, "ERROR"), _verdict("W1", None, "NEEDS_ENGINEER", kind="area", check="host.a")]
    out = _run({"verdicts": _set(*verdicts)})
    assert (out["governing"], out["governing_by_group"]) == (None, [])
    assert [r["subject_id"] for r in out["attention"]] == ["W1", "F1"]  # by S2: area before frame
    assert out["members"] == [
        {"subject_kind": "area", "subject_id": "W1", "check_id": "host.a", "status": "NEEDS_ENGINEER", "ratio": None},
        {"subject_kind": "frame", "subject_id": "F1", "check_id": CHECK, "status": "ERROR", "ratio": None},
    ]
    assert out["status"] == "NEEDS_ENGINEER"
    groups = _run({"verdicts": _set(_verdict("F1", 0.4, "PASS"), _verdict("W1", 0.9, "PASS", kind="area"))})
    assert [(g["subject_kind"], g["check_id"], g["row"]["subject_id"]) for g in groups["governing_by_group"]] == [
        ("area", CHECK, "W1"),
        ("frame", CHECK, "F1"),
    ]


def test_member_status_order() -> None:
    """S5: member status is the worst by FAIL > ERROR > NEEDS_ENGINEER > PASS > NOT_APPLICABLE; ratio the largest."""
    pairs = [
        ("FAIL", 1.2, "ERROR", None, "FAIL"),
        ("ERROR", None, "NEEDS_ENGINEER", None, "ERROR"),
        ("NEEDS_ENGINEER", None, "PASS", 0.3, "NEEDS_ENGINEER"),
        ("PASS", 0.3, "NOT_APPLICABLE", None, "PASS"),
    ]
    for first, r1, second, r2, worst in pairs:
        for order in ((first, r1, second, r2), (second, r2, first, r1)):
            verdicts = [_verdict("F1", order[1], order[0], case="A"), _verdict("F1", order[3], order[2], case="B")]
            (member,) = _run({"verdicts": _set(*verdicts)})["members"]
            assert member["status"] == worst, order
            assert member["ratio"] == (r1 if r1 is not None else r2), order
    (member,) = _run({"verdicts": _set(_verdict("F1", None, "NOT_APPLICABLE"))})["members"]
    assert (member["status"], member["ratio"]) == ("NOT_APPLICABLE", None)


def test_changes_need_a_previous() -> None:
    """S5: without a previous summary nothing is listed as changed, appeared or disappeared."""
    out = _run({"verdicts": _set(_verdict("F1", 0.5, "PASS"))})
    lists = ("newly_failing", "newly_passing", "other_changes", "appeared", "disappeared")
    assert out["changes"] == {name: [] for name in lists}


def test_status_rules_and_reasons() -> None:
    """S6: FAIL beats every reason; NEEDS_ENGINEER for attention, not designed or incomplete input; else PASS."""
    one = _set(_verdict("F1", 0.5, "PASS"))
    assert _run({"verdicts": one})["status"] == "PASS"
    assert _steps({"verdicts": one})["status_reasons"].value == "none"
    frames = {"frames": [_frame("F1"), _frame("C1")]}
    refs = _refs(frames=_ref(2, "model.frame_placements/1", revision=5, complete=False))
    out = _run({"verdicts": one, "frames": frames}, refs)
    assert (out["status"], out["not_designed"], out["complete"]) == ("NEEDS_ENGINEER", ["C1"], False)
    assert _steps({"verdicts": one, "frames": frames}, refs)["status_reasons"].value == (
        "frames without design results; incomplete input"
    )
    failing = _set(_verdict("F1", 1.5, "FAIL"), _verdict("F2", None, "ERROR"))
    steps = _steps({"verdicts": failing, "frames": frames}, refs)
    assert steps["status"].value == "FAIL"
    assert steps["status_reasons"].value == (
        "FAIL verdicts; NEEDS_ENGINEER or ERROR verdicts; frames without design results; incomplete input"
    )
    designed = _run({"verdicts": _set(_verdict("C1", 0.2, "PASS", kind="area")), "frames": {"frames": [_frame("C1")]}})
    assert designed["not_designed"] == ["C1"]  # only a (frame, id) verdict designs a frame


def _frame(fid: str) -> dict[str, Any]:
    point = {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0}
    return {
        "id": fid,
        "kind": "column",
        "section": "S1",
        "i": point,
        "j": point | {"z_mm": 3000.0},
        "rotation_deg": 0.0,
    }


def _basis_refusal(basis: dict[str, Any], refs: dict[str, Any] | None = None) -> ContractError:
    with pytest.raises(ContractError) as caught:
        _run({"verdicts": _set(), "basis": basis}, refs)
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    return caught.value


@pytest.mark.parametrize(
    ("basis", "message"),
    [
        ({"template": None, "fields": {}}, "basis field report.top_n is missing (no default)"),
        (_basis(confirmed=False), "basis field report.top_n is not confirmed"),
        (_basis(unit="1"), "basis field report.top_n must have no unit, not 1"),
        (_basis(0), "basis field report.top_n must be an integer >= 1"),
        (_basis(2.0), "basis field report.top_n must be an integer >= 1"),
        (_basis(True), "basis field report.top_n must be an integer >= 1"),
        (_basis("2"), "basis field report.top_n must be an integer >= 1"),
    ],
)
def test_basis_top_n_required(basis: dict[str, Any], message: str) -> None:
    """4.4: report.top_n present, confirmed, without a unit and an integer >= 1; no default."""
    error = _basis_refusal(basis)
    assert error.detail.message == message
    assert (error.detail.field, error.detail.hint) == ("basis.fields.report.top_n", TOP_HINT)


def test_basis_must_be_a_record() -> None:
    """4.4: the basis is read through its record, which names the trace pointer."""
    error = _basis_refusal(_basis(), {"verdicts": _ref(1, "verdicts.set/1", revision=5)})
    assert (error.detail.message, error.detail.field) == ("the basis must be a record reference", "basis")


def test_trace_and_schema() -> None:
    """Trace (4.9): the top-N input, the counts of S1 to S5 and the status (S6); schema marks of 4.13."""
    trace = TraceBuilder()
    verdicts = _set(_verdict("F1", 1.5, "FAIL"), _verdict("F2", None, "ERROR"), _verdict("F3", 0.5, "PASS"))
    _run({"verdicts": verdicts, "basis": _basis(2), "frames": {"frames": [_frame("C1")]}}, None, trace)
    built = trace.build(REGISTRY[CALC_ID], "ab" * 32)
    (top_n,) = built.inputs
    assert (top_n.name, top_n.value, top_n.unit) == ("report_top_n", 2, None)
    assert top_n.ref == "res_00000000000000000000000009#/fields/report.top_n"
    got = [(s.name, s.value, s.formula, s.source, s.uses) for s in built.steps]
    assert got == [
        ("verdict_count", 3, "host verdicts, statuses and ratios as reported", "§4.9 S1", []),
        ("failing_verdicts", 1, "verdicts with status FAIL", "§4.9 S3", ["verdict_count"]),
        ("attention_verdicts", 1, "verdicts with status NEEDS_ENGINEER or ERROR", "§4.9 S3", ["verdict_count"]),
        ("top_rows", 2, "the first report.top_n verdicts by S2, at most all", "§4.9 S3",
         ["report_top_n", "verdict_count"]),
        ("not_designed_frames", 1, "frames without a verdict on (frame, id)", "§4.9 S4", []),
        ("member_count", 3, "distinct (subject kind, subject id, check id)", "§4.9 S5", ["verdict_count"]),
        ("status_reasons", "FAIL verdicts; NEEDS_ENGINEER or ERROR verdicts; frames without design results",
         "the reasons of S6 that hold", "§4.9 S6",
         ["failing_verdicts", "attention_verdicts", "not_designed_frames", "verdict_count"]),
        ("status", "FAIL", "FAIL: any FAIL verdict; else NEEDS_ENGINEER: any reason of S6; else PASS", "§4.9 S6",
         ["status_reasons"]),
    ]  # fmt: skip
    assert built.outputs == ["status"]
    input_type = REGISTRY[CALC_ID].input_type
    assert isinstance(input_type, type)
    assert issubclass(input_type, CalcInput)
    properties = input_type.model_json_schema()["properties"]
    kinds = {
        "verdicts": ["harness.host_design_verdicts/1", "verdicts.set/1"],
        "frames": ["model.frame_placements/1"],
        "previous": ["harness.design_summary/1"],
        "basis": ["basis.design_basis/1"],
    }
    assert set(properties) == set(kinds)
    for name, kind in kinds.items():
        mark = properties[name]["x-eng"]
        assert (mark["ref_kinds"], mark["stale_ok"], mark["engineering_quantity"]) == (kind, False, True), name


def _host(*verdicts: dict[str, Any]) -> dict[str, Any]:
    """The `harness.host_design_verdicts/1` payload of the verdicts: the set's members and the calc port's three."""
    sha = "a" * 64
    calc_id = "harness.host_design_verdicts"
    trace = {"calc_id": calc_id, "calc_version": "1", "content_sha256": sha, "inputs": [], "constants": []}
    return _set(*verdicts) | {
        "calc": {"id": calc_id, "version": 1, "content_sha256": sha, "status": "draft"},
        "trace": trace | {"steps": [], "outputs": []},
        "draft": True,
    }


def _mixed() -> list[dict[str, Any]]:
    return [
        _verdict("F1", 0.97, "FAIL", case="COMB1", limit=0.95),
        _verdict("F2", 0.4, "PASS", case="COMB2", limit=0.95),
        _verdict("F3", None, "NEEDS_ENGINEER", check="host.concrete_design_ratio"),
    ]


def test_host_design_verdicts_input() -> None:
    """Spec 0003 4.9 (B-538): a `harness.host_design_verdicts/1` reference gives the body of a `verdicts.set/1`."""
    verdicts = _mixed()
    refs = _refs(verdicts=_ref(1, "harness.host_design_verdicts/1"))
    from_host = _run({"verdicts": _host(*verdicts)}, refs)
    assert from_host == _run({"verdicts": _set(*verdicts)})
    assert (from_host["status"], from_host["counts"]["FAIL"], from_host["governing"]["subject_id"]) == ("FAIL", 1, "F1")


def test_golden_expectations_are_valid_payloads() -> None:
    """Each summary golden's expected body, with calc metadata and a trace added, fits the calc's output kind."""
    output_type = HARNESS_KINDS[REGISTRY[CALC_ID].output_kind]
    assert output_type is DesignSummary
    files = sorted(GOLDEN_DIR.glob("summary-*.json"))
    assert len(files) == 5
    meta = {"id": CALC_ID, "version": 1, "content_sha256": "a" * 64, "status": "draft"}
    trace = {"calc_id": CALC_ID, "calc_version": "1", "content_sha256": "a" * 64, "steps": [], "outputs": []}
    for path in files:
        expected = json.loads(path.read_text(encoding="utf-8"))["expected"]
        output_type.model_validate(
            expected | {"calc": meta, "draft": True, "trace": trace | {"inputs": [], "constants": []}}
        )


def test_both_verdict_kinds_give_the_same_trace() -> None:
    """The summary reads the member `verdicts` only: the trace's inputs, steps and outputs do not depend on the kind."""
    verdicts = _mixed()
    host_trace, set_trace = TraceBuilder(), TraceBuilder()
    _run({"verdicts": _host(*verdicts)}, _refs(verdicts=_ref(1, "harness.host_design_verdicts/1")), host_trace)
    _run({"verdicts": _set(*verdicts)}, trace=set_trace)
    built = [t.build(REGISTRY[CALC_ID], "ab" * 32) for t in (host_trace, set_trace)]
    assert built[0] == built[1]
