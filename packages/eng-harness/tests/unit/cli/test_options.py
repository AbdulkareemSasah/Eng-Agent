"""Generated `run` options (spec 0006 AC14): scalars, enums and literals are offered; quantities and models are not."""

import enum
from typing import Literal

import pytest
from pydantic import BaseModel

from eng_harness.cli._options import option_fields, parse_options
from eng_harness.cli._parser import UsageError


class Kind(enum.StrEnum):
    BEAM = "beam"
    COLUMN = "column"


class Nested(BaseModel):
    depth: int = 1


class Options(BaseModel):
    title: str = ""
    count: int = 1
    dry_run: bool = False
    kind: Kind = Kind.BEAM
    shape: Literal["tee", "box"] = "tee"
    maybe: str | None = None
    load: float = 0.0
    nested: Nested = Nested()
    tags: list[str] = []


def test_generated_options_exclude_quantities() -> None:
    assert list(option_fields(Options)) == ["title", "count", "dry_run", "kind", "shape", "maybe"]
    values = parse_options(
        Options,
        ["--title", "T", "--count", "3", "--dry-run", "--kind", "column", "--shape", "box", "--maybe", "m"],
    )
    assert values == {"title": "T", "count": 3, "dry_run": True, "kind": "column", "shape": "box", "maybe": "m"}
    assert parse_options(Options, ["--no-dry-run"]) == {"dry_run": False}
    assert parse_options(Options, []) == {}  # an option not given is not in the input


@pytest.mark.parametrize(
    "rest",
    [["--load", "1.5"], ["--nested", "x"], ["--tags", "a"], ["--count", "many"], ["--kind", "wall"], ["--cnt", "1"]],
)
def test_options_not_offered_or_bad_are_usage_errors(rest: list[str]) -> None:
    with pytest.raises(UsageError):
        parse_options(Options, rest)


def test_no_options_model_offers_nothing() -> None:
    assert parse_options(None, []) == {}
    with pytest.raises(UsageError):
        parse_options(None, ["--title", "T"])
