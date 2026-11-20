"""SAFE product profile data and model extensions (plan 0008 T3, T5; spec 0008 section 4.1, 4.4)."""

MODEL_EXTENSIONS = (".FDB",)
COMPANION_GLOBS: tuple[str, ...] = ()  # empty until local test L2 (spec 0008 section 4.1)
# Table keys of the SAFE model-state read set (spec 0008 section 4.4, 4.5); host names from the SAFE 22 reference.
TABLES = {
    "pattern_defs": "Load Pattern Definitions",
    "combo_defs": "Load Combination Definitions",
    "joint_loads": "Joint Loads Assignments - Force",
    "slab_sections": "Slab Property Definitions",
    "materials_general": "Material Properties - General",
    "materials_mechanical": "Material Properties - Basic Mechanical Properties",
    "materials_concrete": "Material Properties - Concrete Data",
    "soil_properties": "Spring Property Definitions - Area Springs",
    "soil_assignments": "Area Assignments - Area Springs",
}
READBACK: dict[str, tuple[str, str, str]] = {}
