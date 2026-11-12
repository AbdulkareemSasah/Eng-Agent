"""ETABS table keys of the model-state read set (spec 0002 section 4.6.4)."""

TABLES = {
    "restraints": "Joint Assignments - Restraints",
    "pattern_defs": "Load Pattern Definitions",
    "combo_defs": "Load Combination Definitions",
    "frame_loads": "Frame Loads Assignments - Distributed",
    "area_loads": "Area Load Assignments - Uniform",
    "wall_sections": "Wall Property Definitions - Specified",  # no thickness in the area-section list, OQ-G10
}
MODEL_EXTENSIONS = (".EDB",)
