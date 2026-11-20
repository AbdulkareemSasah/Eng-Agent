"""Property: IDEA host-verdict mapping never upgrades a host FAIL (plan 0014 T5; spec 0014 AC13)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from eng_contract.verdicts import VerdictStatus
from eng_harness.adapters.idea import _verdicts as idea_verdicts

_finite = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
_names = st.text(min_size=0, max_size=40)


@settings(derandomize=True, max_examples=200, deadline=None)
@given(check_value=_finite, name=_names)
def test_no_status_upgrade(check_value: float, name: str) -> None:
    """AC13: when the host reports check_status false (not skipped), the adapter never emits PASS."""
    check = {
        "name": name,
        "check_value": check_value,
        "check_status": False,
        "skipped": False,
        "message": "host fail",
        "load_case_id": None,
    }
    verdict = idea_verdicts.map_check(
        check,
        connection_name="CON1",
        design_code="AISC",
        route="native",
    )
    assert verdict.status is not VerdictStatus.PASS
    assert verdict.source.value == "host"
