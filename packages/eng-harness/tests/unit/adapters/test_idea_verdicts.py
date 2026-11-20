"""IDEA verdict-set construction (plan 0014 T5; spec 0014 AC14, AC15, section 4.5)."""

from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.verdicts import Subject, SubjectKind, Verdict, VerdictSource, VerdictStatus

from eng_harness.adapters.idea import _verdicts as idea_verdicts


def _check(
    name: str,
    value: float,
    *,
    status: bool = True,
    skipped: bool = False,
    case: str | None = "LC1",
) -> dict[str, Any]:
    return {
        "name": name,
        "check_value": value,
        "check_status": status,
        "skipped": skipped,
        "message": "OK",
        "load_case_id": case,
    }


def _connection(
    name: str = "CON1",
    *,
    connection_id: int | str = 1,
    passed: bool = True,
    calculated: bool = True,
    checks: list[dict[str, Any]] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "connection_id": connection_id,
        "name": name,
        "passed": passed,
        "calculated": calculated,
        "checks": checks if checks is not None else [_check("Plates", 87.5)],
        "errors": errors or [],
        "warnings": [],
    }


def test_set_properties() -> None:
    """AC14: one verdicts.set/1, counts match, draft while the load map is unconfirmed, governing by largest ratio."""
    connections = [
        _connection(
            "CON1",
            checks=[_check("Plates", 50.0), _check("Bolts", 90.0), _check("Skip", 10.0, skipped=True)],
        ),
        _connection(
            "CON2",
            connection_id=2,
            checks=[_check("Plates", 80.0), _check("Bolts", 80.0)],
        ),
    ]
    payload = idea_verdicts.build_verdict_set(
        connections,
        design_code="AISC",
        route="native",
        load_map_confirmed=False,
    )
    assert isinstance(payload, VerdictSet)
    assert payload.draft is True
    assert payload.traces == []
    assert all(v.trace_ref is None for v in payload.verdicts)
    assert all(v.source is VerdictSource.HOST for v in payload.verdicts)
    tally = {s: sum(1 for v in payload.verdicts if v.status is s) for s in VerdictStatus}
    assert payload.counts == tally

    con1 = [v for v in payload.verdicts if v.subject.id == "CON1" and v.status is not VerdictStatus.NOT_APPLICABLE]
    governing = [v for v in con1 if v.governing]
    assert len(governing) == 1
    assert governing[0].check_id == "idea:bolts"
    assert governing[0].ratio == 0.9

    con2 = [v for v in payload.verdicts if v.subject.id == "CON2"]
    assert all(v.governing for v in con2)  # tie at 0.8: both governing

    confirmed = idea_verdicts.build_verdict_set(
        connections,
        design_code="AISC",
        route="native",
        load_map_confirmed=True,
    )
    assert confirmed.draft is False

    rest = idea_verdicts.build_verdict_set(
        connections,
        design_code="AISC",
        route="rest",
        load_map_confirmed=True,
    )
    assert rest.draft is True  # route rest always draft (IG-5 / §4.5)


def test_host_only() -> None:
    """AC14: a code-pack verdict in the set is a construction error; host-only sets validate."""
    host = idea_verdicts.build_verdict_set(
        [_connection()],
        design_code="AISC",
        route="native",
        load_map_confirmed=True,
    )
    assert all(v.source is VerdictSource.HOST for v in host.verdicts)

    code_pack = Verdict(
        source=VerdictSource.CODE_PACK,
        check_id="aci318_14.flexure.beam_moment",
        code="ACI 318-14",
        clause="22.3",
        subject=host.verdicts[0].subject,
        demand=None,
        capacity=None,
        ratio=0.5,
        status=VerdictStatus.NEEDS_ENGINEER,
        trace_ref="#/traces/0",
        assumptions=[],
    )
    with pytest.raises(ValueError, match=r"code_pack"):
        idea_verdicts.require_host_only([*host.verdicts, code_pack])


def test_empty_is_precondition() -> None:
    """AC14: no calculated connection is PRECONDITION_FAILED analysis_current, never an empty passing set."""
    with pytest.raises(ContractError) as empty:
        idea_verdicts.build_verdict_set(
            [],
            design_code="AISC",
            route="native",
            load_map_confirmed=True,
        )
    assert empty.value.detail.code is ErrorCode.PRECONDITION_FAILED
    assert empty.value.detail.precondition is Precondition.analysis_current

    with pytest.raises(ContractError) as uncalculated:
        idea_verdicts.build_verdict_set(
            [_connection(calculated=False, checks=[])],
            design_code="AISC",
            route="native",
            load_map_confirmed=True,
        )
    assert uncalculated.value.detail.code is ErrorCode.PRECONDITION_FAILED
    assert uncalculated.value.detail.precondition is Precondition.analysis_current


