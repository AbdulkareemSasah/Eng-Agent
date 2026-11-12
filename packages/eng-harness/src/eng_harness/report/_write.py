"""Atomic UTF-8 report file write (spec 0006 section 4.7, AC59)."""

import os
from pathlib import Path


def write_report(html: str, path: Path) -> None:
    """Write `html` to `path` as UTF-8 with LF newlines, by temporary file and rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(html, encoding="utf-8", newline="\n")
    os.replace(temporary, path)
