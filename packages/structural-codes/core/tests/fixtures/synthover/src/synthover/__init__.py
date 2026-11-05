"""Synthetic overlay pack `synthover` over `synthbase.RUNNER_PACK`: structural fixtures, no engineering content."""

from structural_codes.overlay import Added, Inherited, Overlay, Overridden, Removed
from structural_codes.pack import Pack

from .checks import CODE, OWN_CHECKS, extra, sized_over

CLAUSE_MAP = {"S3.1": "3.1", "S4.1": "4.1", "S5.2": "5.2", "S6.1": "6.1", "A1.1": None}
ENTRIES = (
    Overridden("synthbase.3_1.sized", sized_over),
    Inherited("synthbase.4_1.two_pre", clause="S4.1"),
    Inherited("synthbase.5_2.scoped_free", clause="S5.2"),
    Inherited("synthbase.6_1.gap", clause="S6.1"),
    Removed("synthbase.5_1.scoped", reason="synthetic removal reason scoped"),
    Removed("synthbase.6_2.gap_undeclared", reason="synthetic removal reason undeclared"),
    Removed("synthbase.6_3.gap_pre", reason="synthetic removal reason pre"),
    Removed("synthbase.7_1.silent", reason="synthetic removal reason silent"),
    Added(extra),
)
OVERLAY = Overlay(base="synthbase", clause_map=CLAUSE_MAP, entries=ENTRIES)
PACK = Pack(
    name="synthover",
    code=CODE,
    edition="2",
    version="0.0.3",
    checks=OWN_CHECKS,
    approvals="approvals.yaml",
    base="synthbase",
    overlay=OVERLAY,
)
