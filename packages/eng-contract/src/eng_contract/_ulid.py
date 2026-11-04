"""ULID text form (ulid/spec, github.com/ulid/spec; spec 4.3.2): Crockford base32, 48-bit time and 80-bit random part.

Units: time in Unix milliseconds (UTC). Errors: `ContractError` with `INVALID_ARGUMENT` for malformed input.
"""

import re

from eng_contract.errors import ContractError, ErrorCode

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
TIME_BITS = 48
RANDOM_BITS = 80
_ULID = re.compile(r"^(?:(?:res|mdl)_)?([0-7][0-9A-HJKMNP-TV-Z]{25})$")


def encode(time_ms: int, random_part: int) -> str:
    """Return the 26-character ULID for `time_ms` (0 to 2**48 - 1) and `random_part` (0 to 2**80 - 1).

    Raises:
        ContractError: `INVALID_ARGUMENT` when either part is out of range.
    """
    if not 0 <= time_ms < 1 << TIME_BITS or not 0 <= random_part < 1 << RANDOM_BITS:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "ULID time or random part out of range")
    value = (time_ms << RANDOM_BITS) | random_part
    return "".join(ALPHABET[(value >> shift) & 31] for shift in range(125, -1, -5))


def decode_time_ms(text: str) -> int:
    """Return the Unix time in milliseconds of a ULID, optionally prefixed `res_` or `mdl_`.

    Raises:
        ContractError: `INVALID_ARGUMENT` when `text` is not a ULID (upper case only, first character 0 to 7).
    """
    match = _ULID.match(text)
    if match is None:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "not a ULID", received=text[:64])
    value = 0
    for char in match.group(1):
        value = (value << 5) | ALPHABET.index(char)
    return value >> RANDOM_BITS
