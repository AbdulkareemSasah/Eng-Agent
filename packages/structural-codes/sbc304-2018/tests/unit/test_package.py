"""Package skeleton tests (plan 0003 task T1, criterion AC11)."""

from importlib import resources

import yaml

import sbc304_2018


def test_version_and_empty_approvals() -> None:
    """The version is set and the shipped approvals file is the valid empty file (core spec 4.8, AC23)."""
    assert sbc304_2018.__version__ == "0.1.0.dev0"
    assert sbc304_2018.__all__ == ["__version__"]
    text = resources.files("sbc304_2018").joinpath("approvals.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data == {"format": "structural-codes-approvals/1", "approvals": [], "withdrawn": []}
