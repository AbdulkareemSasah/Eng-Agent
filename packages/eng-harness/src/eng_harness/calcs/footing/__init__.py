"""The footing calcs of spec 0010 section 4.4: explicit registration, no discovery (spec 0003 4.2).

`FOOTING_CALCS` are registered in `eng_harness.calcs.REGISTRY`; `FOOTING_KINDS` are the result kinds their registry
needs (spec 0010 4.2). Each later footing calc is added here by its plan task.
"""

from eng_harness.calc import CalcDef
from eng_harness.calcs.footing.layout import footing_layout
from eng_harness.calcs.footing.plan_size import footing_plan_size
from eng_harness.calcs.footing.resize import footing_resize
from eng_harness.calcs.footing.schedule import footing_schedule
from eng_harness.calcs.footing.status import footing_status
from eng_harness.calcs.footing.subjects import footing_subjects
from eng_harness.kinds.footing import FOOTING_KINDS

FOOTING_CALCS: tuple[CalcDef, ...] = (
    footing_subjects,
    footing_plan_size,
    footing_resize,
    footing_layout,
    footing_status,
    footing_schedule,
)
"""The shipped footing calcs, in registration order."""

__all__ = ["FOOTING_CALCS", "FOOTING_KINDS"]
