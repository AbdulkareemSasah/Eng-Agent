"""The design basis of a run (spec 0004): the fields a workflow declares, their rules, and the draft built from them.

Purpose: the public surface of `eng_harness.basis`; the setup view; a later plan task adds the freeze.
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
from eng_harness.basis._setup import (
    BasisSetupAnswer,
    BasisSetupPort,
    BasisSetupView,
    SetupRow,
    SetupSection,
    build_setup_view,
)

__all__ = [
    "BasisDraft",
    "BasisInvalid",
    "BasisSetupAnswer",
    "BasisSetupPort",
    "BasisSetupView",
    "DetectedValue",
    "DraftField",
    "DraftTemplate",
    "DraftWarning",
    "EngineerEntry",
    "EngineerValues",
    "FieldSpec",
    "SetupRow",
    "SetupSection",
    "build_draft",
    "build_setup_view",
    "check_declaration",
]
