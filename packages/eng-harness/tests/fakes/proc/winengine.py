"""Stand-in for the engine process on Windows: starts `wintree.py` through the Windows launcher (spec 0002 AC5).

Arguments: the job policy (`server` or `tool`) and the stderr file of the server. Writes one JSON line with the pid the
engine reports for itself, the pids the server stand-in reports, and the pids of the server job's members, then reads
standard input until end-of-file and exits. A test ends it by closing its standard input or by killing it, and then
checks what happened to the server and its descendants (test double, spec 0002 AC5).
"""

import json
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    from eng_harness.servers._launcher import JobPolicy, LaunchSpec
    from eng_harness.servers._launcher_windows import windows_launcher

    def main() -> None:
        """Start the server stand-in in its own job, announce the pids, then wait for end-of-file on stdin."""
        policy, stderr_path = JobPolicy(sys.argv[1]), Path(sys.argv[2])
        spec = LaunchSpec(
            argv=[str(Path(sys.base_prefix) / "python.exe"), str(Path(__file__).with_name("wintree.py"))],
            env=dict(os.environ),
            cwd=Path.cwd(),
            stderr_path=stderr_path,
            job=policy,
        )
        server = windows_launcher().start(spec)
        announced = json.loads(server.stdout.readline())
        announced["engine"] = os.getpid()
        announced["members"] = [member.pid for member in server.job_members()]
        sys.stdout.write(json.dumps(announced) + "\n")
        sys.stdout.flush()
        sys.stdin.buffer.read()

    if __name__ == "__main__":
        main()