def test_passed_disagreement() -> None:
    """AC14: when passed is true, disagree on a non-skipped check_status false or mapped FAIL/ERROR.

    Host-pass / high-ratio (103/true) is NEEDS_ENGINEER on the check alone and does not add idea:connection.
    Host-fail / low-ratio (80/false) with passed=true is the real passed-vs-checks disagreement.
    """
    disagree = idea_verdicts.build_verdict_set(
        [_connection(passed=True, checks=[_check("Welds", 80.0, status=False)])],
        design_code="AISC",
        route="native",
        load_map_confirmed=True,
    )
    extra_disagree = [v for v in disagree.verdicts if v.check_id == "idea:connection"]
    assert len(extra_disagree) == 1
    assert extra_disagree[0].status is VerdictStatus.NEEDS_ENGINEER
    assert extra_disagree[0].subject.id == "CON1"

    host_fail = idea_verdicts.build_verdict_set(
        [_connection(passed=True, checks=[_check("Welds", 112.0, status=False)])],
        design_code="AISC",
        route="native",
        load_map_confirmed=True,
    )
    assert len([v for v in host_fail.verdicts if v.check_id == "idea:connection"]) == 1

    agree_high = idea_verdicts.build_verdict_set(
        [_connection(passed=True, checks=[_check("Bolts", 103.0, status=True)])],
        design_code="AISC",
        route="native",
        load_map_confirmed=True,
    )
    assert [v for v in agree_high.verdicts if v.check_id == "idea:connection"] == []
    assert agree_high.verdicts[0].status is VerdictStatus.NEEDS_ENGINEER
    assert agree_high.verdicts[0].ratio == 1.03


def test_code_label_and_assumptions() -> None:
    """AC15: code is the design-basis value; route rest assumptions name the unread host code; never ECEN."""
    native = idea_verdicts.map_check(
        _check("Plates", 50.0),
        connection_name="CON1",
        design_code="AISC 360-16",
        route="native",
    )
    assert native.code == "AISC 360-16"
    assert "ECEN" not in native.code
    assert "design code declared in the design basis, not read from the host" not in native.assumptions

    rest = idea_verdicts.map_check(
        _check("Plates", 50.0),
        connection_name="CON1",
        design_code="AISC 360-16",
        route="rest",
    )
    assert rest.code == "AISC 360-16"
    assert "design code declared in the design basis, not read from the host" in rest.assumptions
    assert "loads as stored in the opened file" in rest.assumptions
    assert "ECEN" not in "".join(rest.assumptions)


def test_slug_and_empty_name() -> None:
    """AC13 / §4.5: check_id is idea:<slug>; empty name becomes idea:check."""
    assert idea_verdicts.slug("Plates") == "plates"
    assert idea_verdicts.slug("  Bolt Check!  ") == "bolt_check_"
    assert idea_verdicts.slug("") == "check"
    assert idea_verdicts.slug("   ") == "check"

    empty = idea_verdicts.map_check(
        {"check_value": 40.0, "check_status": True, "skipped": False},
        connection_name="CON1",
        design_code="AISC",
        route="native",
    )
    assert empty.check_id == "idea:check"
    assert empty.subject.case is None


def test_map_check_every_field_and_case() -> None:
    """AC13 / §4.5: every Verdict field; load_case_id becomes subject.case (cut to 200)."""
    long_case = "C" * 250
    verdict = idea_verdicts.map_check(
        _check("Plate Check", 87.5, case=long_case),
        connection_name="JOINT-A",
        design_code="AISC",
        route="native",
    )
    assert verdict.source is VerdictSource.HOST
    assert verdict.check_id == "idea:plate_check"
    assert verdict.code == "AISC"
    assert verdict.clause is None
    assert verdict.subject.kind.value == "joint"
    assert verdict.subject.id == "JOINT-A"
    assert verdict.subject.station_mm is None
    assert verdict.subject.case == "C" * 200
    assert verdict.demand is None
    assert verdict.capacity is None
    assert verdict.ratio == 0.875
    assert verdict.ratio_limit == 1.0
    assert verdict.status is VerdictStatus.PASS
    assert verdict.governing is False
    assert verdict.trace_ref is None
    assert verdict.assumptions == [
        idea_verdicts.HOST_ASSUMPTION,
    ]

    none_case = idea_verdicts.map_check(
        _check("Plates", 50.0, case=None),
        connection_name="CON1",
        design_code="AISC",
        route="native",
    )
    assert none_case.subject.case is None


