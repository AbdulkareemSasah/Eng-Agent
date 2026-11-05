"""Output encoding of the standard streams (spec 0006 section 4.7, AC5)."""

import io
from typing import TextIO


def configure_streams(*streams: TextIO) -> None:
    """Make output safe for any text: redirected streams become UTF-8, a console keeps its encoding.

    Unencodable characters never raise: they print as backslash escapes. Streams that cannot be reconfigured
    (such as `io.StringIO`) are left alone.
    """
    for stream in streams:
        if not isinstance(stream, io.TextIOWrapper):
            continue
        if stream.isatty():
            stream.reconfigure(errors="backslashreplace")
        else:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
