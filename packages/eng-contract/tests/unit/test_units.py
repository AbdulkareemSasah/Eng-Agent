"""Units of canonical/1 (plan T5; spec 3.5 and 4.7; AC30 to AC32, AC37, AC38).

Expected factors are in `tests/data/units/factors.json`, derived from the cited exact definitions with plain decimal
arithmetic (see `docs/verification/units.md`), not read back from the implementation.
"""

import json
import math
import sys
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from eng_contract.errors import ErrorCode
from eng_contract.units import (
    QUANTITY_KINDS,
    UNITS,
    CsiUnitSystem,
    Dimension,
    UnitError,
    UnitGapError,
    convert,
    convert_exact,
    csi_unit_system,
    kind_for_field,
    unit,
)

_ROWS = json.loads((Path(__file__).parent.parent / "data" / "units" / "factors.json").read_text(encoding="utf-8"))[
    "units"
]
_BY_SYMBOL = {row["symbol"]: row for row in _ROWS}
_EPS = sys.float_info.epsilon


def _factor(symbol: str) -> Fraction:
    return Fraction(_BY_SYMBOL[symbol]["factor"])


def _offset(symbol: str) -> Fraction:
    return Fraction(_BY_SYMBOL[symbol]["offset"])


def _expected(value: float, src: str, dst: str) -> float:
    """Correctly rounded float of the exact conversion, from the fixture factors."""
    kelvin = Fraction(value) * _factor(src) + _offset(src)
    return float((kelvin - _offset(dst)) / _factor(dst))


def test_factors_exact() -> None:
    for row in _ROWS:
        u = UNITS[row["symbol"]]
        assert u.symbol == row["symbol"]
        assert u.dimension == tuple(row["dimension"]), row["symbol"]
        assert u.factor == Fraction(row["factor"]), row["symbol"]
        assert u.pi_power == row["pi_power"], row["symbol"]
        assert u.offset == Fraction(row["offset"]), row["symbol"]
    # Defining values quoted from the sources, as decimals (not through the fixture).
    assert UNITS["lbf"].factor == Fraction("4.4482216152605")
    assert UNITS["kip"].factor == Fraction("4448.2216152605")
    assert UNITS["tonf"].factor == Fraction("9806.65")
    assert UNITS["deg"].factor * 180 == 1
    assert UNITS["deg"].pi_power == 1
    assert UNITS["degC"].offset == Fraction("273.15")


def test_every_unit_is_well_formed() -> None:
    assert len(UNITS) > 150
    for symbol, u in UNITS.items():
        assert u.symbol == symbol
        assert isinstance(u.dimension, Dimension)
        assert u.factor > 0
        assert u.pi_power in (0, 1)
        assert (u.offset != 0) <= (u.dimension.temperature == 1)
    assert unit("kN.m") is UNITS["kN.m"]
    with pytest.raises(TypeError):
        UNITS["x"] = UNITS["m"]  # type: ignore[index]


def test_named_units_of_the_spec_exist() -> None:
    names = (
        "mm",
        "cm",
        "m",
        "in",
        "ft",
        "mm2",
        "cm2",
        "m2",
        "in2",
        "ft2",
        "mm3",
        "cm3",
        "m3",
        "in3",
        "ft3",
        "mm4",
        "cm4",
        "m4",
        "in4",
        "ft4",
        "N",
        "kN",
        "MN",
        "kgf",
        "tonf",
        "lbf",
        "kip",
        "kN.m",
        "kN.mm",
        "N.mm",
        "kgf.m",
        "tonf.m",
        "lbf.in",
        "lbf.ft",
        "kip.in",
        "kip.ft",
        "MN.m",
        "Pa",
        "kPa",
        "MPa",
        "GPa",
        "N/mm2",
        "kN/m2",
        "kgf/cm2",
        "psi",
        "ksi",
        "psf",
        "ksf",
        "kN/m",
        "N/mm",
        "kgf/m",
        "tonf/m",
        "lbf/ft",
        "kip/ft",
        "kip/in",
        "kN/m3",
        "N/mm3",
        "kgf/m3",
        "tonf/m3",
        "pcf",
        "kip/ft3",
        "kip/in3",
        "kg",
        "t",
        "lb",
        "s",
        "min",
        "h",
        "deg",
        "rad",
        "degC",
        "degF",
        "K",
        "m/s2",
        "mm/s2",
        "ft/s2",
        "in/s2",
        "1",
    )
    assert [n for n in names if n not in UNITS] == []
    # Composition: the same force and length give the same moment however it is written.
    assert UNITS["kip.in"].factor == UNITS["kip"].factor * UNITS["in"].factor
    assert UNITS["lbf/in2"].factor == UNITS["psi"].factor
    assert UNITS["ksf"].dimension == UNITS["MPa"].dimension