def test_map_check_missing_keys_use_host_defaults() -> None:
    """AC13 / §4.5: missing skipped/check_status/check_value arrive as false/false/0."""
    # Missing skipped → false (calculated); missing check_status → false; value 80 → NEEDS_ENGINEER.
    missing_status = idea_verdicts.map_check(
        {"name": "Welds", "check_value": 80.0},
        connection_name="CON1",
        design_code="AISC",
        route="native",
    )
    assert missing_status.status is VerdictStatus.NEEDS_ENGINEER
    assert missing_status.ratio == 0.8

    # Missing check_value → 0 with check_status true → NEEDS_ENGINEER (zero-utilization rule).
    missing_value = idea_verdicts.map_check(
        {"name": "Plates", "check_status": True, "skipped": False},
        connection_name="CON1",
        design_code="AISC",
        route="native",
    )
    assert missing_value.status is VerdictStatus.NEEDS_ENGINEER
    assert missing_value.ratio == 0.0
    assert any("utilization is exactly zero" in a for a in missing_value.assumptions)

    # Missing skipped with a clear pass stays PASS (default skipped false).
    missing_skipped = idea_verdicts.map_check(
        {"name": "Plates", "check_value": 50.0, "check_status": True},
        connection_name="CON1",
        design_code="AISC",
        route="native",
    )
    assert missing_skipped.status is VerdictStatus.PASS
    assert missing_skipped.ratio == 0.5


def test_passed_false_does_not_add_connection_verdict() -> None:
    """AC14: when passed is false, no idea:connection disagreement is added (both directions)."""
    payload = idea_verdicts.build_verdict_set(
        [_connection(passed=False, checks=[_check("Welds", 80.0, status=False)])],
        design_code="AISC",
        route="native",
        load_map_confirmed=True,
    )
    assert [v for v in payload.verdicts if v.check_id == "idea:connection"] == []
    assert payload.verdicts[0].status is VerdictStatus.NEEDS_ENGINEER


def test_passed_disagreement_ignores_skipped_and_non_mapping() -> None:
    """AC14: skipped checks and non-mapping rows do not count as passed disagreement."""
    checks: list[Any] = [
        "not-a-check",
        _check("SkipFail", 80.0, status=False, skipped=True),
        _check("Plates", 50.0, status=True),
    ]
    payload = idea_verdicts.build_verdict_set(
        [_connection(passed=True, checks=checks)],
        design_code="AISC",
        route="native",
        load_map_confirmed=True,
    )
    assert [v for v in payload.verdicts if v.check_id == "idea:connection"] == []
    assert [v.check_id for v in payload.verdicts] == ["idea:skipfail", "idea:plates"]


def test_passed_disagreement_missing_check_keys() -> None:
    """AC14: missing skipped/check_status on a check still drive passed disagreement (§4.5 defaults)."""
    # No skipped key → false; check_status false → disagree.
    no_skipped = idea_verdicts.build_verdict_set(
        [
            _connection(
                passed=True,
                checks=[{"name": "Welds", "check_value": 80.0, "check_status": False}],
            )
        ],
        design_code="AISC",
        route="native",
        load_map_confirmed=True,
    )
    assert len([v for v in no_skipped.verdicts if v.check_id == "idea:connection"]) == 1

    # No check_status key → false; with ratio <= 1.0 → disagree.
    no_status = idea_verdicts.build_verdict_set(
        [
            _connection(
                passed=True,
                checks=[{"name": "Welds", "check_value": 80.0, "skipped": False}],
            )
        ],
        design_code="AISC",
        route="native",
        load_map_confirmed=True,
    )
    assert len([v for v in no_status.verdicts if v.check_id == "idea:connection"]) == 1


