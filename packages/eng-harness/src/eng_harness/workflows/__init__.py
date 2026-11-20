"""Shipped workflows of eng-harness (spec 0007 4.2; plan 0007 T9b).

`SHIPPED` is the tuple `block.discover()` builds its registry from. Later plans append their blocks to the same tuple.
The submodule name `model_edit_cycle` stays the package (not the workflow callable) so
`from eng_harness.workflows import model_edit_cycle` keeps working.
"""

import eng_harness.workflows.model_edit_cycle as _edit

__all__ = ["SHIPPED"]

SHIPPED = (
    _edit.model_edit_cycle,
    _edit.read_state,
    _edit.obtain_change_set,
    _edit.apply_change_set,
    _edit.edit_cycle_once,
    _edit.run_and_summarize,
    _edit.engineer_turn_only,
    _edit.promote_revision,
    _edit.sign_off_run,
)