def test_quantity_kinds() -> None:
    expected = {
        "length": ((1, 0, 0, 0, 0), "mm", "_mm"),
        "area": ((2, 0, 0, 0, 0), "mm2", "_mm2"),
        "section_modulus": ((3, 0, 0, 0, 0), "mm3", "_mm3"),
        "second_moment": ((4, 0, 0, 0, 0), "mm4", "_mm4"),
        "force": ((1, 1, -2, 0, 0), "kN", "_kN"),
        "moment": ((2, 1, -2, 0, 0), "kN.m", "_kNm"),
        "stress": ((-1, 1, -2, 0, 0), "MPa", "_MPa"),
        "line_load": ((0, 1, -2, 0, 0), "kN/m", "_kN_m"),
        "area_load": ((-1, 1, -2, 0, 0), "kPa", "_kPa"),
        "unit_weight": ((-2, 1, -2, 0, 0), "kN/m3", "_kN_m3"),
        "mass": ((0, 1, 0, 0, 0), "kg", "_kg"),
        "angle": ((0, 0, 0, 0, 1), "deg", "_deg"),
        "time": ((0, 0, 1, 0, 0), "s", "_s"),
        "temperature": ((0, 0, 0, 1, 0), "degC", "_C"),
        "acceleration": ((1, 0, -2, 0, 0), "m/s2", "_m_s2"),
        "dimensionless": ((0, 0, 0, 0, 0), "1", "_ratio"),
    }
    assert set(QUANTITY_KINDS) == set(expected)
    for name, (dimension, canonical, suffix) in expected.items():
        kind = QUANTITY_KINDS[name]
        assert (kind.name, kind.dimension, kind.canonical_unit, kind.suffix) == (name, dimension, canonical, suffix)
        assert UNITS[canonical].dimension == dimension


def test_known_conversions() -> None:
    cases = [
        (1, "in", "mm", 25.4),
        (1, "ft", "mm", 304.8),
        (1, "lbf", "kN", 0.0044482216152605),
        (1, "kip", "kN", 4.4482216152605),
        (1, "kgf", "kN", 0.00980665),
        (1, "psi", "MPa", 0.006894757293168362),
        (1, "kip.ft", "kN.m", 1.3558179483314003),
    ]
    for value, src, dst, literal in cases:
        assert convert(value, src, dst) == literal, (src, dst)
        assert convert(value, src, dst) == _expected(value, src, dst), (src, dst)
    assert convert_exact(1, "in", "mm") == Fraction(254, 10)
    assert convert_exact(Decimal("2.5"), "m", "mm") == 2500
    assert convert_exact(Fraction(1, 3), "m", "m") == Fraction(1, 3)
    assert convert_exact(0.1, "mm", "mm") == Fraction(0.1)
    assert isinstance(convert(3, "m", "mm"), float)
    assert convert(1, "MPa", "kPa") == 1000.0
    assert convert(1, "tonf", "kN") == 9.80665
    assert convert(2, "N/mm2", "MPa") == 2.0


def test_temperature_is_affine_through_kelvin() -> None:
    assert convert_exact(0, "degC", "K") == Fraction("273.15")
    assert convert_exact(32, "degF", "degC") == 0
    assert convert_exact(212, "degF", "degC") == 100
    assert convert_exact(-40, "degC", "degF") == -40
    assert convert(100, "degC", "K") == 373.15


def test_degrees_and_radians_use_one_float_step() -> None:
    assert convert(180, "deg", "rad") == float(Fraction(180) / 180 * Fraction(math.pi))
    assert convert(math.pi, "rad", "deg") == float(Fraction(math.pi) * 180 / Fraction(math.pi))
    assert math.isclose(convert(90, "deg", "rad"), math.pi / 2, rel_tol=4 * _EPS)
    assert math.isclose(convert(1, "rad", "deg"), 180 / math.pi, rel_tol=4 * _EPS)
    assert convert(30, "deg", "deg") == 30.0
    with pytest.raises(UnitError) as info:
        convert_exact(1, "deg", "rad")
    assert "convert" in (info.value.detail.hint or "")


def test_dimension_mismatch() -> None:
    with pytest.raises(UnitError) as info:
        convert(1, "kN", "mm")
    assert info.value.detail.code is ErrorCode.UNIT_MISMATCH
    assert info.value.detail.retryable is False
    with pytest.raises(UnitError):
        convert_exact(1, "m", "m2")
    with pytest.raises(UnitError):
        convert(1, "rad", "1")  # an angle is not a ratio
    with pytest.raises(UnitError):
        convert(1, "degC", "s")


