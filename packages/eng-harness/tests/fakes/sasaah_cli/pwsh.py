"""Stand-in for the shell: `pwsh -NoProfile -NonInteractive -File <script> -Name value ...` runs the script in Python."""

import runpy
import sys
from pathlib import Path


def main(argv: list[str]) -> None:
    """Skip the shell switches, then run the script named by `-File` with the named arguments left in `sys.argv`."""
    rest = [a for a in argv if a not in ("-NoProfile", "-NonInteractive")]
    if rest[:1] != ["-File"]:
        sys.exit(64)
    script = Path(rest[1])
    sys.path.insert(0, str(script.parent))
    sys.argv = [str(script), *rest[2:]]
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main(sys.argv[1:])
