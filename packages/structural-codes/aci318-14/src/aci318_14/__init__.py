"""ACI 318-14 pack of the structural-codes folder (plan 0002).

Purpose: the version constant and `PACK`, the six footing and three column checks registered under the entry-point group
`structural_codes.packs`. Every check is `draft` until `approvals.yaml` holds an entry for it.
"""

from structural_codes.pack import Pack

from aci318_14.checks.axial_flexure import axial_flexure_uniaxial
from aci318_14.checks.bearing_pressure import bearing_pressure_service
from aci318_14.checks.development_length import development_length_bottom_bars
from aci318_14.checks.flexure import flexure_at_column_face
from aci318_14.checks.max_axial import max_axial_strength
from aci318_14.checks.min_reinforcement import min_flexural_reinforcement
from aci318_14.checks.one_way_shear import one_way_shear
from aci318_14.checks.punching_shear import punching_shear
from aci318_14.checks.reinforcement_limits import longitudinal_reinforcement_limits

__version__ = "0.1.0.dev0"

# `PACK` stays out of `__all__` because tests/unit/test_package.py (T1, outside T9's files) asserts the list.
__all__ = ["__version__"]

PACK = Pack(
    "aci318_14",
    "ACI 318-14",
    "2014",
    __version__,
    checks=(
        bearing_pressure_service,
        one_way_shear,
        punching_shear,
        flexure_at_column_face,
        min_flexural_reinforcement,
        development_length_bottom_bars,
        max_axial_strength,
        axial_flexure_uniaxial,
        longitudinal_reinforcement_limits,
    ),
    approvals="approvals.yaml",
)
