"""Number formatting of RFC 8785 section 3.2.2.3 (spec 4.3.1 rule 4). Imports nothing from this package."""

from decimal import Decimal

_EXPONENT_LIMIT = 21  # ECMAScript Number::toString switches to exponent form above 10**21 (ECMA-262 6.1.6.1.20)
_SMALL_LIMIT = -6  # and below 10**-6


def format_float(x: float) -> str:
    """Serialize a finite float as ECMAScript `Number.prototype.toString` does; both zeros give `0`.

    The digits are Python's shortest round-trip digits (`repr`), which are the digits ECMAScript prescribes.
    The caller guarantees `x` is finite.
    """
    if x == 0:
        return "0"
    decimal = Decimal(repr(abs(x))).normalize()
    digits = "".join(map(str, decimal.as_tuple().digits))
    k, n = len(digits), decimal.adjusted() + 1  # value = 0.<digits> * 10**n
    if k <= n <= _EXPONENT_LIMIT:
        body = digits + "0" * (n - k)
    elif 0 < n <= _EXPONENT_LIMIT:
        body = f"{digits[:n]}.{digits[n:]}"
    elif _SMALL_LIMIT < n <= 0:
        body = f"0.{'0' * -n}{digits}"
    else:
        mantissa = digits[0] + (f".{digits[1:]}" if k > 1 else "")
        body = f"{mantissa}e{'+' if n > 0 else '-'}{abs(n - 1)}"
    return f"-{body}" if x < 0 else body
