"""Stand-in for the engine process: starts `tree.py` through the POSIX launcher and waits to be killed.

Argument 1 is the stderr file of the server. Prints the server pid, then sleeps (test double, spec 0002 AC4).
"""

import os
import sys
import time
from pathlib import Path

from eng_harness.servers._launcher import JobPolicy, LaunchSpec, PosixLauncher


def main() -> None:
    """Launch the server stand-in and hold its pipes until this process is killed."""
    tree = Path(__file__).with_name("tree.py")
    spec = LaunchSpec(
        argv=[sys.executable, str(tree)],
        env=dict(os.environ),
        cwd=Path.cwd(),
        stderr_path=Path(sys.argv[1]),
        job=JobPolicy.SERVER,
    )
    process = PosixLauncher().start(spec)
    sys.stdout.write(f"{process.pid}\n")
    sys.stdout.flush()
    time.sleep(120)


if __name__ == "__main__":
    main()
