"""Output encoding of the standard streams (spec 0006 AC5, section 4.7)."""

import io

from eng_harness.cli._encoding import configure_streams

ARABIC = "مرحبا ☃"  # the snowman has no cp1256 encoding


class _Console(io.TextIOWrapper):
    def isatty(self) -> bool:
        return True


def test_redirected_output_is_utf8() -> None:
    raw = io.BytesIO()
    pipe = io.TextIOWrapper(raw, encoding="cp1256", errors="strict", newline="")
    configure_streams(pipe)
    pipe.write(ARABIC + "\n")
    pipe.flush()
    assert raw.getvalue() == (ARABIC + "\n").encode("utf-8")


def test_console_keeps_encoding_and_escapes() -> None:
    raw = io.BytesIO()
    console = _Console(raw, encoding="cp1256", errors="strict", newline="")
    configure_streams(console)
    console.write("م ☃")
    console.flush()
    assert console.encoding == "cp1256"
    assert raw.getvalue() == "م".encode("cp1256") + b" \\u2603"


def test_streams_without_reconfigure_are_left_alone() -> None:
    text = io.StringIO()
    configure_streams(text)
    text.write(ARABIC)
    assert text.getvalue() == ARABIC
