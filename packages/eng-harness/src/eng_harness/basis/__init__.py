"""The design basis of a run (spec 0004): the fields a workflow declares, their rules, and the draft built from them.

Purpose: the public surface of `eng_harness.basis`; later plan tasks add the setup view and the freeze.
"""

from eng_harness.basis._build import (
    BasisDraft,
    DetectedValue,
    DraftField,
    DraftTemplate,
    DraftWarning,
    EngineerEntry,
    EngineerValues,
    build_draft,
)
from eng_harness.basis._fields import BasisInvalid, FieldSpec, check_declaration

__all__ = [
    "BasisDraft",
    "BasisInvalid",
    "DetectedValue",
    "DraftField",
    "DraftTemplate",
    "DraftWarning",
    "EngineerEntry",
    "EngineerValues",
    "FieldSpec",
    "build_draft",
    "check_declaration",
]
