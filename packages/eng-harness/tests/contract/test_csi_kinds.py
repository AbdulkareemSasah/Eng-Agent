"""The CSI harness kinds live in `eng_harness.kinds.csi` and are registered (plan 0002 T21; spec 0002 AC46)."""

import importlib
from pathlib import Path

import pytest

from eng_harness._kinds import HARNESS_KINDS

KIND_MODELS = {
    "harness.csi_model_status/1": "CsiModelStatus",
    "harness.csi_analysis_run/1": "CsiAnalysisRun",
    "harness.csi_analysis_status/1": "CsiAnalysisStatus",
    "harness.csi_design_run/1": "CsiDesignRun",
    "harness.csi_design_results/1": "CsiRows",
    "harness.csi_analysis_messages/1": "CsiRows",
}


def test_csi_kinds_registered() -> None:
    """Each of the six kinds is in `HARNESS_KINDS`, as the model of the kinds module that `_replies.py` re-exports."""
    kinds = importlib.import_module("eng_harness.kinds.csi")
    replies = importlib.import_module("eng_harness.adapters.csi._replies")
    assert dict(kinds.CSI_KINDS) == {kind: getattr(kinds, name) for kind, name in KIND_MODELS.items()}
    for kind, name in KIND_MODELS.items():
        assert HARNESS_KINDS[kind] is getattr(kinds, name)
        assert getattr(replies, name) is getattr(kinds, name)
    assert replies.CSI_KINDS is kinds.CSI_KINDS


def test_kinds_module_imports_pydantic_only() -> None:
    """The module is admitted to the calcs (spec 0003 4.3), so it imports nothing of the harness or the contract."""
    kinds = importlib.import_module("eng_harness.kinds.csi")
    text = Path(str(kinds.__file__)).read_text(encoding="utf-8")
    imports = [line for line in text.splitlines() if line.startswith(("import ", "from "))]
    assert all(line.startswith("from pydantic import") for line in imports), imports


def test_registry_refuses_a_second_registration() -> None:
    """`extend` refuses a kind that is already registered, so the kinds are registered exactly once."""
    from eng_contract.params import ContractDefinitionError

    kinds = importlib.import_module("eng_harness.kinds.csi")
    with pytest.raises(ContractDefinitionError):
        HARNESS_KINDS.extend(kinds.CSI_KINDS)
