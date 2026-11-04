"""Quantity: a number with a unit symbol, compared physically and never used in arithmetic (spec 4.8).

Purpose: carry measured values across the contract so that a threshold or a unit mistake cannot pass silently.
Units: any symbol in `units.UNITS`; the wire form is `{"value": 450.0, "unit": "mm"}`.
Errors: `UnitError` (`UNIT_MISMATCH`) for an unknown symbol, a conversion across dimensions or an unknown kind;
`TypeError` for arithmetic, number conversion, truth tests and ordering against anything but a `Quantity` of the same
dimension.
"""

import math
from fractions import Fraction
from typing import Annotated, NoReturn, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from eng_contract.units import QUANTITY_KINDS, UNITS, Dimension, UnitError, convert


def _refuse(self: object, *args: object, **kwargs: object) -> NoReturn:
    raise TypeError(f"{type(self).__name__} supports no arithmetic or number conversion; read .value explicitly")


def check_unit_symbol(symbol: str) -> str:
    """Return `symbol` if it is in `UNITS`.

    Raises:
        UnitError: the symbol is unknown.
    """
    if symbol not in UNITS:
        raise UnitError(f"unknown unit symbol {symbol!r}", received=symbol)
    return symbol


class Quantity(BaseModel):
    """A finite value in a unit; frozen, hashable, with physical equality and same-dimension ordering.

    Equality and ordering compare exact fractions of the coherent SI value (spec 4.8 rule 4). A float enters the
    fraction as its shortest round-trip decimal (the number as written, so 25.4 mm equals 1 in); the spec text says
    `Fraction(value)`, which would make AC35 false (owner queue). Between units with different powers of pi (`deg`
    against `rad`) the single float64 step `sifloat` is compared instead; equality across powers of pi is therefore
    not transitive at the last bit, and canonical stored data never mixes them. `sifloat` saturates to infinity
    beyond the float64 range, which only coarsens the hash and the cross-pi comparison there.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: Annotated[float, Field(strict=True, allow_inf_nan=False)]
    unit: str

    def __init__(self, value: float, unit: str, **extra: JsonValue) -> None:
        """Build from a value and a unit symbol (keywords `value` and `unit` also work)."""
        super().__init__(value=value, unit=unit, **extra)

    _unit_known = field_validator("unit")(check_unit_symbol)

    __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = _refuse
    __truediv__ = __rtruediv__ = __floordiv__ = __mod__ = __pow__ = _refuse
    __neg__ = __pos__ = __abs__ = __round__ = _refuse
    __float__ = __int__ = __index__ = __bool__ = _refuse

    def _key(self) -> tuple[Dimension, Fraction, int]:
        u = UNITS[self.unit]
        return u.dimension, Fraction(repr(self.value)) * u.factor + u.offset, u.pi_power

    def _sifloat(self) -> float:
        _, r, p = self._key()
        try:
            return float(r) * math.pi**p
        except OverflowError:
            return math.inf if r > 0 else -math.inf

    def _compare(self, other: object) -> int:
        if not isinstance(other, Quantity):
            raise TypeError(f"cannot order a Quantity against {type(other).__name__}")
        (da, ra, pa), (db, rb, pb) = self._key(), other._key()
        if da != db:
            raise TypeError(f"cannot order quantities of different dimensions ({self.unit} and {other.unit})")
        if pa != pb:
            ra, rb = Fraction(self._sifloat()), Fraction(other._sifloat())
        return (ra > rb) - (ra < rb)

    def __eq__(self, other: object) -> bool:
        """Physical equality; another dimension is unequal, a non-Quantity gives NotImplemented."""
        if not isinstance(other, Quantity):
            return NotImplemented
        if UNITS[self.unit].dimension != UNITS[other.unit].dimension:
            return False
        return self._compare(other) == 0

    def __hash__(self) -> int:
        """Hash of (dimension, sifloat); equal quantities hash equal (spec 4.8 rule 5)."""
        return hash((UNITS[self.unit].dimension, self._sifloat()))

    def __lt__(self, other: object) -> bool:
        """Order against a Quantity of the same dimension, else TypeError."""
        return self._compare(other) < 0

    def __le__(self, other: object) -> bool:
        """Order against a Quantity of the same dimension, else TypeError."""
        return self._compare(other) <= 0

    def __gt__(self, other: object) -> bool:
        """Order against a Quantity of the same dimension, else TypeError."""
        return self._compare(other) > 0

    def __ge__(self, other: object) -> bool:
        """Order against a Quantity of the same dimension, else TypeError."""
        return self._compare(other) >= 0

    def to(self, symbol: str) -> Quantity:
        """Return this quantity in unit `symbol` (one rounding, `units.convert`).

        Raises:
            UnitError: unknown symbol or different dimension.
        """
        return Quantity(convert(self.value, self.unit, symbol), symbol)

    def canonical(self, kind: str) -> Quantity:
        """Return this quantity in the canonical unit of quantity kind `kind`.

        Raises:
            UnitError: unknown kind or a different dimension.
        """
        if kind not in QUANTITY_KINDS:
            raise UnitError(f"unknown quantity kind {kind!r}", received=kind)
        return self.to(QUANTITY_KINDS[kind].canonical_unit)


class LabeledQuantity(Quantity):
    """A Quantity with extra members (strings, integers, booleans) such as `member` or `combo`; not compared."""

    model_config = ConfigDict(frozen=True, extra="allow")

    @model_validator(mode="after")
    def _labels_are_plain(self) -> Self:
        for name, label in (self.model_extra or {}).items():
            if not isinstance(label, str | int):
                raise ValueError(f"label {name!r} must be a string, integer or boolean")
        return self


__all__ = ["LabeledQuantity", "Quantity", "check_unit_symbol"]
