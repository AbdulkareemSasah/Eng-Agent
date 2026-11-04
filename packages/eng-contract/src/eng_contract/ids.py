"""Identifiers, clocks and id sources (spec 4.2.1, 4.3.2): `res_`/`mdl_` ULIDs and RFC 3339 UTC timestamps.

Units: milliseconds since the Unix epoch (UTC). Errors: `IdOverflowError` (`LIMIT_EXCEEDED`); malformed ids raise
`ContractError` (`INVALID_ARGUMENT`).
"""

import hashlib
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Protocol

from pydantic import AfterValidator, StringConstraints

from eng_contract import _ulid
from eng_contract.errors import ContractError, ErrorCode

_BODY = r"[0-7][0-9A-HJKMNP-TV-Z]{25}"
ResultId = Annotated[str, StringConstraints(pattern=rf"^res_{_BODY}$")]
ModelId = Annotated[str, StringConstraints(pattern=rf"^mdl_{_BODY}$")]

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _valid_date(text: str) -> str:
    try:
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as exc:
        raise ValueError("not a valid date and time") from exc
    return text


Timestamp = Annotated[
    str,
    StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"),
    AfterValidator(_valid_date),
]
"""RFC 3339 UTC with exactly three fraction digits and `Z`, and a valid date."""


def _format(ms: int) -> str:
    try:
        moment = _EPOCH + timedelta(milliseconds=ms)
    except OverflowError as exc:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "time outside the year 1 to 9999", received=ms) from exc
    return f"{moment:%Y-%m-%dT%H:%M:%S}.{moment.microsecond // 1000:03d}Z"


class Clock(Protocol):
    """Source of time; tests inject `FixedClock`."""

    def now_ms(self) -> int:
        """Unix time in milliseconds, UTC."""
        ...

    def now(self) -> Timestamp:
        """The same instant as a `Timestamp`."""
        ...


class SystemClock:
    """The wall clock (`time.time_ns()`)."""

    def now_ms(self) -> int:
        """Unix time in milliseconds, UTC."""
        return time.time_ns() // 1_000_000

    def now(self) -> Timestamp:
        """The current instant as a `Timestamp`."""
        return _format(self.now_ms())


class FixedClock:
    """Deterministic clock: the i-th call (from 0) of `now_ms` or `now` returns `start_ms + i * step_ms`."""

    def __init__(self, start_ms: int, step_ms: int = 0) -> None:
        """Set the first value and the step, both in milliseconds."""
        self._next, self._step = start_ms, step_ms

    def now_ms(self) -> int:
        """Return the next value in milliseconds."""
        value, self._next = self._next, self._next + self._step
        return value

    def now(self) -> Timestamp:
        """Return the next value as a `Timestamp` (`INVALID_ARGUMENT` outside years 1 to 9999)."""
        return _format(self.now_ms())


class IdSource(Protocol):
    """Source of ULIDs."""

    def new_ulid(self) -> str:
        """A new 26-character ULID."""
        ...


class IdOverflowError(ContractError):
    """The 80-bit random part overflows within one millisecond; the code is fixed to `LIMIT_EXCEEDED`."""

    def __init__(self) -> None:
        """Build the error with code `LIMIT_EXCEEDED` (not retryable)."""
        super().__init__(ErrorCode.LIMIT_EXCEEDED, "ULID random part overflow within one millisecond")


class _MonotonicSource:
    """ULID monotonic rule (ulid/spec): a clock value not after the previous one reuses its time and adds one."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._last: tuple[int, int] | None = None

    def _fresh_random(self) -> int:
        raise NotImplementedError

    def new_ulid(self) -> str:
        """Return the next ULID, greater than every earlier one of this instance.

        Raises:
            IdOverflowError: the random part would exceed 80 bits.
            ContractError: `INVALID_ARGUMENT` when the clock is outside 0 to 2**48 - 1 ms.
        """
        now, random_part = self._clock.now_ms(), self._fresh_random()
        if self._last is not None and now <= self._last[0]:
            now, random_part = self._last[0], self._last[1] + 1
            if random_part >> _ulid.RANDOM_BITS:
                raise IdOverflowError
        text = _ulid.encode(now, random_part)
        self._last = (now, random_part)
        return text


class SystemIdSource(_MonotonicSource):
    """Production id source; per-instance state only."""

    def __init__(self, clock: Clock, random_bytes: Callable[[int], bytes] = os.urandom) -> None:
        """Use `clock` for time and `random_bytes(n)` for the random part."""
        super().__init__(clock)
        self._random_bytes = random_bytes

    def _fresh_random(self) -> int:
        return int.from_bytes(self._random_bytes(10), "big")


class SeededIdSource(_MonotonicSource):
    """Deterministic id source for tests and replay: random part i is `sha256(seed + i)[:10]`, i counting from 0."""

    def __init__(self, seed: bytes, clock: Clock) -> None:
        """Set the seed and the clock."""
        super().__init__(clock)
        self._seed, self._count = seed, 0

    def _fresh_random(self) -> int:
        digest = hashlib.sha256(self._seed + self._count.to_bytes(8, "big")).digest()
        self._count += 1
        return int.from_bytes(digest[:10], "big")


def new_result_id(ids: IdSource) -> str:
    """A new `res_` id from `ids`."""
    return f"res_{ids.new_ulid()}"


def new_model_id(ids: IdSource) -> str:
    """A new `mdl_` id from `ids`."""
    return f"mdl_{ids.new_ulid()}"


def ulid_timestamp_ms(ulid: str) -> int:
    """Unix time in milliseconds encoded in a ULID, with or without its `res_`/`mdl_` prefix.

    Raises:
        ContractError: `INVALID_ARGUMENT` when `ulid` is malformed.
    """
    return _ulid.decode_time_ms(ulid)
