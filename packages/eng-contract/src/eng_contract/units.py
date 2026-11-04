"""Units of canonical/1: quantity kinds, exact conversion and CSI unit systems (spec 4.7; 04 section 4).

Purpose: the one implementation of unit conversion for the platform. Factors are exact `Fraction`s composed from cited
definitions (`_unit_table`); conversion rounds once, at the end.
Units: wire symbols are ASCII (`kN.m`, `kN/m3`, `mm2`); canonical units are in `QUANTITY_KINDS`.
Errors: `UnitError` (code `UNIT_MISMATCH`); `UnitGapError` for the CSI `Ton_*` systems (gap G-1).
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType

from pydantic import JsonValue

from eng_contract._unit_table import Dimension as Dimension  # re-exported: the public name lives here
from eng_contract._unit_table import Unit as Unit
from eng_contract._unit_table import build_units
from eng_contract.errors import ContractError, ErrorCode


class UnitError(ContractError):
    """Unknown unit symbol, conversion across dimensions or an unconvertible value; code `UNIT_MISMATCH`."""

    def __init__(
        self,
        message: str,
        *,
        received: JsonValue = None,
        expected: dict[str, JsonValue] | None = None,
        hint: str | None = None,
    ) -> None:
        """Build the error with code `UNIT_MISMATCH` (not retryable)."""
        super().__init__(ErrorCode.UNIT_MISMATCH, message, received=received, expected=expected, hint=hint)


class UnitGapError(UnitError):
    """A unit system whose meaning is an open gap (G-1: CSI `Ton_*`); never guessed."""


UNITS: Mapping[str, Unit] = MappingProxyType(build_units())
"""Every named unit by symbol (spec 4.7.3); immutable."""


@dataclass(frozen=True, slots=True)
class QuantityKind:
    """A quantity kind of canonical/1 (spec 4.7.2): its dimension, canonical unit symbol and field suffix."""

    name: str
    dimension: Dimension
    canonical_unit: str
    suffix: str


def _kind(name: str, exponents: tuple[int, ...], canonical_unit: str, suffix: str) -> QuantityKind:
    return QuantityKind(name, Dimension(*exponents), canonical_unit, suffix)


QUANTITY_KINDS: Mapping[str, QuantityKind] = MappingProxyType(
    {
        k.name: k
        for k in (
            _kind("length", (1, 0, 0, 0, 0), "mm", "_mm"),
            _kind("area", (2, 0, 0, 0, 0), "mm2", "_mm2"),
            _kind("section_modulus", (3, 0, 0, 0, 0), "mm3", "_mm3"),
            _kind("second_moment", (4, 0, 0, 0, 0), "mm4", "_mm4"),
            _kind("force", (1, 1, -2, 0, 0), "kN", "_kN"),
            _kind("moment", (2, 1, -2, 0, 0), "kN.m", "_kNm"),
            _kind("stress", (-1, 1, -2, 0, 0), "MPa", "_MPa"),
            _kind("line_load", (0, 1, -2, 0, 0), "kN/m", "_kN_m"),
            _kind("area_load", (-1, 1, -2, 0, 0), "kPa", "_kPa"),
            _kind("unit_weight", (-2, 1, -2, 0, 0), "kN/m3", "_kN_m3"),
            _kind("mass", (0, 1, 0, 0, 0), "kg", "_kg"),
            _kind("angle", (0, 0, 0, 0, 1), "deg", "_deg"),
            _kind("time", (0, 0, 1, 0, 0), "s", "_s"),
            _kind("temperature", (0, 0, 0, 1, 0), "degC", "_C"),
            _kind("acceleration", (1, 0, -2, 0, 0), "m/s2", "_m_s2"),
            _kind("dimensionless", (0, 0, 0, 0, 0), "1", "_ratio"),
        )
    }
)


def kind_for_field(name: str) -> QuantityKind | None:
    """Return the quantity kind whose suffix ends `name`, or None for a name without one.

    No suffix of the table ends another, so at most one matches (so `_kN_m3` never reads as `_kN`). `_ratio` gives
    `dimensionless`; a name such as `label` has no unit and gives None (a result, not a failure).
    """
    for kind in QUANTITY_KINDS.values():
        if name.endswith(kind.suffix):
            return kind
    return None


def unit(symbol: str) -> Unit:
    """Return the unit with this symbol.

    Raises:
        UnitError: the symbol is not in `UNITS`.
    """
    try:
        return UNITS[symbol]
    except KeyError as exc:
        raise UnitError(f"unknown unit symbol {symbol!r}", received=symbol) from exc


def _exact_value(value: int | Fraction | Decimal | float) -> Fraction:
    finite = (
        math.isfinite(value) if isinstance(value, float) else value.is_finite() if isinstance(value, Decimal) else True
    )
    if not finite:
        raise UnitError("value must be finite", received=str(value))
    return Fraction(value)


def _rational(value: int | Fraction | Decimal | float, src: str, dst: str) -> tuple[Fraction, Unit, Unit]:
    """Exact value in `dst` ignoring powers of pi, with both units; affine units go through kelvin."""
    a, b = unit(src), unit(dst)
    if a.dimension != b.dimension:
        raise UnitError(f"cannot convert {src} to {dst}: different dimensions", received=src, expected={"unit": dst})
    kelvin_or_si = _exact_value(value) * a.factor + a.offset
    return (kelvin_or_si - b.offset) / b.factor, a, b


def convert_exact(value: int | Fraction | Decimal | float, src: str, dst: str) -> Fraction:
    """Convert `value` from unit `src` to unit `dst` exactly (a float is taken as its exact binary value).

    Raises:
        UnitError: unknown symbol, different dimensions, a non-finite value, or units with different powers of pi
            (degrees and radians; use `convert`).
    """
    exact, a, b = _rational(value, src, dst)
    if a.pi_power != b.pi_power:
        raise UnitError(
            f"cannot convert {src} to {dst} exactly: the factor contains pi",
            received=src,
            expected={"unit": dst},
            hint="use convert, which applies float64 pi once",
        )
    return exact


def convert(value: float, src: str, dst: str) -> float:
    """Convert `value` from `src` to `dst` with one rounding: the correctly rounded float64 of the exact result.

    Between degrees and radians the rational part is exact and the exact product with the float64 `math.pi` is
    rounded once; that is the only float step.

    Raises:
        UnitError: as `convert_exact`, except for pi; or the result is outside the float64 range.
    """
    exact, a, b = _rational(value, src, dst)
    exact *= Fraction(math.pi) ** (a.pi_power - b.pi_power)
    try:
        return float(exact)
    except OverflowError as exc:
        raise UnitError(f"result of {src} to {dst} is outside the float64 range", received=str(value)) from exc


_CSI_NAMES = (
    "lb_in_F",
    "lb_ft_F",
    "kip_in_F",
    "kip_ft_F",
    "kN_mm_C",
    "kN_m_C",
    "kgf_mm_C",
    "kgf_m_C",
    "N_mm_C",
    "N_m_C",
    "Ton_mm_C",
    "Ton_m_C",
    "kN_cm_C",
    "kgf_cm_C",
    "N_cm_C",
    "Ton_cm_C",
)
_CSI_FORCES = {"lb": "lbf", "kip": "kip", "kN": "kN", "kgf": "kgf", "N": "N"}
_CSI_TEMPERATURES = {"F": "degF", "C": "degC"}


@dataclass(frozen=True, slots=True)
class CsiUnitSystem:
    """A CSI present-units system as unit symbols: force, length and temperature, and those derived from them.

    `moment` is force times length; `stress`, `line_load` and `unit_weight` are force per length squared, length and
    length cubed; `area`, `section_modulus` and `second_moment` are length to the power 2, 3 and 4.
    """

    name: str
    force: str
    length: str
    temperature: str
    moment: str
    stress: str
    line_load: str
    unit_weight: str
    area: str
    section_modulus: str
    second_moment: str


def csi_unit_system(name: str) -> CsiUnitSystem:
    """Return the CSI unit system named like the CSI `eUnits` value (spec 4.7.4).

    Raises:
        UnitGapError: a `Ton_*` system; the meaning of `Ton` is gap G-1 and is not guessed.
        UnitError: the name is not one of the 16 CSI names.
    """
    if name not in _CSI_NAMES:
        raise UnitError(f"unknown CSI unit system {name!r}", received=name)
    force, length, temperature = name.split("_")
    if force == "Ton":
        raise UnitGapError(
            f"CSI unit system {name!r} is not supported",
            received=name,
            hint="gap G-1: the meaning of Ton (metric tonne-force or short ton-force) is unconfirmed",
        )
    f = _CSI_FORCES[force]
    return CsiUnitSystem(
        name,
        f,
        length,
        _CSI_TEMPERATURES[temperature],
        f"{f}.{length}",
        f"{f}/{length}2",
        f"{f}/{length}",
        f"{f}/{length}3",
        f"{length}2",
        f"{length}3",
        f"{length}4",
    )
