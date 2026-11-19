"""The column-workflow calcs of spec 0013 section 4.4: explicit registration, no discovery (spec 0003 4.2).

`COLUMN_DESIGN_CALCS` are registered in `eng_harness.calcs.REGISTRY`; `COLUMN_DESIGN_KINDS` are the result kinds their
registry needs (spec 0013 4.2). Each later column calc (plan 0013 T3, T4, T5, T7, T8) is added here by its plan task.
"""

from eng_harness.calc import CalcDef
from eng_harness.calcs.column_design.change_set import column_change_set
from eng_harness.calcs.column_design.column_select import column_select
from eng_harness.calcs.column_design.section_match import column_section_match
from eng_harness.kinds.column_design import COLUMN_DESIGN_KINDS

COLUMN_DESIGN_CALCS: tuple[CalcDef, ...] = (column_select, column_section_match, column_change_set)
"""The shipped column-workflow calcs, in registration order."""

__all__ = ["COLUMN_DESIGN_CALCS", "COLUMN_DESIGN_KINDS"]
