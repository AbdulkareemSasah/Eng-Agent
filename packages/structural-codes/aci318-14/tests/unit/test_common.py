"""Shared constants and preconditions of the ACI 318-14 pack (plan 0002 T2; PK-AC2).

Limits come from the clause specs' §5: `fc_min = 17 MPa` (Table 19.2.1.1), `fy_max = 550 MPa` (Table 20.2.2.4(a)),
full contact at `q_min = 0` (FS S5). Each precondition is tested just below, at and above its limit.
"""

# ruff: noqa: N815  # B-271: field names are fixed by the contract's unit suffixes (EC §4.7.2), e.g. fc_MPa

from pathlib import Path
from typing import Any

import pytest
from eng_contract.cited import Cited
from eng_contract.envelope import LiteralInput
from eng_contract.params import ValidatedInput
from eng_contract.verdicts import Subject, SubjectKind
from structural_codes.applicability import Outcome, Precondition
from structural_codes.errors import CheckDefinitionError
from structural_codes.inputs import CheckInputs, bounded
from structural_codes.trace import TraceRecorder

from aci318_14._common import CITED, FC_MIN, FY_MAX, NORMALWEIGHT, ConcreteClass, const
from aci318_14._footing import COMPRESSION, FootingLoads, ServiceFooting, full_contact, statics

_POSITIVE_MPA = Cited(value=0, unit="MPa", source="Mechanics of materials: test input, a strength is positive")
_PREFIXES = ("ACI 318-14 ", "SI prefix", "Mechanics of materials", "Statics", "Geometry")


class _Materials(CheckInputs):
    """Material inputs the shared preconditions read (clause specs §3)."""

    fc_MPa: float = bounded(gt=_POSITIVE_MPA, unit="MPa")
    fy_MPa: float = bounded(gt=_POSITIVE_MPA, unit="MPa")
    concrete_class: ConcreteClass = ConcreteClass.NORMALWEIGHT


def recorder(model_cls: type[Any], **values: Any) -> tuple[Any, TraceRecorder]:
    """Return the validated model and a recorder over it, every field given as a literal."""
    model = model_cls(**values)
    provenance = {name: LiteralInput(literal=value) for name, value in values.items()}
    t = TraceRecorder(
        ValidatedInput(model, provenance),
        calc_id="aci318_14.13_3_1_1.common_test",
        calc_version="0.1.0.dev0",
        content_sha256="0" * 64,
        subject=Subject(kind=SubjectKind.FOOTING, id="F1"),
    )
    return model, t


def _passes(p: Precondition, model_cls: type[Any], **values: Any) -> bool:
    model, t = recorder(model_cls, **values)
    return bool(p.test(model, t))


_LOADS = {"FX_kN": 0.0, "FY_kN": 0.0, "MX_kNm": 0.0, "Lx_mm": 2500.0, "Ly_mm": 2500.0, "reaction_height_mm": 0.0}


def _contact(my: float) -> tuple[float, bool]:
    """q_min and FULL_CONTACT after COMPRESSION (which runs the statics), strength form.

    Footing 2000 x 2000 mm, FZ = 1200 kN: q_avg = 1200/4 = 300 kPa and q_bend = MY/(2**3/6) = 0.75*MY kPa, so
    q_min = 0 at MY = 400 kN.m, exactly zero in float64 in the implemented order of operations.
    """
    square = {**_LOADS, "Lx_mm": 2000.0, "Ly_mm": 2000.0}
    model, t = recorder(FootingLoads, **square, FZ_kN=1200.0, MY_kNm=my)
    assert COMPRESSION.test(model, t)
    return t.value("q_min_kPa"), bool(full_contact("G-2").test(model, t))


def test_shared_preconditions() -> None:
    """Below, at and above each limit (PK-AC2): 17 MPa passes FC_MIN, 550 MPa passes FY_MAX, q_min = 0 passes."""
    base = {"fc_MPa": 28.0, "fy_MPa": 420.0}
    assert not _passes(FC_MIN, _Materials, **{**base, "fc_MPa": 16.0})
    assert _passes(FC_MIN, _Materials, **{**base, "fc_MPa": 17.0})
    assert _passes(FC_MIN, _Materials, **{**base, "fc_MPa": 18.0})
    assert _passes(FY_MAX, _Materials, **{**base, "fy_MPa": 549.0})
    assert _passes(FY_MAX, _Materials, **{**base, "fy_MPa": 550.0})
    assert not _passes(FY_MAX, _Materials, **{**base, "fy_MPa": 551.0})
    assert _passes(NORMALWEIGHT, _Materials, **base)
    for other in (ConcreteClass.LIGHTWEIGHT, ConcreteClass.SAND_LIGHTWEIGHT):
        assert not _passes(NORMALWEIGHT, _Materials, **base, concrete_class=other)
    assert _contact(399.0) == pytest.approx((0.75, True), abs=1e-9)
    assert _contact(400.0) == (0.0, True)
    assert _contact(401.0) == pytest.approx((-0.75, False), abs=1e-9)


