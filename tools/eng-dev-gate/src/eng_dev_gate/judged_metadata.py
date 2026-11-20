"""Metadata of the installed distributions, read inside the environment of the judged tree (spec 4.12, B-086).

In pull-request context the ``licenses`` step runs ``uv run --project <judged tree> ... python -I judged_metadata.py
<output file>``: this file is run as a script by the interpreter of the judged environment, so it imports nothing of the
gate (a unit test checks it) and prints nothing; it writes the fields the license policy needs, the interpreter and the
module map to the output file. The policies are evaluated by the gate, never here. A head run calls ``collect``.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from importlib.metadata import distributions, packages_distributions
from pathlib import Path

__all__ = ["collect", "main", "module_map"]


def collect(path: Sequence[str] | None = None) -> list[dict[str, object]]:
    """Return name, license fields, classifiers and requirements of each distribution on ``path`` (default: sys.path).

    A distribution without a name is skipped: it cannot be a requirement of anything.
    """
    found: list[dict[str, object]] = []
    for dist in distributions(path=list(path)) if path else distributions():
        meta = dist.metadata
        if not meta.get("Name"):
            continue
        found.append(
            {
                "name": meta.get("Name"),
                "expression": meta.get("License-Expression") or "",
                "license": meta.get("License") or "",
                "classifiers": [c for c in meta.get_all("Classifier") or [] if c.startswith("License ::")],
                "requires": list(dist.requires or []),
            }
        )
    return found


def module_map() -> dict[str, list[str]]:
    """Return ``packages_distributions()`` without nameless distributions (module name to distribution names)."""
    return {top: [name for name in names if name] for top, names in packages_distributions().items()}


def main(argv: Sequence[str]) -> int:
    """Write ``executable``, ``distributions`` (``collect()``) and ``packages`` (``module_map()``) to ``argv[0]``."""
    report = {"executable": sys.executable, "distributions": collect(), "packages": module_map()}
    Path(argv[0]).write_text(json.dumps(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
