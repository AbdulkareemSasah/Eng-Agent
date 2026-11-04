"""Windows stand-in for a Sasaah server (spec 0002 section 4.3.1; test double, lead decision D-5).

Starts a child that starts a grandchild (all of them sleeping), writes one JSON line with the pid each of the three
processes reports for itself, then reads standard input until end-of-file and exits, as the synthetic fakes of spec 0002
do when the engine ends. A virtual-environment `python.exe` is a launcher whose child is the real interpreter, so no
pid of a `Popen` is trusted: every process reports its own `os.getpid()`.

With `--breakaway` the server also tries to start a process with `CREATE_BREAKAWAY_FROM_JOB` and reports whether the
job allowed it (`"denied"` for an access-denied error, else `"allowed"`).
"""

import json
import os
import subprocess
import sys

CREATE_BREAKAWAY_FROM_JOB = 0x01000000  # winbase.h, "Process Creation Flags"
ERROR_ACCESS_DENIED = 5  # winerror.h


def _breakaway() -> str:
    """Try to leave the job explicitly; return "denied" or "allowed"."""
    try:
        attempt = subprocess.Popen([sys.executable, "-c", "pass"], creationflags=CREATE_BREAKAWAY_FROM_JOB)
    except PermissionError as error:
        if getattr(error, "winerror", None) != ERROR_ACCESS_DENIED:
            raise
        return "denied"
    attempt.wait()
    return "allowed"


def main() -> None:
    """Start the child tree, announce the pids, then wait for end-of-file on standard input."""
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import os, subprocess, sys, time\n"
            "sleeper = 'import os, time; print(os.getpid(), flush=True); time.sleep(300)'\n"
            "grandchild = subprocess.Popen([sys.executable, '-c', sleeper], stdin=subprocess.DEVNULL,\n"
            "                              stdout=subprocess.PIPE, text=True)\n"
            "print(os.getpid(), grandchild.stdout.readline().strip(), flush=True)\n"
            "time.sleep(300)\n",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert child.stdout is not None
    child_pid, grandchild_pid = (int(part) for part in child.stdout.readline().split())
    announced: dict[str, int | str] = {"server": os.getpid(), "child": child_pid, "grandchild": grandchild_pid}
    if "--breakaway" in sys.argv[1:]:
        announced["breakaway"] = _breakaway()
    sys.stdout.write(json.dumps(announced) + "\n")
    sys.stdout.flush()
    sys.stdin.buffer.read()


if __name__ == "__main__":
    main()