def test_compression_limit() -> None:
    """COMPRESSION needs N > 0: strength N = FZ; service N = FZ + W (bearing BD-3 gives N < 0)."""
    for fz, expected in ((-1.0, False), (0.0, False), (1.0, True)):
        model, t = recorder(FootingLoads, **_LOADS, FZ_kN=fz, MY_kNm=0.0)
        assert COMPRESSION.test(model, t) is expected
    service = {**_LOADS, "MY_kNm": 0.0, "h_mm": 600.0, "soil_depth_mm": 1000.0, "gamma_c_kN_m3": 24.0}
    service |= {"gamma_s_kN_m3": 18.0, "surcharge_kPa": 0.0}
    model, t = recorder(ServiceFooting, **service, FZ_kN=-250.0)  # bearing BD-3: N = -250 + 202.5 < 0
    assert not COMPRESSION.test(model, t)
    model, t = recorder(ServiceFooting, **service, FZ_kN=-200.0)  # N = 2.5 kN > 0: the weight carries it
    assert COMPRESSION.test(model, t)


def test_full_contact_needs_the_statics() -> None:
    """FULL_CONTACT declared without COMPRESSION before it is a definition error."""
    model, t = recorder(FootingLoads, **_LOADS, FZ_kN=1700.0, MY_kNm=0.0)
    with pytest.raises(CheckDefinitionError):
        full_contact("G-1").test(model, t)
    with pytest.raises(CheckDefinitionError):
        full_contact("G1")


def test_declarations() -> None:
    """Ids, outcomes and clauses of the clause specs §2; the gap id appears in the message."""
    assert [(p.id, p.outcome, p.clause) for p in (NORMALWEIGHT, FC_MIN, FY_MAX)] == [
        ("NORMALWEIGHT", Outcome.NEEDS_ENGINEER, "19.2.4.2"),
        ("FC_MIN", Outcome.NEEDS_ENGINEER, "Table 19.2.1.1"),
        ("FY_MAX", Outcome.NEEDS_ENGINEER, "Table 20.2.2.4(a)"),
    ]
    assert "G-1" in NORMALWEIGHT.description
    assert (COMPRESSION.id, COMPRESSION.outcome) == ("COMPRESSION", Outcome.NEEDS_ENGINEER)
    contact = full_contact("G-2")
    assert (contact.id, contact.outcome) == ("FULL_CONTACT", Outcome.NEEDS_ENGINEER)
    assert "G-2" in contact.description


def test_cited_constants() -> None:
    """The shared constants carry the values and citations of the clause specs §5."""
    expected = {
        "phi_v": (0.75, "ACI 318-14 Table 21.2.1"),
        "lambda_nw": (1.0, "ACI 318-14 19.2.4.2"),
        "sf_max": (8.3, "ACI 318-14 22.5.3.1"),
        "fc_min": (17, "ACI 318-14 Table 19.2.1.1"),
        "fy_max": (550, "ACI 318-14 Table 20.2.2.4(a)"),
        "k_m": (0.001, "SI prefix"),
        "k_kN": (0.001, "SI prefix"),
        "k_kNm": (1.0e-6, "SI prefix"),
        "c_S": (6, "Mechanics of materials"),
        "c_I": (12, "Mechanics of materials"),
        "c_half": (2, "Statics"),
        "c_third": (3, "Statics"),
    }
    assert {name: c.value for name, c in CITED.items()} == {name: v for name, (v, _) in expected.items()}
    for name, (_, source) in expected.items():
        assert CITED[name].source.startswith(source), name
    assert all(c.source.startswith(_PREFIXES) for c in CITED.values())
    _, t = recorder(_Materials, fc_MPa=28.0, fy_MPa=420.0)
    assert const(t, "phi_v") == 0.75
    assert t.to_trace(outputs=[], status=None).constants[0].cited == CITED["phi_v"]


def test_statics_is_reused_not_repeated() -> None:
    """COMPRESSION records the statics; calling the statics again on the same trace is a definition error."""
    model, t = recorder(FootingLoads, **_LOADS, FZ_kN=1700.0, MY_kNm=0.0)
    assert COMPRESSION.test(model, t)
    with pytest.raises(CheckDefinitionError):
        statics(model, t)


_CLAUSES = Path(__file__).resolve().parents[3] / "docs" / "clauses" / "aci318_14"
_SF_NOTE = "true unit MPa^0.5; stored as 1 because the eng-contract unit table has no MPa^0.5 (plan 0002 §6 Q6)"


def _section5_rows(text: str) -> list[list[str]]:
    """Return the cells of the §5 table rows of a clause spec (plan 0002 T2c)."""
    body = text.split("\n## 5.", 1)[1].split("\n## ", 1)[0]
    return [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in body.splitlines() if ln.startswith("| `")]


def test_shared_sources_match_clause_specs() -> None:
    """Each shared constant's row in every clause spec §5 equals its `Cited` (plan 0002 §1.1, T2c)."""
    seen: set[str] = set()
    for spec in sorted(_CLAUSES.glob("*.md")):
        for symbol, value, unit, citation, *_ in _section5_rows(spec.read_text(encoding="utf-8")):
            name = symbol.strip("`")
            if name not in CITED or (name == "c_half" and "development_length" in spec.name):
                continue
            seen.add(name)
            assert (citation, float(value), unit) == (CITED[name].source, CITED[name].value, CITED[name].unit), spec
    assert seen == set(CITED)
    assert CITED["sf_max"].note == _SF_NOTE
