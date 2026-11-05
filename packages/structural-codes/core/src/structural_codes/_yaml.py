"""The one place that reads YAML (package ADR-0001): `yaml.safe_load` only, duplicate keys rejected.

Errors: the exception class the caller passes, for a syntax error, an unsafe tag or a repeated mapping key.
"""

from typing import Any

import yaml

__all__ = ["load_yaml"]


def _reject_duplicates(node: yaml.Node | None, error: type[Exception], seen: set[int]) -> None:
    """Raise `error` when a mapping below `node` repeats a key (YAML itself keeps the last value silently)."""
    if node is None or id(node) in seen:
        return
    seen.add(id(node))
    if isinstance(node, yaml.MappingNode):
        keys: set[str] = set()
        for key, value in node.value:
            if isinstance(key, yaml.ScalarNode):
                if key.value in keys:
                    raise error(f"duplicate key {key.value!r} at line {key.start_mark.line + 1}")
                keys.add(key.value)
            _reject_duplicates(value, error, seen)
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            _reject_duplicates(item, error, seen)


def load_yaml(text: str, error: type[Exception]) -> Any:
    """Parse one YAML document with `yaml.safe_load`; an empty text gives None. Raises `error` as stated above."""
    try:
        _reject_duplicates(yaml.compose(text, Loader=yaml.SafeLoader), error, set())
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise error(f"invalid YAML: {exc}") from exc
