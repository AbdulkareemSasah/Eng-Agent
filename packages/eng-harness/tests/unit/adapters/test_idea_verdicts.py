"""IDEA verdict-set construction (plan 0014 T5; spec 0014 AC14, AC15, section 4.5)."""

from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.verdicts import Verdict, VerdictSource, VerdictStatus

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
    """AC14: connection passed that disagrees with its checks adds one idea:connection NEEDS_ENGINEER."""
    connections = [
        _connection(
            passed=True,
            checks=[_check("Welds", 112.0, status=False)],
        )
    ]
    payload = idea_verdicts.build_verdict_set(
        connections,
        design_code="AISC",
        route="native",
        load_map_confirmed=True,
    )
    extra = [v for v in payload.verdicts if v.check_id == "idea:connection"]
    assert len(extra) == 1
    assert extra[0].status is VerdictStatus.NEEDS_ENGINEER
    assert extra[0].subject.id == "CON1"


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
