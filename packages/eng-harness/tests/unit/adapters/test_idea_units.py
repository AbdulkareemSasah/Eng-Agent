"""IDEA unit header and canonical load read-back (plan 0014 T3/T7; spec 0014 AC16, section 4.6)."""

from __future__ import annotations

from typing import Any

import pytest
from eng_contract.units import convert


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


def test_read_back_loads_canonical() -> None:
    """AC16: stored read-back loads convert host N / N.m to canonical kN / kN.m (section 4.6)."""
    from eng_harness.adapters.idea import _loads as loads

    host_effect: dict[str, Any] = {
        "id": 1,
        "name": "LE1",
        "checkEquilibrium": True,
        "forcesOnSegments": [
            {
                "beamSegmentId": 1,
                "position": 0.0,
                "n": 10000.0,
                "qy": 0.0,
                "qz": -5000.0,
                "mx": 0.0,
                "my": 2000.0,
                "mz": 0.0,
            }
        ],
        "forcesPercentageOnSegments": [],
    }
    canonical = loads.host_loads_to_canonical(
        connection="CON1",
        effects=[host_effect],
        file_sha256="ab" * 32,
    )
    seg = canonical.effects[0].segments[0]
    assert seg.N_kN == convert(10000.0, "N", "kN")
    assert seg.Qz_kN == convert(-5000.0, "N", "kN")
    assert seg.My_kNm == convert(2000.0, "N.m", "kN.m")
    assert seg.beam_segment_id == 1
    assert seg.position_host == 0.0
    assert canonical.percentage_segments_present is False
