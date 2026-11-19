"""Property tests of `harness.column_review` (plan 0013 T4; spec 0013 AC8)."""

import copy
from typing import Any, cast

from eng_contract.canonical import payload_sha256
from eng_contract.verdicts import VerdictStatus
from hypothesis import given, settings
from hypothesis import strategies as st

from eng_harness.calc import CalcInput, CalcStatus, InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.kinds.calcs import CalcMeta
from eng_harness.kinds.column_design import ColumnReview

CALC_ID = "harness.column_review"
CODE_CHECKS = (
    ("max_axial_strength", "aci318_14.22_4_2_1.max_axial_strength", "22.4.2.1", "kN", 0.0, "ULS1"),
    ("axial_flexure_uniaxial", "aci318_14.22_4_1_1.axial_flexure_uniaxial", "22.4.1.1", "kN.m", 0.0, "ULS1"),
    (
        "longitudinal_reinforcement_limits",
        "aci318_14.10_6_1_1.longitudinal_reinforcement_limits",
        "10.6.1.1",
        "mm2",
        None,
        None,
    ),
)
KINDS = {
    "selection": "harness.column_selection/1",
    "host": "harness.host_design_verdicts/1",
    "max_axial_strength": "verdicts.set/1",
    "axial_flexure_uniaxial": "verdicts.set/1",
    "longitudinal_reinforcement_limits": "verdicts.set/1",
    "items": "harness.column_check_items/1",
    "previous": "harness.column_review/1",
    "basis": "basis.design_basis/1",
}
REFS = {name: f"res_01KCR{'0' * 20}{n}" for n, name in enumerate(KINDS, 1)}
SHA = "a" * 64
FRAMES = ["C1", "C2", "C3", "C4"]
LIMITS = st.sampled_from([0.8, 0.9, 1.0, 1.2])
RATIOS = st.sampled_from([0.1, 0.25, 0.5, 0.75, 0.85, 0.95, 1.05, 1.3, 1.6])


def _calc_header(calc_id: str) -> dict[str, Any]:
    return {
        "calc": {"id": calc_id, "version": 1, "content_sha256": SHA, "status": "draft"},
        "draft": True,
        "trace": {
            "calc_id": calc_id,
            "calc_version": "1",
            "content_sha256": SHA,
            "inputs": [],
            "constants": [],
            "steps": [],
            "outputs": [],
        },
    }


def _verdict_counts(verdicts: list[dict[str, Any]]) -> dict[str, int]:
    return {s.value: sum(1 for v in verdicts if v["status"] == s.value) for s in VerdictStatus}


@st.composite
def _host_verdict(draw: st.DrawFn, frame_id: str) -> dict[str, Any]:
    limit = draw(LIMITS)
    status = draw(st.sampled_from(["PASS", "FAIL", "NEEDS_ENGINEER"]))
    ratio: float | None
    if status == "NEEDS_ENGINEER":
        ratio = None
    elif status == "PASS":
        ratio = draw(st.sampled_from([0.2, 0.4, 0.6, limit]))
    else:
        ratio = round(limit + draw(st.sampled_from([0.1, 0.3, 0.6])), 4)
    return {
        "source": "host",
        "check_id": draw(st.sampled_from(["host.steel_design_ratio", "host.concrete_design_ratio"])),
        "code": "host_steel_design",
        "clause": None,
        "subject": {"kind": "frame", "id": frame_id, "station_mm": None, "case": "ULS1"},
        "demand": None,
        "capacity": None,
        "ratio": ratio,
        "ratio_limit": limit,
        "status": status,
        "governing": False,
        "trace_ref": None,
        "assumptions": [],
    }


