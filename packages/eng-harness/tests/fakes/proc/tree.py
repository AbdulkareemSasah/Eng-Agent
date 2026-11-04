"""Stand-in for a Sasaah server process (spec 0002 section 4.3.1; test double, lead decision D-5).

Prints one JSON line with its own pid and, with `--children`, the pid of a sleeping child in its process group
("child") and of a sleeping host stand-in started in a new session ("host"); then reads standard input until
end-of-file and exits, as the synthetic fakes of spec section 4.3.1 do when the engine ends.
"""

import json
import os
import sys
import time


def _sleeper(new_session: bool) -> int:
    """Fork a process that closes its standard streams and sleeps; return its pid once it is set up.

    The child reports through a pipe after `setsid`, so a host stand-in has left the server's process group before its
    pid is announced; without the handshake a reader of the group could still count it as a member (B-368).
    """
    ready_read, ready_write = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(ready_read)
        if new_session:
            os.setsid()
        os.write(ready_write, b"1")
        os.close(ready_write)
        os.closerange(0, 3)
        time.sleep(120)
        os._exit(0)
    os.close(ready_write)
    os.read(ready_read, 1)
    os.close(ready_read)
    return pid


def main() -> None:
    """Start the requested stand-ins, announce the pids, then wait for end-of-file on stdin."""
    pids = {"server": os.getpid()}
    if "--children" in sys.argv[1:]:
        pids["child"] = _sleeper(new_session=False)
        pids["host"] = _sleeper(new_session=True)
    sys.stdout.write(json.dumps(pids) + "\n")
    sys.stdout.flush()
    sys.stdin.buffer.read()


if __name__ == "__main__":
    main()
