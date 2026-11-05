"""The design basis of a run (spec 0004): the fields a workflow declares and their coherence rules.

Purpose: the public surface of `eng_harness.basis`; later plan tasks add the draft, the setup view and the freeze.
"""

from eng_harness.basis._fields import BasisInvalid, FieldSpec, check_declaration

__all__ = ["BasisInvalid", "FieldSpec", "check_declaration"]