def test_unknown_symbol_and_bad_values() -> None:
    for call in (lambda: unit("furlong"), lambda: convert(1, "furlong", "mm"), lambda: convert(1, "mm", "furlong")):
        with pytest.raises(UnitError) as info:
            call()
        assert info.value.detail.code is ErrorCode.UNIT_MISMATCH
    with pytest.raises(UnitError) as info:
        unit("furlong")
    assert info.value.detail.received == "furlong"
    for bad in (math.nan, math.inf, -math.inf, Decimal("NaN"), Decimal("Infinity")):
        with pytest.raises(UnitError):
            convert_exact(bad, "mm", "m")
    with pytest.raises(UnitError):
        convert(1e308, "m", "mm")  # exact value beyond float64


def test_suffix_lookup() -> None:
    kinds = {
        "w_kN_m": "line_load",
        "Sx_mm3": "section_modulus",
        "drift_ratio": "dimensionless",
        "gamma_kN_m3": "unit_weight",
        "P_kN": "force",
        "M3_kNm": "moment",
        "b_mm": "length",
        "As_mm2": "area",
        "Ix_mm4": "second_moment",
        "fc_MPa": "stress",
        "q_allow_kPa": "area_load",
        "mass_kg": "mass",
        "rotation_deg": "angle",
        "period_s": "time",
        "t_C": "temperature",
        "a_m_s2": "acceleration",
    }
    for name, kind in kinds.items():
        found = kind_for_field(name)
        assert found is not None, name
        assert found is QUANTITY_KINDS[kind], name
    assert kind_for_field("label") is None
    assert kind_for_field("ratio") is None
    assert kind_for_field("width") is None
    assert kind_for_field("x_mm5") is None
    assert kind_for_field("kN") is None  # the suffix includes its underscore


_CSI = {
    "lb_in_F": ("lbf", "in", "degF"),
    "lb_ft_F": ("lbf", "ft", "degF"),
    "kip_in_F": ("kip", "in", "degF"),
    "kip_ft_F": ("kip", "ft", "degF"),
    "kN_mm_C": ("kN", "mm", "degC"),
    "kN_m_C": ("kN", "m", "degC"),
    "kgf_mm_C": ("kgf", "mm", "degC"),
    "kgf_m_C": ("kgf", "m", "degC"),
    "N_mm_C": ("N", "mm", "degC"),
    "N_m_C": ("N", "m", "degC"),
    "kN_cm_C": ("kN", "cm", "degC"),
    "kgf_cm_C": ("kgf", "cm", "degC"),
    "N_cm_C": ("N", "cm", "degC"),
}
_TON = ("Ton_mm_C", "Ton_m_C", "Ton_cm_C")


def test_csi_unit_systems() -> None:
    for name, (force, length, temperature) in _CSI.items():
        system = csi_unit_system(name)
        assert isinstance(system, CsiUnitSystem)
        assert (system.name, system.force, system.length, system.temperature) == (name, force, length, temperature)
        assert system.moment == f"{force}.{length}"
        assert system.stress == f"{force}/{length}2"
        assert system.line_load == f"{force}/{length}"
        assert system.unit_weight == f"{force}/{length}3"
        assert (system.area, system.section_modulus, system.second_moment) == (
            f"{length}2",
            f"{length}3",
            f"{length}4",
        )
        for kind, symbol in (
            ("force", system.force),
            ("length", system.length),
            ("temperature", system.temperature),
            ("moment", system.moment),
            ("stress", system.stress),
            ("line_load", system.line_load),
            ("unit_weight", system.unit_weight),
            ("area", system.area),
            ("section_modulus", system.section_modulus),
            ("second_moment", system.second_moment),
        ):
            assert UNITS[symbol].dimension == QUANTITY_KINDS[kind].dimension, (name, kind)
    assert len(_CSI) + len(_TON) == 16
    assert csi_unit_system("kip_in_F").stress == "kip/in2"
    assert convert(1, csi_unit_system("kN_m_C").stress, "kPa") == 1.0


def test_csi_ton_systems_are_a_gap() -> None:
    for name in _TON:
        with pytest.raises(UnitGapError) as info:
            csi_unit_system(name)
        assert isinstance(info.value, UnitError)
        assert "G-1" in (info.value.detail.hint or "")


def test_csi_unknown_name() -> None:
    for name in ("kN_m_K", "", "Ton_in_F"):
        with pytest.raises(UnitError) as info:
            csi_unit_system(name)
        assert not isinstance(info.value, UnitGapError)
