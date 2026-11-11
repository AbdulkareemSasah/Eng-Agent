"""Tests of the error types and check metadata (plan 0001 task T2; spec 0001 AC1, AC2, sections 4.2 and 6)."""

from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.verdicts import SubjectKind

from structural_codes import errors, meta
from structural_codes.errors import (
    ApprovalsFileError,
    CheckDefinitionError,
    CheckNotUsable,
    NotImplementedGap,
    TraceValueError,
    VerificationDataError,
)
from structural_codes.meta import CheckMeta, GapDecl, clause_token

_MISSING = object()

# Structural fixtures only: no engineering value is involved (the clause numbers are labels, not data).
_GOOD: dict[str, Any] = {
    "check_id": "synthbase.22_6_5_2.shear_one_way",
    "pack": "synthbase",
    "code": "Synthetic Code",
    "edition": "1",
    "clauses": ("22.6.5.2", "22.6.1"),
    "title": "One-way shear of a synthetic member",
    "members": {SubjectKind.SECTION, SubjectKind.AREA},
    "spec": "synthbase/synthbase.22_6_5_2.shear_one_way.md",
}


def _meta(**changes: Any) -> CheckMeta:
    data = {**_GOOD, **changes}
    return CheckMeta(**{k: v for k, v in data.items() if v is not _MISSING})


def test_clause_token_examples() -> None:
    assert clause_token("22.6.5.2") == "22_6_5_2"
    assert clause_token("21.2.1(b)") == "21_2_1_b"
    assert clause_token(" A-1.2 ") == "a_1_2"
    assert clause_token("(c)(2)") == "c_2"
    assert clause_token("9") == "9"


def test_check_id_rule() -> None:
    ok = _meta()
    assert ok.check_id == "synthbase.22_6_5_2.shear_one_way"
    assert ok.clauses == ("22.6.5.2", "22.6.1")
    assert _meta(check_id="synthbase.21_2_1_b.phi", clauses=("21.2.1(b)",)).pack == "synthbase"

    bad_ids = [
        "synthbase.22_6_5_2",  # two segments
        "synthbase.22_6_5_2.shear.extra",  # four segments
        "Synthbase.22_6_5_2.shear_one_way",  # upper case
        "synthbase.22.6.5.2.shear_one_way",  # dots inside the clause segment
        "synthbase.22_6_5_2.1shear",  # short name starts with a digit
        "synthbase.22_6_5_2.shear-one-way",  # hyphen
        "synthbase.22_6_5_2.",  # empty short name
        "",
        "synthbase.22_6_5_2.shear_one_way\n",  # a trailing newline must not slip through a `$` anchor
    ]
    for bad in bad_ids:
        with pytest.raises(CheckDefinitionError):
            _meta(check_id=bad)

    # Well-formed for the contract but not for this package.
    with pytest.raises(CheckDefinitionError, match="pack"):
        _meta(check_id="otherpack.22_6_5_2.shear_one_way")
    with pytest.raises(CheckDefinitionError, match="clause"):
        _meta(check_id="synthbase.22_6_1.shear_one_way")  # the second clause, not the first
    with pytest.raises(CheckDefinitionError, match="clause"):
        _meta(check_id="synthbase.22_6_5_3.shear_one_way")
    with pytest.raises(CheckDefinitionError):
        _meta(pack="Synth-Base", check_id="Synth-Base.22_6_5_2.shear_one_way")


@pytest.mark.parametrize("name", ["code", "edition", "clauses", "title", "members", "check_id", "pack", "spec"])
def test_metadata_fields(name: str) -> None:
    with pytest.raises(CheckDefinitionError, match=name):
        _meta(**{name: _MISSING})


def test_error_message_names_model_and_fields() -> None:
    with pytest.raises(CheckDefinitionError) as one:
        _meta(code=_MISSING)
    assert str(one.value).startswith("invalid CheckMeta: code: ")
    with pytest.raises(CheckDefinitionError) as two:
        _meta(edition=_MISSING, code=_MISSING)
    assert str(two.value).startswith("invalid CheckMeta: code, edition: ")
    with pytest.raises(CheckDefinitionError) as model_level:
        _meta(clauses=())
    assert str(model_level.value).startswith("invalid CheckMeta: model: ")
    with pytest.raises(CheckDefinitionError) as nested:
        _meta(gaps=({"id": "bad", "clause": "1", "reason": "r"},))
    assert str(nested.value).startswith("invalid GapDecl: id: ")


