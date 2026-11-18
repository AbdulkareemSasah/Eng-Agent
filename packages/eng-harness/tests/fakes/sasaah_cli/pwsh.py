"""Stand-in for the shell and the three scripts (spec 0002 4.8.3; test code, never packaged).

`pwsh -NoProfile -NonInteractive -File <script> -Name value ...` behaves as the tool the script's name says
(`run_prepare.py`, `run_inspect.py`, `run_build.py`; the files are markers). `control.json` next to the scripts arms a
fault: `sleep` (seconds, to run past the timeout), `exit` (a failing exit code), `touch_artifact` (a path whose content
is changed while the tool runs). Outputs are JSON files that echo what the tool received.
"""

import json
import sys
import time
from pathlib import Path
from typing import Any

OUTPUTS = {"prepare": "prepared.json", "inspect": "inspection.json", "build": "model.json"}


def main(argv: list[str]) -> None:
    """Skip the shell switches, apply the armed fault, then write the output file of the tool `-File` names."""
    rest = [a for a in argv if a not in ("-NoProfile", "-NonInteractive")]
    if rest[:1] != ["-File"]:
        sys.exit(64)
    script = Path(rest[1])
    kind = script.stem.removeprefix("run_")
    args = {name.lstrip("-"): value for name, value in zip(rest[2::2], rest[3::2], strict=True)}
    control = script.with_name("control.json")
    fault: dict[str, Any] = json.loads(control.read_text()) if control.exists() else {}
    if "touch_artifact" in fault:
        with Path(fault["touch_artifact"]).open("ab") as artifact:
            artifact.write(b"rebuilt")
    time.sleep(fault.get("sleep", 0))
    if "exit" in fault:
        sys.stderr.write("stand-in failure\n")
        sys.exit(fault["exit"])
    out = Path(args["OutDir"])
    echo: dict[str, Any] = {"args": args}
    if kind == "build":
        echo["config"] = json.loads(Path(args["Config"]).read_text())
    (out / OUTPUTS[kind]).write_text(json.dumps(echo, sort_keys=True))
    sys.stdout.write(f"{kind} done\n")


if __name__ == "__main__":
    main(sys.argv[1:])
