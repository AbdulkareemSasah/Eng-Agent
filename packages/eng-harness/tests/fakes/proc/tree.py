"""Stand-in for a Sasaah server process (spec 0002 section 4.3.1; test double, lead decision D-5).

Prints one JSON line with its own pid and, with `--children`, the pid of a sleeping child in its process group
("child") and of a sleeping host stand-in started in a new session ("host"); then reads standard input until
end-of-file and exits, as the synthetic fakes of spec section 4.3.1 do when the engine ends.
"""

import json
import os
import subprocess
import sys

_SLEEP = [sys.executable, "-c", "import time; time.sleep(120)"]


def main() -> None:
    """Start the requested stand-ins, announce the pids, then wait for end-of-file on stdin."""
    pids = {"server": os.getpid()}
    if "--children" in sys.argv[1:]:
        pids["child"] = subprocess.Popen(_SLEEP, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL).pid
        pids["host"] = subprocess.Popen(
            _SLEEP, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, start_new_session=True
        ).pid
    sys.stdout.write(json.dumps(pids) + "\n")
    sys.stdout.flush()
    sys.stdin.buffer.read()


if __name__ == "__main__":
    main()