def test_metadata_field_values() -> None:
    with pytest.raises(CheckDefinitionError):
        _meta(members=set())
    with pytest.raises(CheckDefinitionError):
        _meta(members={"banana"})
    with pytest.raises(CheckDefinitionError):
        _meta(members={object()})
    with pytest.raises(CheckDefinitionError):
        _meta(clauses=())
    with pytest.raises(CheckDefinitionError):
        _meta(clauses=("",))
    with pytest.raises(CheckDefinitionError):
        _meta(unexpected_field=1)

    # Length bounds of spec 4.2: both edges.
    assert _meta(code="c" * 100, edition="e" * 20, title="t" * 200, title_ar="ع" * 200)
    assert _meta(clauses=("1" * 40,), check_id="synthbase." + "1" * 40 + ".shear_one_way")
    for field, size in (("code", 101), ("edition", 21), ("title", 201), ("title_ar", 201)):
        with pytest.raises(CheckDefinitionError):
            _meta(**{field: "x" * size})
    for field in ("code", "edition", "title", "title_ar"):
        with pytest.raises(CheckDefinitionError):
            _meta(**{field: ""})
    with pytest.raises(CheckDefinitionError):
        _meta(clauses=("1" * 41,), check_id="synthbase." + "1" * 41 + ".shear_one_way")

    assert _meta(assumptions=("a" * 500,)).assumptions == ("a" * 500,)
    with pytest.raises(CheckDefinitionError):
        _meta(assumptions=("a" * 501,))
    assert _meta(unconditional="u" * 500).unconditional == "u" * 500
    with pytest.raises(CheckDefinitionError):
        _meta(unconditional="u" * 501)
    with pytest.raises(CheckDefinitionError):
        _meta(unconditional="")
    assert _meta().unconditional is None
    assert _meta().gaps == ()
    assert _meta().assumptions == ()
    assert _meta().title_ar is None
    assert _meta().members == frozenset({SubjectKind.SECTION, SubjectKind.AREA})


@pytest.mark.parametrize("path", ["a.md", "synthbase/a.b.md", "dir/sub/x_y-z.md"])
def test_spec_path_accepted(path: str) -> None:
    assert _meta(spec=path).spec == path


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/abs/a.md",
        "C:/a.md",
        "c:a.md",
        "dir\\a.md",
        "../a.md",
        "dir/../a.md",
        "dir//a.md",
        "./a.md",
        "a.txt",
        "a",
        "a.MD",
        ".md",
        "dir/.md",
        "a.md/",
    ],
)
def test_spec_path_rejected(path: str) -> None:
    with pytest.raises(CheckDefinitionError):
        _meta(spec=path)


def test_gap_declarations() -> None:
    g = GapDecl(id="G-3", clause="22.6.5.2", reason="not covered")
    assert (g.id, g.clause, g.reason) == ("G-3", "22.6.5.2", "not covered")
    assert _meta(gaps=(g,)).gaps == (g,)
    assert _meta(gaps=[{"id": "G-12", "clause": "1", "reason": "r"}]).gaps[0].id == "G-12"
    for bad in ("G-", "g-1", "G1", "G-1a", "G-1\n", " G-1", ""):
        with pytest.raises(CheckDefinitionError):
            _meta(gaps=({"id": bad, "clause": "1", "reason": "r"},))
    for missing in ("id", "clause", "reason"):
        data = {"id": "G-1", "clause": "1", "reason": "r"}
        del data[missing]
        with pytest.raises(CheckDefinitionError):
            _meta(gaps=(data,))
    with pytest.raises(CheckDefinitionError):
        _meta(gaps=({"id": "G-1", "clause": "1", "reason": "r", "x": 1},))
    with pytest.raises(CheckDefinitionError):
        _meta(gaps=({"id": "G-1", "clause": "", "reason": "r"},))
    with pytest.raises(CheckDefinitionError):
        _meta(gaps=({"id": "G-1", "clause": "1", "reason": ""},))
    # Two gaps with one id would make "declared" ambiguous.
    with pytest.raises(CheckDefinitionError, match="G-1"):
        _meta(gaps=({"id": "G-1", "clause": "1", "reason": "r"}, {"id": "G-1", "clause": "2", "reason": "s"}))


def test_metadata_is_frozen_and_error_chained() -> None:
    m = _meta()
    with pytest.raises(Exception, match="frozen"):
        m.title = "other"
    with pytest.raises(CheckDefinitionError) as info:
        _meta(code=_MISSING)
    assert info.value.__cause__ is not None  # the pydantic error stays reachable
    assert not isinstance(info.value, ContractError)


def test_error_types() -> None:
    assert sorted(errors.__all__) == sorted(
        [
            "CheckDefinitionError",
            "NotImplementedGap",
            "TraceValueError",
            "CheckNotUsable",
            "ApprovalsFileError",
            "VerificationDataError",
        ]
    )
    assert meta.__all__ == ["CheckMeta", "GapDecl", "clause_token"]
    for cls in (CheckDefinitionError, TraceValueError, ApprovalsFileError, VerificationDataError, NotImplementedGap):
        assert issubclass(cls, Exception)
        assert not issubclass(cls, ContractError)
    assert CheckDefinitionError("x").args == ("x",)

    gap = NotImplementedGap("G-3", clause="22.6.5.2", reason="out of scope")
    assert (gap.gap_id, gap.clause, gap.reason) == ("G-3", "22.6.5.2", "out of scope")
    assert "G-3" in str(gap)
    assert "22.6.5.2" in str(gap)
    assert "out of scope" in str(gap)

    err = CheckNotUsable("synthbase.22_6_5_2.shear_one_way", "state: draft")
    assert isinstance(err, ContractError)
    assert err.detail.code is ErrorCode.INVALID_ARGUMENT
    assert err.detail.field == "check_id"
    assert err.detail.hint == "state: draft"
    assert err.detail.retryable is False
    assert "synthbase.22_6_5_2.shear_one_way" in err.detail.message


def test_check_version() -> None:
    assert _meta().version == 1
    assert _meta(version=3).version == 3
    for bad in (0, -1):
        with pytest.raises(CheckDefinitionError, match="version"):
            _meta(version=bad)
    with pytest.raises(CheckDefinitionError, match="version"):
        _meta(version="2")
    with pytest.raises(CheckDefinitionError, match="version"):
        _meta(version=1.5)
