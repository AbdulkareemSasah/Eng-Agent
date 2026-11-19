"""SAP2000 product profile data and model extensions (plan 0012 T1; spec 0012 section 4.3)."""

MODEL_EXTENSIONS = (".SDB",)
COMPANION_GLOBS: tuple[str, ...] = ()  # empty until local test L2 (spec 0012 section 4.3)
TABLES: dict[str, str] = {}
READBACK: dict[str, tuple[str, str, str]] = {}
