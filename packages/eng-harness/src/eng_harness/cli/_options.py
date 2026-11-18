"""The generated `--<field>` options of `run` (spec 0006 section 4.2.1, AC14).

Purpose: a workflow's `options_model` is its command-line setup form. `run` offers one option for each top-level field
of type `str`, `int`, `bool`, enum or `Literal` (an optional one too), and none for a quantity or a nested model: those
values come from `--input FILE`, as references or literals (P2). A value given on the command line replaces the
same field of the input file. Units: none. Errors: `UsageError` (exit 2) for an option the model does not offer.
"""

import argparse
import enum
import types
from collections.abc import Sequence
from typing import Any, Literal, NoReturn, Union, get_args, get_origin

from pydantic import BaseModel

from eng_harness.cli._parser import UsageError


class _Options(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(f"eng-harness run: error: {message}")


def _unwrap(annotation: Any) -> Any:
    """`X | None` is offered as `X`."""
    if get_origin(annotation) in (Union, types.UnionType):
        rest = [part for part in get_args(annotation) if part is not type(None)]
        if len(rest) == 1:
            return rest[0]
    return annotation


def _choices(annotation: Any) -> tuple[Any, ...] | None:
    """The values an enum or a `Literal` allows, else `None`."""
    if get_origin(annotation) is Literal:
        return get_args(annotation)
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return tuple(member.value for member in annotation)
    return None


def option_fields(model: type[BaseModel]) -> dict[str, Any]:
    """The top-level fields of `model` that `run` offers as options, by name, with the annotation that parses them."""
    offered = {}
    for name, info in model.model_fields.items():
        annotation = _unwrap(info.annotation)
        if annotation in (str, int, bool) or _choices(annotation) is not None:
            offered[name] = annotation
    return offered


def parse_options(model: type[BaseModel] | None, rest: Sequence[str]) -> dict[str, Any]:
    """The values `rest` (the arguments the shared parser did not know) give to the fields `model` offers.

    Raises:
        UsageError: an argument that no offered field names, or a value that is not of the field's type.
    """
    parser = _Options(prog="eng-harness run", add_help=False, allow_abbrev=False)
    for name, annotation in (option_fields(model) if model is not None else {}).items():
        flag = "--" + name.replace("_", "-")
        if annotation is bool:
            parser.add_argument(flag, dest=name, action=argparse.BooleanOptionalAction, default=argparse.SUPPRESS)
            continue
        allowed = _choices(annotation)
        kind = type(allowed[0]) if allowed else annotation
        parser.add_argument(flag, dest=name, type=kind, choices=allowed, default=argparse.SUPPRESS)
    return vars(parser.parse_args(list(rest)))
