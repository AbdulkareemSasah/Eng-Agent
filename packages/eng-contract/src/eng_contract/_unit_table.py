"""Base definitions and exact composition of the units of canonical/1 (spec 4.7.3).

Purpose: the only place where unit factors are typed. Every typed value is an exact definition with its source in the
comment beside it; every other factor is a product of these, computed with `Fraction` at import. The table and section
numbers of the sources are unconfirmed (gap G-4, docs/verification/units.md).
Units: factors are exact to the coherent SI unit of the dimension (m, kg, s, rad; kelvin).
Errors: none; the table is built from constants.
"""

from dataclasses import dataclass, replace
from fractions import Fraction
from typing import NamedTuple


class Dimension(NamedTuple):
    """Integer exponents over length, mass, time, temperature and plane angle (spec 4.7.1)."""

    length: int = 0
    mass: int = 0
    time: int = 0
    temperature: int = 0
    angle: int = 0


@dataclass(frozen=True, slots=True)
class Unit:
    """A unit: `value_in_coherent_SI = value * factor * pi**pi_power + offset` (offset: temperature only)."""

    symbol: str
    dimension: Dimension
    factor: Fraction
    pi_power: int = 0
    offset: Fraction = Fraction(0)


def _mul(a: Unit, b: Unit) -> Unit:
    dim = Dimension(*(x + y for x, y in zip(a.dimension, b.dimension, strict=True)))
    return Unit("", dim, a.factor * b.factor, a.pi_power + b.pi_power)


def _pow(a: Unit, n: int) -> Unit:
    return Unit("", Dimension(*(x * n for x in a.dimension)), a.factor**n, a.pi_power * n)


def _div(a: Unit, b: Unit) -> Unit:
    return _mul(a, _pow(b, -1))


def _scale(a: Unit, factor: Fraction | int) -> Unit:
    return replace(a, factor=a.factor * factor)


_METRE = Unit("m", Dimension(length=1), Fraction(1))  # SI Brochure 9th ed., Table 2
_KG = Unit("kg", Dimension(mass=1), Fraction(1))  # SI Brochure 9th ed., Table 2
_SECOND = Unit("s", Dimension(time=1), Fraction(1))  # SI Brochure 9th ed., Table 2
_KELVIN = Unit("K", Dimension(temperature=1), Fraction(1))  # SI Brochure 9th ed., Table 2
_RADIAN = Unit("rad", Dimension(angle=1), Fraction(1))  # SI Brochure 9th ed., Table 4
_ACCEL = _div(_METRE, _pow(_SECOND, 2))
_NEWTON = _mul(_KG, _ACCEL)  # N = kg m/s2, SI Brochure 9th ed., Table 4
_PASCAL = _div(_NEWTON, _pow(_METRE, 2))  # Pa = N/m2, SI Brochure 9th ed., Table 4
_PREFIX = {"m": Fraction(1, 1000), "c": Fraction(1, 100), "k": Fraction(1000), "M": Fraction(10**6)}
_GIGA = Fraction(10**9)  # SI prefix G, SI Brochure 9th ed., Table 7 (not in the spec's prefix row; used by GPa)
_TONNE = _scale(_KG, 1000)  # 1 t = 1000 kg, SI Brochure 9th ed., Table 8
_INCH = _scale(_METRE, Fraction("0.0254"))  # exact, NIST SP 811 (2008), Appendix B.8
_FOOT = _scale(_METRE, Fraction("0.3048"))  # exact, NIST SP 811 (2008), Appendix B.8
_POUND = _scale(_KG, Fraction("0.45359237"))  # exact, NIST SP 811 (2008), Appendix B.8
_G_N = _scale(_ACCEL, Fraction("9.80665"))  # standard gravity, 3rd CGPM (1901); NIST SP 811 (2008), App. B.8
_DEGREE = Unit("deg", Dimension(angle=1), Fraction(1, 180), 1)  # pi/180 rad, SI Brochure 9th ed., Table 8
_CELSIUS_OFFSET = Fraction("273.15")  # T/K = t/degC + 273.15, SI Brochure 9th ed., 2.3.1; NIST SP 811 4.2.1.1
_FAHRENHEIT = Fraction(5, 9)  # t/degC = (t/degF - 32)/1.8, NIST SP 811 (2008), Appendix B.8

_LENGTHS = {
    "mm": _scale(_METRE, _PREFIX["m"]),
    "cm": _scale(_METRE, _PREFIX["c"]),
    "m": _METRE,
    "in": _INCH,
    "ft": _FOOT,
}
_LBF = _mul(_POUND, _G_N)  # pound-force = 1 lb x g_n
_FORCES = {
    "N": _NEWTON,
    "kN": _scale(_NEWTON, _PREFIX["k"]),
    "MN": _scale(_NEWTON, _PREFIX["M"]),
    "kgf": _mul(_KG, _G_N),
    "tonf": _mul(_TONNE, _G_N),  # metric tonne-force; its use for CSI `Ton` is gap G-1
    "lbf": _LBF,
    "kip": _scale(_LBF, 1000),
}
_ALIASES = {"psi": "lbf/in2", "ksi": "kip/in2", "psf": "lbf/ft2", "ksf": "kip/ft2", "pcf": "lbf/ft3"}


def build_units() -> dict[str, Unit]:
    """Return every named unit of canonical/1 by symbol, composed exactly from the base definitions above."""
    units: dict[str, Unit] = {}
    for name, length in _LENGTHS.items():
        units[name] = length
        units.update({f"{name}{n}": _pow(length, n) for n in (2, 3, 4)})
        units[f"{name}/s2"] = _div(length, _pow(_SECOND, 2))
    for fname, force in _FORCES.items():
        units[fname] = force
        for lname, length in _LENGTHS.items():
            units[f"{fname}.{lname}"] = _mul(force, length)
            units[f"{fname}/{lname}"] = _div(force, length)
            units[f"{fname}/{lname}2"] = _div(force, _pow(length, 2))
            units[f"{fname}/{lname}3"] = _div(force, _pow(length, 3))
    units.update({"Pa": _PASCAL, "kPa": _scale(_PASCAL, _PREFIX["k"]), "MPa": _scale(_PASCAL, _PREFIX["M"])})
    units["GPa"] = _scale(_PASCAL, _GIGA)
    units.update({alias: units[target] for alias, target in _ALIASES.items()})
    units.update({"kg": _KG, "t": _TONNE, "lb": _POUND, "s": _SECOND, "min": _scale(_SECOND, 60)})
    units.update({"h": _scale(_SECOND, 3600), "rad": _RADIAN, "deg": _DEGREE})
    units.update({"K": _KELVIN, "1": Unit("1", Dimension(), Fraction(1))})
    units["degC"] = replace(_KELVIN, offset=_CELSIUS_OFFSET)
    units["degF"] = replace(_KELVIN, factor=_FAHRENHEIT, offset=_CELSIUS_OFFSET - 32 * _FAHRENHEIT)
    return {symbol: replace(unit, symbol=symbol) for symbol, unit in units.items()}
