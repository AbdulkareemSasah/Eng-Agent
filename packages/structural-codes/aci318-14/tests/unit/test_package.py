"""Package skeleton tests (plan 0002 task T1, criterion PK-AC1)."""

from importlib import resources

import yaml

import aci318_14


def test_version_and_empty_approvals() -> None:
    """The version is set and the shipped approvals file is the valid empty file (core spec 4.8, AC23)."""
    assert aci318_14.__version__ == "0.1.0.dev0"
    assert aci318_14.__all__ == ["__version__"]
    text = resources.files("aci318_14").joinpath("approvals.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data == {"format": "structural-codes-approvals/1", "approvals": [], "withdrawn": []}
