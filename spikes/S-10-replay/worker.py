"""S-10 spike: one engine process. Throwaway.

A crash is simulated inside the process with os._exit (nothing is flushed or closed, the state a SIGKILL leaves), or
by the parent killing the process (check.py, external kill).

Exit codes: 0 completed, 10 paused, 11 needs reconciliation, 12 replay divergence, 13 failed, 86 crashed on purpose.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from engine import Engine
from scenarios import BLOCKS, FOOTING_INPUT, VERSION, FakeHost

EXIT = {"COMPLETED": 0, "PAUSED": 10, "NEEDS_RECONCILIATION": 11, "REPLAY_DIVERGENCE": 12, "FAILED": 13}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--block", default="footing")
    ap.add_argument("--name", default="", help="logical block name recorded in the journal (default: --block)")
    ap.add_argument("--version", default=VERSION)
    ap.add_argument("--policy", default="mixed")
    ap.add_argument("--crash", default="", help="PATH@POINT, for example 3/0@after_effect")
    ap.add_argument("--no-reconciler", action="store_true")
    ap.add_argument("--input", default=json.dumps(FOOTING_INPUT))
    a = ap.parse_args()

    crash_path, _, crash_point = a.crash.partition("@")

    def faults(point: str, path: str) -> None:
        if a.crash and point == crash_point and path == crash_path:
            os._exit(86)

    run_dir = Path(a.run_dir)
    host = FakeHost(run_dir / "host")
    eng = Engine(run_dir, "run-001", host.tools(reconciler=not a.no_reconciler), a.policy, faults if a.crash else None)
    out = asyncio.run(eng.run(BLOCKS[a.block], json.loads(a.input), a.name or a.block, a.version))
    print(
        json.dumps(
            {
                "status": out.status,
                "result": out.result,
                "detail": out.detail,
                "pending": out.pending,
                "replayed": out.replayed,
                "live": out.live,
            }
        )
    )
    return EXIT[out.status]


if __name__ == "__main__":
    sys.exit(main())
