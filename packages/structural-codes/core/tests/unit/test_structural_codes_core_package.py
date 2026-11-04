"""Package skeleton tests (plan 0001 task K.T1)."""

import structural_codes


def test_version_constant() -> None:
    assert structural_codes.__version__ == "0.1.0.dev0"
    assert structural_codes.__all__ == ["__version__"]
