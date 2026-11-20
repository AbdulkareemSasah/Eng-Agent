"""IDEA adapter gap registry (plan 0014 T6; spec 0014 AC6, section 4.4, section 11 IG-1 to IG-9).

Purpose: hold the IDEA gap identifiers and messages (`NotImplementedGap`). T6 wires IG-1, IG-3 and IG-4 to the gap
tools of section 4.4; IG-2 (load map) is raised from the loads step in T7; the remaining ids are registered for later
tasks. Nothing is sent to the host. Units: none.
"""

from collections.abc import Mapping
from typing import NoReturn

from eng_harness.errors import NotImplementedGap

__all__ = [
    "IDEA_GAPS",
    "TOOL_GAPS",
    "create_project",
    "raise_gap",
    "refuse_tool",
    "set_loads",
]

# Spec 0014 section 11: gap ids and the recommendation text that becomes the refusal message.
IDEA_GAPS: Mapping[str, str] = {
    "IG-1": "idea_set_loads forces have no unit (S12-G12): not served",
    "IG-2": "ETABS to IDEA axis, sign and member-end mapping unconfirmed (contract G-3)",
    "IG-3": "in-memory edit tools do not reach a real calculation: not served",
    "IG-4": "project creation through the server leaves the connection in memory only: not served",
    "IG-5": "reads of the opened REST project are Sasaah defaults: not served",
    "IG-6": "no check_model and no get_stress_strain_results on the IDEA server",
    "IG-7": "no server build id (S12-G1); hash and commit pin stand in",
    "IG-8": "effects with forcesPercentageOnSegments are not supported",
    "IG-9": "position and beamSegmentId in the loading JSON are opaque host keys",
}

# Spec 0014 section 4.4 Gap (20): creation is IG-4; idea_set_loads is IG-1 and IG-3; other gap tools are IG-3.
TOOL_GAPS: Mapping[str, tuple[str, ...]] = {
    "idea_create_project": ("IG-4",),
    "idea_create_project_from_template": ("IG-4",),
    "idea_set_loads": ("IG-1", "IG-3"),
    "idea_create_connection": ("IG-3",),
    "idea_set_members": ("IG-3",),
    "idea_add_plate": ("IG-3",),
    "idea_add_bolt_group": ("IG-3",),
    "idea_add_weld": ("IG-3",),
    "idea_add_cut": ("IG-3",),
    "idea_add_stiffener": ("IG-3",),
    "idea_update_operation": ("IG-3",),
    "idea_delete_operation": ("IG-3",),
    "idea_duplicate_connection": ("IG-3",),
    "idea_rename_connection": ("IG-3",),
    "idea_delete_connection": ("IG-3",),
    "idea_add_load_case": ("IG-3",),
    "idea_set_load_combinations": ("IG-3",),
    "idea_set_project_settings": ("IG-3",),
    "idea_add_material": ("IG-3",),
    "idea_add_section": ("IG-3",),
}


def raise_gap(*gap_ids: str) -> NoReturn:
    """Raise `NotImplementedGap` for one or more gap ids; `KeyError` for an unknown identifier."""
    if not gap_ids:
        raise KeyError("at least one gap id is required")
    messages = [IDEA_GAPS[gap_id] for gap_id in gap_ids]
    raise NotImplementedGap("; ".join(messages), evidence=gap_ids)


def refuse_tool(tool: str) -> NoReturn:
    """Raise the `NotImplementedGap` wired to `tool`; `KeyError` when none is wired."""
    raise_gap(*TOOL_GAPS[tool])


def create_project() -> NoReturn:
    """Refuse creating a project through the server (gap IG-4); nothing is sent."""
    raise_gap("IG-4")


def set_loads() -> NoReturn:
    """Refuse `idea_set_loads` (gaps IG-1 and IG-3); nothing is sent."""
    raise_gap("IG-1", "IG-3")
