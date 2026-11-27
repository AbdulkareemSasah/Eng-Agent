"""Strict YAML 1.2 loader for template and values files (spec 0004 section 4.3, AC7).

Purpose: read one YAML document as plain JSON data (dict, list, str, int, float, bool, None) and refuse everything that
could change a value silently: duplicate keys, anchors, aliases, merge keys, explicit tags, non-string keys, more than
one document, non-finite numbers, files over `MAX_BYTES` and nesting deeper than `MAX_DEPTH`.
Scalars follow the YAML 1.2 core schema only: `no`, `on` and `yes` are strings, `1:30` is a string, `010` is the
integer 10, `0o10` is 8, `0x1F` is 31, a date such as `2026-01-31` is a string, `1_000` and `0b11` are strings.
Units: none; nothing is converted. Errors: `TemplateInvalid` with reason `yaml_invalid` (or `not_found` for a missing
file); the message holds the reason and the key path, never file contents. Other `OSError`s are not caught.
"""

import math
import re
from pathlib import Path
from typing import Any, Final

from pydantic import JsonValue
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from ruamel.yaml.events import CollectionEndEvent, CollectionStartEvent, DocumentStartEvent, NodeEvent
from ruamel.yaml.resolver import VersionedResolver

from eng_harness.templates._model import TemplateInvalid

MAX_BYTES: Final = 1024 * 1024
MAX_DEPTH: Final = 8

_CORE = "tag:yaml.org,2002:"
_FLOAT = r"[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN)"
_DIGITS = list("-+0123456789")
# YAML 1.2 core schema (revision 1.2.2, section 10.3.2), first character -> candidate (tag, pattern) pairs.
_RULES: Final[dict[str | None, list[tuple[str, re.Pattern[str]]]]] = {}
for _tag, _pattern, _first in (
    ("null", r"~|null|Null|NULL|", ["~", "n", "N", ""]),
    ("bool", r"true|True|TRUE|false|False|FALSE", list("tTfF")),
    ("int", r"[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+", _DIGITS),
    ("float", _FLOAT, [*_DIGITS, "."]),
):
    for _char in _first:
        _RULES.setdefault(_char, []).append((_CORE + _tag, re.compile(f"^(?:{_pattern})$")))


class _CoreResolver(VersionedResolver):
    """Resolver with the YAML 1.2 core schema only: no merge key, timestamp, sexagesimal or underscore numbers."""

    @property
    def processing_version(self) -> tuple[int, int]:
        """The only version this loader reads."""
        return (1, 2)

    @property
    def versioned_resolver(self) -> dict[str | None, list[tuple[str, re.Pattern[str]]]]:
        """The core schema rules, whatever the document declares."""
        return _RULES


def _refuse(path: str, file: str | None) -> TemplateInvalid:
    return TemplateInvalid("yaml_invalid", path, file)


def _parser() -> Any:
    yaml = YAML(typ="safe", pure=True)
    yaml.Resolver = _CoreResolver
    return yaml


def _check_events(yaml: Any, text: str, file: str | None) -> None:
    """Refuse aliases, anchors, tags, a second document and nesting past `MAX_DEPTH`, before any data is built."""
    depth = documents = 0
    for event in yaml.parse(text):
        if isinstance(event, NodeEvent) and (event.anchor is not None or getattr(event, "tag", None) is not None):
            raise _refuse("", file)  # an alias event carries its anchor
        if isinstance(event, DocumentStartEvent):
            documents += 1
        if isinstance(event, CollectionStartEvent):
            depth += 1
        elif isinstance(event, CollectionEndEvent):
            depth -= 1
        if depth > MAX_DEPTH or documents > 1:
            raise _refuse("", file)
    if documents == 0:
        raise _refuse("", file)


def _plain(node: object, path: str, file: str | None) -> JsonValue:
    """Check the built data: string keys only and finite numbers; `path` is the dotted key path, for the error."""
    if isinstance(node, dict):
        for key, value in node.items():
            if not isinstance(key, str):
                raise _refuse(path, file)
            _plain(value, f"{path}.{key}" if path else key, file)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _plain(item, f"{path}[{index}]", file)
    elif (isinstance(node, float) and not math.isfinite(node)) or not (
        node is None or isinstance(node, str | int | float | bool)
    ):
        raise _refuse(path, file)
    return node


def loads_strict(text: str, file: str | None = None) -> JsonValue:
    """Parse `text` as one YAML 1.2 document and return plain JSON data.

    Raises `TemplateInvalid` (`yaml_invalid`) for every case in the module docstring and for a syntax error; `file` is
    only the name carried by the error.
    """
    yaml = _parser()
    try:
        _check_events(yaml, text, file)
        data = yaml.load(text)
    except (YAMLError, ValueError) as error:  # ValueError: an integer with more digits than Python converts
        raise _refuse("", file) from error
    return _plain(data, "", file)


def load_strict(path: Path) -> JsonValue:
    """Read `path` (UTF-8, optional byte order mark, any line ending) with `loads_strict`.

    A file over `MAX_BYTES` or not valid UTF-8 is `yaml_invalid`, a missing file is `not_found`; the file is not
    parsed when it is too large.
    """
    name = path.name
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
    except FileNotFoundError as error:
        raise TemplateInvalid("not_found", "", name) from error
    if len(raw) > MAX_BYTES:
        raise _refuse("", name)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise _refuse("", name) from error
    return loads_strict(text, name)
