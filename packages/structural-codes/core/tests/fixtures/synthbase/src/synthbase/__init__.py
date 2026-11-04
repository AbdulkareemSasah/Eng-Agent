"""Synthetic base pack `synthbase` for framework tests: structural fixtures only, no engineering content."""

from structural_codes.pack import Pack

from .checks import SYNTH_CHECKS

PACK = Pack(
    name="synthbase",
    code="Synthetic Code",
    edition="1",
    version="0.0.1",
    checks=SYNTH_CHECKS,
    approvals="approvals.yaml",
)
