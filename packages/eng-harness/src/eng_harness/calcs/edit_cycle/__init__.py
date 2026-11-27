"""The edit-cycle calcs of spec 0007 section 4.4: explicit registration, no discovery (spec 0003 4.2).

`EDIT_CYCLE_CALCS` are registered in `eng_harness.calcs.REGISTRY`; `EDIT_CYCLE_KINDS` are the result kinds their
registry needs (spec 0007 4.2). Each later edit-cycle calc is added here by its plan task.
"""

from eng_harness.calc import CalcDef
from eng_harness.calcs.edit_cycle.analysis_summary import analysis_summary
from eng_harness.calcs.edit_cycle.change_set_check import change_set_check
from eng_harness.calcs.edit_cycle.expected_effects import expected_effects
from eng_harness.calcs.edit_cycle.host_design_verdicts import host_design_verdicts
from eng_harness.kinds.edit_cycle import EDIT_CYCLE_KINDS

EDIT_CYCLE_CALCS: tuple[CalcDef, ...] = (change_set_check, expected_effects, analysis_summary, host_design_verdicts)
"""The shipped edit-cycle calcs, in registration order."""

__all__ = ["EDIT_CYCLE_CALCS", "EDIT_CYCLE_KINDS"]
