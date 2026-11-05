"""Package skeleton tests (plan 0001 task K.T1) and public API declaration (plan 0001 task T14a)."""

import tomllib
from pathlib import Path

import structural_codes

# The modules of spec 0001 section 4.1.
_SPEC_41_MODULES = {
    "structural_codes",
    "structural_codes.errors",
    "structural_codes.meta",
    "structural_codes.inputs",
    "structural_codes.applicability",
    "structural_codes.trace",
    "structural_codes.check",
    "structural_codes.pack",
    "structural_codes.overlay",
    "structural_codes.content_hash",
    "structural_codes.verification",
    "structural_codes.lifecycle",
    "structural_codes.notes",
}

# The section 4.1 modules that exist after plan task T10 (lifecycle and notes come with T11 and T13).
_REQUIRED_NOW = _SPEC_41_MODULES - {"structural_codes.lifecycle", "structural_codes.notes"}


def test_version_constant() -> None:
    assert structural_codes.__version__ == "0.1.0.dev0"
    assert structural_codes.__all__ == ["__version__"]


def test_public_modules_declared() -> None:
    """The existing section 4.1 modules are declared; every declared module exists (one direction, plan T14a)."""
    root = Path(__file__).resolve().parents[2]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    declared = set(config["tool"]["eng-gate"].get("public_modules", []))
    src = root / "src" / "structural_codes"
    existing = {"structural_codes"} | {
        f"structural_codes.{p.stem}" for p in src.glob("*.py") if not p.stem.startswith("_")
    }
    assert declared >= _REQUIRED_NOW
    assert declared <= existing & _SPEC_41_MODULES
