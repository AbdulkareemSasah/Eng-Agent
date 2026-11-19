"""Property tests of harness.footing_layout (plan 0010 T5; spec 0010 AC8, section 4.4.3)."""

from fractions import Fraction
from typing import Any

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from eng_harness.calc import InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs.footing.layout import LayoutBody, LayoutInput, footing_layout

_BASIS_SRC = "engineer:synthetic@2026-01-01T00:00:00.000Z"
_META = InputMeta(
    refs={
        name: RefMeta(
            result_id=f"res_0000000000000000000000000{i}",
            kind=kind,
            complete=True,
            model_id=None,
            model_revision=None,
            parents=(),
            producer_tool="fixture_tool",
        )
        for i, (name, kind) in enumerate(
            [
                ("dims", "harness.footing_dims/1"),
                ("subjects", "harness.footing_subjects/1"),
                ("basis", "basis.design_basis/1"),
            ],
            start=1,
        )
    }
)


def _field(value: Any, unit: str | None) -> dict[str, Any]:
    return {"value": value, "unit": unit, "source": _BASIS_SRC, "confirmed": True, "citation": None}


def _dim_row(fid: str, lx: float, ly: float, h: float, s: float) -> dict[str, Any]:
    return {
        "id": fid,
        "Lx_mm": lx,
        "Ly_mm": ly,
        "h_mm": h,
        "s_mm": s,
        "source": "calc",
        "plan_at_max": False,
        "depth_at_max": False,
        "spacing_at_min": False,
        "status": "OK",
        "reason": None,
    }


def _calc_meta(calc_id: str) -> dict[str, Any]:
    digest = "ab" * 32
    return {
        "calc": {"id": calc_id, "version": 1, "content_sha256": digest, "status": "draft"},
        "draft": True,
        "trace": {
            "calc_id": calc_id,
            "calc_version": "1",
            "content_sha256": digest,
            "inputs": [],
            "constants": [],
            "steps": [],
            "outputs": [],
        },
    }


def _subject(fid: str) -> dict[str, Any]:
    return {"id": fid, "joint": fid, "column": f"C_{fid}", "x_mm": 0.0, "y_mm": 0.0, "cx_mm": 300.0, "cy_mm": 300.0}


@settings(derandomize=True, max_examples=200, deadline=None)
@given(
    db=st.sampled_from([10.0, 12.0, 16.0, 20.0, 25.0, 32.0]),
    cover=st.floats(min_value=0.0, max_value=150.0, allow_nan=False, allow_infinity=False),
    extra_h=st.floats(min_value=1.0, max_value=2000.0, allow_nan=False, allow_infinity=False),
    extra_x=st.floats(min_value=0.5, max_value=8000.0, allow_nan=False, allow_infinity=False),
    extra_y=st.floats(min_value=0.5, max_value=8000.0, allow_nan=False, allow_infinity=False),
    s1=st.floats(min_value=25.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    s2=st.floats(min_value=25.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    bottom_layer=st.sampled_from(["x_bottom", "y_bottom"]),
    reaction_point=st.sampled_from(["top_of_footing", "base_of_footing"]),
)
def test_spacing_bound(
    db: float,
    cover: float,
    extra_h: float,
    extra_x: float,
    extra_y: float,
    s1: float,
    s2: float,
    bottom_layer: str,
    reaction_point: str,
) -> None:
    """AC8: actual spacing <= s, n = 2 or span/(n - 2) > s, and As grows strictly with bar count."""
    h = cover + 1.5 * db + extra_h
    ly = 2.0 * cover + db + extra_x
    lx = 2.0 * cover + db + extra_y
    span_x = Fraction(ly) - 2 * Fraction(cover) - Fraction(db)
    span_y = Fraction(lx) - 2 * Fraction(cover) - Fraction(db)
    assume(span_x > 0 and span_y > 0)
    assume(Fraction(h) - Fraction(cover) - Fraction(3, 2) * Fraction(db) > 0)

    inp = LayoutInput.model_validate(
        {
            "dims": _calc_meta("harness.footing_plan_size")
            | {"footings": [_dim_row("J1", lx, ly, h, s1), _dim_row("J2", lx, ly, h, s2)]},
            "subjects": _calc_meta("harness.footing_subjects")
            | {"subjects": [_subject("J1"), _subject("J2")], "excluded": []},
            "basis": {
                "template": None,
                "fields": {
                    "reinforcement.bar_diameter_mm": _field(db, "mm"),
                    "reinforcement.bottom_layer": _field(bottom_layer, None),
                    "durability.cover_footing_mm": _field(cover, "mm"),
                    "foundation.reaction_point": _field(reaction_point, None),
                },
            },
        }
    )
    out = footing_layout(inp, _META, TraceBuilder())
    assert isinstance(out, LayoutBody)
    r1, r2 = out.footings
    for row, s_in in ((r1, s1), (r2, s2)):
        assert row.status == "OK"
        assert row.reason is None
        s_frac = Fraction(s_in)
        assert row.n_x >= 2
        assert row.n_y >= 2
        assert Fraction(row.s_x_mm) <= s_frac
        assert Fraction(row.s_y_mm) <= s_frac
        assert row.n_x == 2 or span_x / (row.n_x - 2) > s_frac
        assert row.n_y == 2 or span_y / (row.n_y - 2) > s_frac
    for a, b in ((r1, r2), (r2, r1)):
        if a.n_x > b.n_x:
            assert a.As_x_mm2 > b.As_x_mm2
        elif a.n_x == b.n_x:
            assert a.As_x_mm2 == b.As_x_mm2
        if a.n_y > b.n_y:
            assert a.As_y_mm2 > b.As_y_mm2
        elif a.n_y == b.n_y:
            assert a.As_y_mm2 == b.As_y_mm2
