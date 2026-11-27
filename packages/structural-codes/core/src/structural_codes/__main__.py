"""Entry point of `python -m structural_codes` (spec 0001, section 4.9.3)."""

import sys

from structural_codes._cli import main

sys.exit(main(sys.argv[1:], sys.stdout, sys.stderr))
