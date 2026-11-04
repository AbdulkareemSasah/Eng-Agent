"""FB006 (spec 4.8, AC34): a rationale field must forbid digits (type ``Rationale`` or a probed ``pattern``)."""

from __future__ import annotations

import pytest
from support.forbidden import lines
from support.forbidden_b import expected_lines, scan_b

SOURCE = """\
from typing import Annotated
import typing
from pydantic import BaseModel, Field, StringConstraints
from pkg.text import Rationale
import pkg.text as text


class Good(BaseModel):
    rationale: Rationale
    check_rationale: text.Rationale
    plain: str
    note_rationale_text: str
    tag: Annotated[str, Field(pattern=r"^[^0-9]*$")]
    why_rationale: Annotated[str, Field(pattern=r"^\\D*$")]
    other_rationale: typing.Annotated[str, StringConstraints(pattern=r"^[a-zA-Z ]*$")]


class Bad(BaseModel):
    rationale: str  # <-
    design_rationale: str  # <-
    third_rationale = "fixed"  # <-
    fourth_rationale: int  # <-
    fifth_rationale: Annotated[str, Field(max_length=10)]  # <-
    sixth_rationale: Annotated[str, Field(pattern=r"^[^0-8]*$")]  # <-
    seventh_rationale: Annotated[str, Field(pattern=r"^[a-z0-9 ]*$")]  # <-
    eighth_rationale: Annotated[str, Field(pattern=r"^[^\\u0660-\\u0669]*$")]  # <-
    ninth_rationale: Annotated[str, Field(pattern=r"^[^0-9\\u0660-\\u0669]*$")]  # <-
    tenth_rationale: Annotated[str, Field(pattern=r"^[x]*$")]  # <-
    eleventh_rationale: Annotated[str, Field(pattern=r"(")]  # <-
    twelfth_rationale: Annotated[str, Field(pattern=PATTERN)]  # <-
    thirteenth_rationale: Annotated[int, Field(pattern=r"^\\D*$")]  # <-
    fourteenth_rationale: Rationale | None  # <-


def not_a_class(rationale: str) -> None:
    rationale = "x"
"""


def test_rationale_digit_probe() -> None:
    findings = scan_b(SOURCE, "src/pkg/model.py")
    assert lines(findings, "FB006") == expected_lines(SOURCE)
    assert {f.code for f in findings} == {"FB006"}
    assert len(findings) == len(expected_lines(SOURCE))


@pytest.mark.parametrize(
    ("pattern", "flagged"),
    [
        (r"^\D*$", False),
        (r"^[^0-9]*$", False),
        (r"^[^0-9\u0660-\u0669\u06f0-\u06f9]*$", False),
        (r"^[^0-9\u0660-\u0669]*$", True),  # the extended digits U+06F0 to U+06F9 match
        (r"^[^0-9\u06f0-\u06f9]*$", True),  # the Arabic-Indic digits U+0660 to U+0669 match
        (r"^[^\u0660-\u0669\u06f0-\u06f9]*$", True),  # the ASCII digits match
        (r"^[^5]*$", True),
        (r"^x+$", True),  # "ab" must match
        (r"^$", True),
    ],
)
def test_each_digit_set_is_probed(pattern: str, flagged: bool) -> None:
    source = f"class M:\n    why_rationale: Annotated[str, Field(pattern={pattern!r})]\n"
    assert bool(lines(scan_b(source, "src/pkg/model.py"), "FB006")) is flagged


def test_applies_to_every_source_module() -> None:
    assert lines(scan_b("class M:\n    rationale: str\n", "src/pkg/anything/else.py"), "FB006") == [2]
    assert lines(scan_b("class M:\n    rationale: str\n", "tests/test_model.py"), "FB006") == []
