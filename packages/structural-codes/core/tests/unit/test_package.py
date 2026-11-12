"""Package skeleton tests (plan 0001 task K.T1), public API declaration (T14a, T14b) and package-level checks (T14)."""

import ast
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
    assert structural_codes.__all__ == ["BatchItem", "Evaluation", "Mode", "__version__", "evaluate", "evaluate_batch"]
    for name in structural_codes.__all__:
        assert hasattr(structural_codes, name)


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


def test_lifecycle_declared() -> None:
    """structural_codes.lifecycle is a declared public module (plan T14b), so the packs tests may import it."""
    root = Path(__file__).resolve().parents[2]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert "structural_codes.lifecycle" in config["tool"]["eng-gate"]["public_modules"]


def _declared_modules() -> set[str]:
    root = Path(__file__).resolve().parents[2]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return set(config["tool"]["eng-gate"]["public_modules"])


def test_public_modules() -> None:
    """AC38: the declared public modules are exactly the modules of spec 4.1, and each exists in src/."""
    root = Path(__file__).resolve().parents[2]
    src = root / "src" / "structural_codes"
    existing = {"structural_codes"} | {
        f"structural_codes.{p.stem}" for p in src.glob("*.py") if not p.stem.startswith("_") and p.stem != "__main__"
    }
    assert _declared_modules() == _SPEC_41_MODULES
    assert existing == _SPEC_41_MODULES


def test_no_engineering_constants() -> None:
    """AC36: every Cited source starts with a design document name, and no core module defines a check."""
    allowed = ("04-tool-contract", "10-structural-codes")
    src = Path(__file__).resolve().parents[2] / "src" / "structural_codes"
    cited = 0
    for path in sorted(src.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Cited":
                for kw in node.keywords:
                    if kw.arg == "source":
                        assert isinstance(kw.value, ast.Constant), f"{path.name}:{node.lineno} source not a literal"
                        assert str(kw.value.value).startswith(allowed), f"{path.name}:{node.lineno} source"
                        cited += 1
            if isinstance(node, ast.FunctionDef):
                for deco in node.decorator_list:
                    target = deco.func if isinstance(deco, ast.Call) else deco
                    name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
                    assert name != "check", f"{path.name}:{node.lineno} defines a check"
    assert cited > 0
