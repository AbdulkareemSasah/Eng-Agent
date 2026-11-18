"""The `model_edit_cycle` definition (plan 0007 T8; spec 0007 AC1, section 4.2, 4.8).

The expected paths, kinds and units are copied from the table of spec 0007 4.8, not from the code under test.
"""

from pathlib import Path

import eng_harness.templates as templates_pkg
from eng_harness.adapters.csi import csi_allowlist
from eng_harness.block import WorkflowDef
from eng_harness.templates import TemplateRepository, resolve

SPEC_FIELDS = (  # spec 0007 4.8: path, kind, unit (or choices)
    ("compare.length_mm", "quantity", "mm"),
    ("compare.angle_deg", "quantity", "deg"),
    ("compare.stress_MPa", "quantity", "MPa"),
    ("compare.unit_weight_kN_m3", "quantity", "kN/m3"),
    ("compare.line_load_kN_m", "quantity", "kN/m"),
    ("compare.area_load_kPa", "quantity", "kPa"),
    ("compare.dimensionless_ratio", "quantity", "1"),
    ("checks.readback_relative_tolerance_ratio", "quantity", "1"),
    ("report.top_n", "count", None),
    ("limits.ratio_limit_ratio", "quantity", "1"),
    ("limits.drift_ratio", "quantity", "1"),
    ("bounds.thickness_min_mm", "quantity", "mm"),
    ("bounds.thickness_max_mm", "quantity", "mm"),
    ("bounds.line_load_min_kN_m", "quantity", "kN/m"),
    ("bounds.line_load_max_kN_m", "quantity", "kN/m"),
    ("bounds.area_load_min_kPa", "quantity", "kPa"),
    ("bounds.area_load_max_kPa", "quantity", "kPa"),
    ("bounds.ratio_min_ratio", "quantity", "1"),
    ("bounds.ratio_max_ratio", "quantity", "1"),
    ("design.run", "choice", None),
    ("attempts.cycles", "count", None),
    ("attempts.change_set", "count", None),
    ("attempts.approval_void", "count", None),
)


def test_workflow_definition() -> None:
    """AC1: version 1, the fields of 4.8 and nothing else, `required_basis` their paths, the adapter's pinned build,
    `csi_unlock_model` always asked, copy on open; and the blank template asks exactly those fields."""
    from eng_harness.workflows.model_edit_cycle import BASIS_FIELDS, EditCycleInput, model_edit_cycle

    assert isinstance(model_edit_cycle, WorkflowDef)
    assert (model_edit_cycle.name, model_edit_cycle.version) == ("model_edit_cycle", 1)
    assert tuple((f.path, f.kind, f.unit) for f in BASIS_FIELDS) == SPEC_FIELDS
    assert model_edit_cycle.basis_fields == BASIS_FIELDS
    assert model_edit_cycle.required_basis == tuple(path for path, _, _ in SPEC_FIELDS)
    assert all(f.required and f.min is None and f.max is None for f in BASIS_FIELDS)  # no value, bound or default
    (design,) = [f for f in BASIS_FIELDS if f.path == "design.run"]
    assert design.choices == ("steel", "concrete", "steel_and_concrete")
    assert dict(model_edit_cycle.min_server_builds) == {"sasaah-csi-mcp": csi_allowlist().sasaah_commit}
    assert model_edit_cycle.always_ask == ("csi_unlock_model",)
    assert model_edit_cycle.copy_on_open is True
    assert model_edit_cycle.input_model is EditCycleInput
    assert EditCycleInput.model_fields["model"].annotation is Path
    assert EditCycleInput.model_fields["visible_host"].default is True

    shipped = Path(templates_pkg.__file__).resolve().parent / "shipped"
    repository = TemplateRepository(shipped, shipped.parent / "no-user-folder")
    (blank,) = [t for t in repository.list() if t.meta.name == "blank"]
    asks = resolve(blank, repository).template.ask_each_run
    assert [(a.path, a.kind, a.unit, a.label) for a in asks] == [
        (f.path, f.kind, f.unit, f.label) for f in BASIS_FIELDS
    ]
    assert [tuple(a.choices) if a.choices else None for a in asks] == [f.choices for f in BASIS_FIELDS]