def test_connection_verdict_fields_and_governing_exclusion() -> None:
    """AC14: idea:connection carries every host field; it is never governing; later connections still are."""
    connections = [
        _connection(
            "CON1",
            passed=True,
            checks=[_check("Welds", 80.0, status=False)],
        ),
        _connection(
            "CON2",
            connection_id=2,
            passed=True,
            checks=[_check("Plates", 70.0), _check("Bolts", 90.0)],
        ),
    ]
    payload = idea_verdicts.build_verdict_set(
        connections,
        design_code="AISC",
        route="rest",
        load_map_confirmed=True,
    )
    extras = [v for v in payload.verdicts if v.check_id == "idea:connection"]
    assert len(extras) == 1
    connection = extras[0]
    assert connection.source is VerdictSource.HOST
    assert connection.code == "AISC"
    assert connection.clause is None
    assert connection.subject.kind.value == "joint"
    assert connection.subject.id == "CON1"
    assert connection.subject.station_mm is None
    assert connection.subject.case is None
    assert connection.demand is None
    assert connection.capacity is None
    assert connection.ratio is None
    assert connection.ratio_limit == 1.0
    assert connection.status is VerdictStatus.NEEDS_ENGINEER
    assert connection.governing is False
    assert connection.trace_ref is None
    assert "connection passed disagrees with its checks" in connection.assumptions
    assert idea_verdicts.HOST_ASSUMPTION in connection.assumptions
    assert "design code declared in the design basis, not read from the host" in connection.assumptions
    assert "loads as stored in the opened file" in connection.assumptions

    # build_verdict_set must pass route through to map_check (rest assumptions on check rows).
    welds = next(v for v in payload.verdicts if v.check_id == "idea:welds")
    assert "design code declared in the design basis, not read from the host" in welds.assumptions
    assert "loads as stored in the opened file" in welds.assumptions

    con2 = [v for v in payload.verdicts if v.subject.id == "CON2"]
    assert len(con2) == 2
    governing_con2 = next(v for v in con2 if v.governing)
    assert governing_con2.check_id == "idea:bolts"
    assert governing_con2.ratio == 0.9


def test_governing_after_all_none_ratios() -> None:
    """AC14: a connection with only None ratios does not stop governing on a later connection."""
    payload = idea_verdicts.build_verdict_set(
        [
            _connection("CON1", checks=[_check("Neg", -5.0)]),
            _connection(
                "CON2",
                connection_id=2,
                checks=[_check("Plates", 60.0), _check("Bolts", 85.0)],
            ),
        ],
        design_code="AISC",
        route="native",
        load_map_confirmed=True,
    )
    con2 = [v for v in payload.verdicts if v.subject.id == "CON2"]
    governing = [v for v in con2 if v.governing]
    assert len(governing) == 1
    assert governing[0].check_id == "idea:bolts"
    assert governing[0].ratio == 0.85


def test_default_connection_name_and_missing_passed() -> None:
    """AC14: empty connection name becomes 'connection'; missing passed is false (no disagreement)."""
    unnamed = idea_verdicts.build_verdict_set(
        [
            {
                "connection_id": 1,
                "passed": True,
                "calculated": True,
                "checks": [_check("Plates", 50.0)],
                "errors": [],
                "warnings": [],
            }
        ],
        design_code="AISC",
        route="native",
        load_map_confirmed=True,
    )
    assert unnamed.verdicts[0].subject.id == "connection"

    no_passed = idea_verdicts.build_verdict_set(
        [
            {
                "connection_id": 1,
                "name": "CON1",
                "calculated": True,
                "checks": [_check("Welds", 80.0, status=False)],
                "errors": [],
                "warnings": [],
            }
        ],
        design_code="AISC",
        route="native",
        load_map_confirmed=True,
    )
    assert [v for v in no_passed.verdicts if v.check_id == "idea:connection"] == []


def test_host_only_exact_message() -> None:
    """AC14: require_host_only raises the exact construction-error message."""
    with pytest.raises(
        ValueError,
        match=r"^a verdicts\.set of IDEA host checks may not contain a code_pack verdict$",
    ):
        idea_verdicts.require_host_only(
            [
                Verdict(
                    source=VerdictSource.CODE_PACK,
                    check_id="aci318_14.flexure.beam_moment",
                    code="ACI 318-14",
                    clause="22.3",
                    subject=Subject(kind=SubjectKind.JOINT, id="CON1"),
                    status=VerdictStatus.NEEDS_ENGINEER,
                    trace_ref="#/traces/0",
                    assumptions=[],
                )
            ]
        )


def test_empty_precondition_exact_message() -> None:
    """AC14: empty calculated set uses the exact PRECONDITION_FAILED message."""
    with pytest.raises(ContractError) as caught:
        idea_verdicts.build_verdict_set(
            [],
            design_code="AISC",
            route="native",
            load_map_confirmed=True,
        )
    assert caught.value.detail.message == "no calculated connection in the host reply"
    assert caught.value.detail.precondition is Precondition.analysis_current
