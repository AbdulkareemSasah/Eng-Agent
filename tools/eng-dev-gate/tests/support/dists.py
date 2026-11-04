"""Fixture: fake installed distributions (``*.dist-info/METADATA``) in a temporary folder used as the search path."""

from __future__ import annotations

from pathlib import Path


def add_dist(site: Path, name: str, *headers: str) -> None:
    """Write ``<name>-1.0.dist-info/METADATA`` with the given extra header lines (``Key: value``)."""
    folder = site / f"{name.replace('-', '_')}-1.0.dist-info"
    folder.mkdir(parents=True)
    lines = ["Metadata-Version: 2.4", f"Name: {name}", "Version: 1.0", *headers]
    (folder / "METADATA").write_text("\n".join(lines) + "\n", encoding="utf-8")
