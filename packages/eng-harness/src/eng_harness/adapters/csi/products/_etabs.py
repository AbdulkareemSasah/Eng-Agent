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
READBACK = {  # read-back tables of spec 4.6.2: (table, key column, value column); host facts to confirm locally, OQ-G10
    "area_section": ("Area Assignments - Section Properties", "UniqueName", "Section"),
    "wall_section": (TABLES["wall_sections"], "Name", "Thickness"),  # the thickness is in the model's present units
}
