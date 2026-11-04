"""Kind names, the kind registry and the neutral kinds (spec 4.10).

Purpose: the payload models that travel in result records, by kind name. `NEUTRAL_KINDS` holds those defined here;
other packages extend it with their own prefixes through `KindRegistry.extend`.
Errors: `KindNotRegistered` (`INVALID_ARGUMENT`) on lookup of an unknown kind.
"""

from eng_contract._types import KindName
from eng_contract.kinds import basis, forces, issues, model, verdicts
from eng_contract.kinds._registry import NEUTRAL_FAMILIES, KindNotRegistered, KindRegistry

NEUTRAL_KINDS = KindRegistry(
    {
        "model.stories/1": model.Stories,
        "model.grid_system/1": model.GridSystem,
        "model.frame_placements/1": model.FramePlacements,
        "model.area_placements/1": model.AreaPlacements,
        "model.sections/1": model.Sections,
        "model.materials/1": model.Materials,
        "model.load_set/1": model.LoadSet,
        "model.joint_restraints/1": model.JointRestraints,
        "forces.joint_reactions/1": forces.JointReactions,
        "forces.member_end/1": forces.MemberEnd,
        "forces.story_drifts/1": forces.StoryDrifts,
        "basis.design_basis/1": basis.DesignBasis,
        "basis.engineer_input/1": basis.EngineerInput,
        "verdicts.set/1": verdicts.VerdictSet,
        "issues.model_check/1": issues.ModelCheck,
    }
)
"""The neutral kinds defined in this version of the package."""

__all__ = ["NEUTRAL_FAMILIES", "NEUTRAL_KINDS", "KindName", "KindNotRegistered", "KindRegistry"]
