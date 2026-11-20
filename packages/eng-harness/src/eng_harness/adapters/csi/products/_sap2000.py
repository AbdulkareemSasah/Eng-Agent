"""SAP2000 product profile data and model extensions (plan 0012 T1, T4, T6; spec 0012 section 4.3, 4.4, 4.5)."""

MODEL_EXTENSIONS = (".SDB",)
COMPANION_GLOBS: tuple[str, ...] = ()  # empty until local test L2 (spec 0012 section 4.3)
# Table keys for table-backed reads stay empty while every field-map entry is unknown (spec 0012 section 4.4, AC10).
# Typed list tools supply the T4 state read; table names live in `_sap2000_tables.toml` until L4 keys them.
TABLES: dict[str, str] = {}
READBACK: dict[str, tuple[str, str, str]] = {}
# Declared absences of the state reader (spec 0012 section 4.3, AC8): stories and grids are not produced.
DECLARED_ABSENCES: tuple[str, ...] = ("stories", "grids")
# Gap registry (spec 0012 section 4.5); SP-1 wired in T3; SP-3 (concrete non-beam) wired in T6.
GAPS = {
    "SP-1": "creating a new model is not implemented: provide a prepared model",
    "SP-2": "defining sections, materials or load cases is not implemented",
    "SP-3": "concrete design results for frames that are not beams are not implemented",
    "SP-4": "table-based reads and the edits that need them are not implemented",
    "SP-5": "design orientation, frame labels and local axes are not implemented",
    "SP-6": "choosing which load cases an analysis runs is not implemented",
    "SP-7": "levels and grids are not implemented",
    "SP-8": "cable, link and general-shell workflows are not implemented",
}
STEP_GAPS = {
    "new_model": "SP-1",
    "concrete_non_beam": "SP-3",  # plan 0012 T6 / AC16: concrete design results for non-beams
}
