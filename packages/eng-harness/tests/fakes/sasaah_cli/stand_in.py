"""The behaviour of the three stand-in tools; `control.json` next to the scripts arms a fault (test code).

Faults: `sleep` (seconds, to run past the timeout), `exit` (a failing exit code), `touch_artifact` (a path whose
content is changed while the tool runs). Outputs are JSON files that echo what the tool received, so a test can tell
what reached it.
"""

import json
import sys
import time
from pathlib import Path
from typing import Any

OUTPUTS = {"prepare": "prepared.json", "inspect": "inspection.json", "build": "model.json"}


def _named(argv: list[str]) -> dict[str, str]:
    pairs = zip(argv[::2], argv[1::2], strict=True)
    return {name.lstrip("-"): value for name, value in pairs}


def main(kind: str) -> None:
    """Run the stand-in of `kind`: apply the armed fault, then write the output file into `OutDir`."""
    control = Path(__file__).with_name("control.json")
    fault: dict[str, Any] = json.loads(control.read_text()) if control.exists() else {}
    args = _named(sys.argv[1:])
    if "touch_artifact" in fault:
        with Path(fault["touch_artifact"]).open("ab") as artifact:
            artifact.write(b"rebuilt")
    time.sleep(fault.get("sleep", 0))
    if "exit" in fault:
        print("stand-in failure", file=sys.stderr)
        sys.exit(fault["exit"])
    out = Path(args.get("OutDir", args.get("Config", ".")))
    echo: dict[str, Any] = {"args": args}
    if kind == "build":
        config = json.loads(Path(args["Config"]).read_text())
        echo["config"] = config
        out = Path(config["outputFolder"])
    (out / OUTPUTS[kind]).write_text(json.dumps(echo, sort_keys=True))
    print(f"{kind} done")
