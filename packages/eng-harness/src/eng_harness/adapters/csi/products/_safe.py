"""SAFE product profile data and model extensions (plan 0008 T3, T5, T7; spec 0008 section 4.1, 4.4, 4.8)."""

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
# Gap registry (spec 0008 section 4.8); T3 wires SG-1; T7 wires SG-2 to SG-5 and SG-9 (AC24, AC25, amendment B-418).
GAPS = {
    "SG-1": "creating a new model is not implemented: provide a prepared model",
    "SG-2": "defining or changing a footing slab section is not implemented",
    "SG-3": "defining or assigning an area spring soil support is not implemented",
    "SG-4": "resizing or moving a footing area is not implemented",
    "SG-5": "slab design run and punching or flexure results are not implemented",
    "SG-6": "soil pressure table reads beyond 2000 rows require per-footing groups",
    "SG-7": "setting column punching dimensions (XDim, YDim) on a point load is not implemented",
    "SG-8": "clearing a joint load with an all-zero assignment is not implemented",
    "SG-9": "FE slab forces, strip results and displacements are not implemented",
}
STEP_GAPS = {
    "new_model": "SG-1",
    "define_slab_section": "SG-2",
    "define_area_spring": "SG-3",
    "resize_area": "SG-4",
    "slab_design": "SG-5",
    "design_results": "SG-5",
    "area_forces": "SG-9",
}