@st.composite
def _code_verdict(
    draw: st.DrawFn,
    frame_id: str,
    check_id: str,
    clause: str,
    unit: str,
    station_mm: float | None,
    case: str | None,
    trace_index: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    limit = draw(LIMITS)
    status = draw(st.sampled_from(["PASS", "FAIL", "NEEDS_ENGINEER"]))
    ratio: float | None
    demand: dict[str, Any] | None
    capacity: dict[str, Any] | None
    if status == "NEEDS_ENGINEER":
        ratio = None
        demand = None
        capacity = None
    else:
        ratio = draw(st.sampled_from([0.3, 0.5, limit]) if status == "PASS" else st.sampled_from([1.25, 1.5, 2.0]))
        if status == "FAIL" and ratio <= limit:
            ratio = round(limit + 0.25, 4)
        cap_val = 1000.0
        demand = {"value": round(ratio * cap_val, 4), "unit": unit}
        capacity = {"value": cap_val, "unit": unit}
    verdict: dict[str, Any] = {
        "source": "code_pack",
        "check_id": check_id,
        "code": "ACI 318-14",
        "clause": clause,
        "subject": {"kind": "frame", "id": frame_id, "station_mm": station_mm, "case": case},
        "demand": demand,
        "capacity": capacity,
        "ratio": ratio,
        "ratio_limit": limit,
        "status": status,
        "governing": False,
        "trace_ref": f"#/traces/{trace_index}",
        "assumptions": [],
    }
    trace = {
        "calc_id": check_id,
        "calc_version": "0.1.0",
        "content_sha256": SHA,
        "inputs": [],
        "constants": [],
        "steps": [],
        "outputs": [],
    }
    return verdict, trace


@st.composite
def _review_inputs(draw: st.DrawFn) -> tuple[dict[str, Any], dict[str, str]]:
    selected = draw(st.lists(st.sampled_from(FRAMES[:3]), min_size=1, max_size=3, unique=True))
    all_frames = [*selected, "B1"]
    columns = [
        {
            "frame_id": fid,
            "section": "C40",
            "shape": "rectangular",
            "material": "C30",
            "story": "L1",
            "length_mm": 3000.0,
        }
        for fid in selected
    ]
    host_verdicts = [draw(_host_verdict(draw(st.sampled_from(all_frames)))) for _ in range(draw(st.integers(0, 5)))]
    fields: dict[str, Any] = {
        "selection": _calc_header("harness.column_select")
        | {"status": "PASS", "columns": columns, "excluded": [], "issues": []},
        "host": _calc_header("harness.host_design_verdicts")
        | {"verdicts": host_verdicts, "traces": [], "counts": _verdict_counts(host_verdicts)},
        "items": _calc_header("harness.column_demands")
        | {
            "items": {check_id: [] for _, check_id, *_ in CODE_CHECKS},
            "not_checked": [
                {"frame_id": fid, "code": "AXES_UNDECLARED", "gap": "CW-G9"} for fid in selected if draw(st.booleans())
            ],
        },
        "basis": {
            "template": None,
            "fields": {
                "report.top_n": {
                    "value": draw(st.integers(1, 6)),
                    "unit": None,
                    "source": "engineer:trial@2026-11-01T00:00:00.000Z",
                    "confirmed": True,
                    "citation": None,
                }
            },
        },
    }
    for name, check_id, clause, unit, station_mm, case in CODE_CHECKS:
        if draw(st.booleans()):
            verdicts: list[dict[str, Any]] = []
            traces: list[dict[str, Any]] = []
            for idx in range(draw(st.integers(0, 4))):
                st_val = draw(st.sampled_from([0.0, 3000.0])) if station_mm is not None else None
                v, t = draw(_code_verdict(draw(st.sampled_from(all_frames)), check_id, clause, unit, st_val, case, idx))
                verdicts.append(v)
                traces.append(t)
            fields[name] = {"verdicts": verdicts, "traces": traces, "counts": _verdict_counts(verdicts), "draft": True}
    if draw(st.booleans()):
        prev_members = [
            {
                "frame_id": draw(st.sampled_from(selected)),
                "source": "code_pack",
                "check_id": CODE_CHECKS[0][1],
                "status": draw(st.sampled_from(["PASS", "FAIL", "NEEDS_ENGINEER"])),
                "ratio": draw(st.none() | RATIOS),
            }
        ]
        fields["previous"] = _calc_header("harness.column_review") | {
            "columns": [
                {
                    "frame_id": prev_members[0]["frame_id"],
                    "status": prev_members[0]["status"],
                    "host_status": "NOT_APPLICABLE",
                    "code_status": prev_members[0]["status"],
                    "governing": None,
                    "not_checked": [],
                    "gaps": [],
                }
            ],
            "failing": [prev_members[0]["frame_id"]] if prev_members[0]["status"] == "FAIL" else [],
            "attention": [prev_members[0]["frame_id"]] if prev_members[0]["status"] == "NEEDS_ENGINEER" else [],
            "top": {"n": 0, "of_total": 0, "rows": [], "label": "top 0 of 0 by ratio"},
            "members": prev_members,
            "changes": {
                "newly_failing": [],
                "newly_passing": [],
                "other_changes": [],
                "appeared": [],
                "disappeared": [],
            },
            "complete": True,
        }
    refs = {name: REFS[name] for name in fields}
    return fields, refs


@settings(derandomize=True, max_examples=60, deadline=None)
@given(_review_inputs())
def test_ratios_are_referenced_not_computed(case: tuple[dict[str, Any], dict[str, str]]) -> None:
    """AC8: every ratio in `governing`, `top`, `members` and `changes` equals the referenced verdict's ratio."""
    fields, refs = case
    definition = REGISTRY[CALC_ID]
    digest = REGISTRY.content_hash(CALC_ID)
    input_type = cast(type[CalcInput], definition.input_type)
    meta = InputMeta(
        refs={
            name: RefMeta(
                result_id=result_id,
                kind=KINDS[name],
                complete=True,
                model_id=None,
                model_revision=None,
                parents=(),
                producer_tool="fixture_tool",
            )
            for name, result_id in refs.items()
        }
    )
    trace = TraceBuilder()
    body = definition(input_type.model_validate(fields), meta, trace).model_dump(mode="json")
    payload = body | {
        "calc": CalcMeta(
            id=CALC_ID, version=definition.version, content_sha256=digest, status=CalcStatus.DRAFT
        ).model_dump(mode="json"),
        "draft": True,
        "trace": trace.build(definition, digest).model_dump(mode="json"),
    }
    ColumnReview.model_validate(payload)
    verdict_sets: dict[str, list[dict[str, Any]]] = {
        refs[name]: fields[name]["verdicts"] for name in ("host", *(n for n, *_ in CODE_CHECKS)) if name in fields
    }
    selected_ids = {c["frame_id"] for c in fields["selection"]["columns"]}
    selected_verdicts = [
        v
        for verdicts in verdict_sets.values()
        for v in verdicts
        if v["subject"]["kind"] == "frame" and v["subject"]["id"] in selected_ids
    ]
    for col in payload["columns"]:
        if col["governing"] is not None:
            result_id, _, pointer = col["governing"]["ref"].partition("#/verdicts/")
            verdict = verdict_sets[result_id][int(pointer)]
            assert verdict["subject"]["kind"] == "frame"
            assert verdict["subject"]["id"] == col["frame_id"]
            assert verdict["ratio"] is not None
            assert col["governing"]["ratio"] == verdict["ratio"]
        else:
            assert all(v["ratio"] is None for v in selected_verdicts if v["subject"]["id"] == col["frame_id"])
    for row in payload["top"]["rows"]:
        assert any(
            v["subject"]["id"] == row["subject_id"]
            and v["check_id"] == row["check_id"]
            and v["subject"]["case"] == row["case"]
            and v["subject"]["station_mm"] == row["station_mm"]
            and v["status"] == row["status"]
            and v["ratio_limit"] == row["ratio_limit"]
            and v["ratio"] == row["ratio"]
            for v in selected_verdicts
        )
    for member in payload["members"]:
        matching_ratios = [
            v["ratio"]
            for v in selected_verdicts
            if v["subject"]["id"] == member["frame_id"]
            and v["source"] == member["source"]
            and v["check_id"] == member["check_id"]
            and v["ratio"] is not None
        ]
        assert member["ratio"] == (max(matching_ratios) if matching_ratios else None)
    if "previous" in fields:
        prev_by_key = {(m["frame_id"], m["source"], m["check_id"]): m for m in fields["previous"]["members"]}
        curr_by_key = {(m["frame_id"], m["source"], m["check_id"]): m for m in payload["members"]}
        changes = payload["changes"]
        for change in [*changes["newly_failing"], *changes["newly_passing"], *changes["other_changes"]]:
            key = (change["frame_id"], change["source"], change["check_id"])
            assert change["previous_ratio"] == prev_by_key[key]["ratio"]
            assert change["ratio"] == curr_by_key[key]["ratio"]
        for item in changes["appeared"]:
            assert item["ratio"] == curr_by_key[(item["frame_id"], item["source"], item["check_id"])]["ratio"]
        for item in changes["disappeared"]:
            assert item["ratio"] == prev_by_key[(item["frame_id"], item["source"], item["check_id"])]["ratio"]


@settings(derandomize=True, max_examples=40, deadline=None)
@given(_review_inputs(), st.data())
def test_permutation_invariant(case: tuple[dict[str, Any], dict[str, str]], data: st.DataObject) -> None:
    """Permuting selection columns, not_checked rows and previous members keeps the complete payload identical."""
    fields, refs = case
    mixed = copy.deepcopy(fields)
    mixed["selection"]["columns"] = data.draw(st.permutations(mixed["selection"]["columns"]))
    mixed["items"]["not_checked"] = data.draw(st.permutations(mixed["items"]["not_checked"]))
    if "previous" in mixed:
        mixed["previous"]["members"] = data.draw(st.permutations(mixed["previous"]["members"]))

    def run_one(inp_fields: dict[str, Any]) -> tuple[dict[str, Any], str]:
        definition = REGISTRY[CALC_ID]
        digest = REGISTRY.content_hash(CALC_ID)
        input_type = cast(type[CalcInput], definition.input_type)
        meta = InputMeta(
            refs={
                name: RefMeta(
                    result_id=result_id,
                    kind=KINDS[name],
                    complete=True,
                    model_id=None,
                    model_revision=None,
                    parents=(),
                    producer_tool="fixture_tool",
                )
                for name, result_id in refs.items()
            }
        )
        trace = TraceBuilder()
        body = definition(input_type.model_validate(inp_fields), meta, trace).model_dump(mode="json")
        payload = body | {
            "calc": CalcMeta(
                id=CALC_ID, version=definition.version, content_sha256=digest, status=CalcStatus.DRAFT
            ).model_dump(mode="json"),
            "draft": True,
            "trace": trace.build(definition, digest).model_dump(mode="json"),
        }
        ColumnReview.model_validate(payload)
        return payload, payload_sha256(payload)

    assert run_one(mixed) == run_one(fields)
