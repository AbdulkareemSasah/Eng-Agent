"""IDEA unit header: declared N and N.m for native loads; missing for idea_set_loads (plan 0014 T3; spec 0014 AC16)."""

import pytest


def test_declared_units_and_status() -> None:
    """AC16: native loads declare N and N.m as declared; idea_set_loads has no unit with status missing."""
    from eng_harness.adapters.idea import idea_allowlist

    allowlist = idea_allowlist()
    rows = [(e.tool, e.field, e.unit, e.unit_status) for e in allowlist.units]

    assert ("idea_native_get_loads", "force", "N", "declared") in rows
    assert ("idea_native_get_loads", "moment", "N.m", "declared") in rows
    assert ("idea_native_set_loads", "force", "N", "declared") in rows
    assert ("idea_native_set_loads", "moment", "N.m", "declared") in rows
    assert ("idea_set_loads", "forces", None, "missing") in rows

    get_header = allowlist.descriptor("idea_native_get_loads").unit_header
    set_header = allowlist.descriptor("idea_native_set_loads").unit_header
    assert {(e.field, e.unit, e.unit_status) for e in get_header} == {
        ("force", "N", "declared"),
        ("moment", "N.m", "declared"),
    }
    assert {(e.field, e.unit, e.unit_status) for e in set_header} == {
        ("force", "N", "declared"),
        ("moment", "N.m", "declared"),
    }
    with pytest.raises(KeyError):
        allowlist.descriptor("idea_set_loads")
