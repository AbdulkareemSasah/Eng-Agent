"""Text, date and number formatting and sanitizing (spec 0006 section 4.7, AC21, AC58).

This is the only module that formats. It never imports `locale` and never calls `strftime`: output is the same
whatever the culture or calendar (ASCII digits, a point as decimal separator, Gregorian dates in UTC).
"""

import re
import unicodedata

_TIMESTAMP = re.compile(r"^([0-9]{4}-[0-9]{2}-[0-9]{2})T([0-9]{2}:[0-9]{2}:[0-9]{2})\.[0-9]{3}Z$", re.ASCII)
_BIDI_CONTROLS = frozenset(
    chr(code) for code in (0x061C, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A))
)
_LINE_SEPARATORS = frozenset((chr(0x2028), chr(0x2029)))


def format_duration_ms(milliseconds: int) -> str:
    """Format a duration given in milliseconds, by integer arithmetic.

    Under one second the form is `850 ms`; otherwise whole seconds (the fraction is dropped) as `7 s`,
    `2 min 05 s` or `1 h 02 min 03 s`.

    Raises:
        ValueError: the duration is negative.
    """
    if milliseconds < 0:
        raise ValueError("duration is negative")
    if milliseconds < 1000:
        return f"{milliseconds} ms"
    seconds = milliseconds // 1000
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} h {minutes:02d} min {seconds:02d} s"
    if minutes:
        return f"{minutes} min {seconds:02d} s"
    return f"{seconds} s"


def format_timestamp(timestamp: str) -> str:
    """Slice a contract `Timestamp` (RFC 3339 UTC) into `YYYY-MM-DD HH:MM:SS UTC`.

    Raises:
        ValueError: the text is not a contract timestamp.
    """
    match = _TIMESTAMP.match(timestamp)
    if match is None:
        raise ValueError("not a contract timestamp")
    return f"{match.group(1)} {match.group(2)} UTC"


def format_number(value: float, significant: int = 6) -> str:
    """Format a number with `significant` significant digits, ASCII digits and a point as decimal separator.

    Raises:
        ValueError: `significant` is below 1.
    """
    if significant < 1:
        raise ValueError("significant digits must be at least 1")
    return format(value, f".{significant}g")


def _mark(char: str) -> str:
    return f"<U+{ord(char):04X}>"


def _is_unsafe(char: str) -> bool:
    return unicodedata.category(char) == "Cc" or char in _BIDI_CONTROLS or char in _LINE_SEPARATORS


def sanitize_terminal(text: str) -> str:
    """Replace every control, line-separator and bidirectional control character by `<U+XXXX>`.

    The escape character is replaced too, so no escape sequence can act on a terminal.
    """
    return "".join(_mark(c) if _is_unsafe(c) else c for c in text)


def sanitize_html(text: str) -> str:
    """Like `sanitize_terminal` but keeps tab and line feed; escaping for markup is done by the HTML builder."""
    return "".join(_mark(c) if _is_unsafe(c) and c not in "\t\n" else c for c in text)


def truncate(text: str, limit: int) -> str:
    """Shorten `text` to at most `limit` characters, ending with `...` when cut.

    Raises:
        ValueError: `limit` is below 3.
    """
    if limit < 3:
        raise ValueError("limit must be at least 3")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
