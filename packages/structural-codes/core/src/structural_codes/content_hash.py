"""Content hash of a check and the lint scope of its helpers (spec 0001 sections 4.5 and 4.7).

Purpose: one SHA-256 over everything that decides a verdict: the sources of the static import closure (the check's
pack, `structural_codes`, `eng_contract`), the metadata, the input schema and the preconditions. An approval is bound
to this hash, so changing any of them withdraws the approval. Units: none.
Errors: `CheckDefinitionError` for a dynamic import in a module of the check's pack (AC22), an unresolvable or
unreadable import, or a malformed `base`; `CanonicalJsonError` if a document value is not canonical JSON.
"""

import hashlib
import re
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any

import eng_contract
from eng_contract.canonical import payload_sha256

from structural_codes._closure import import_closure, is_package
from structural_codes.check import Check
from structural_codes.errors import CheckDefinitionError
from structural_codes.overlay import InheritedCheck

__all__ = ["content_hash", "lint_scope_violations"]

_FORMAT = "structural-codes-content/1"
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _closure(check: Check) -> dict[str, str]:
    """The import closure of the check's module over its pack, `structural_codes` and `eng_contract`."""
    return import_closure(
        check.module, frozenset({check.meta.pack, "structural_codes", "eng_contract"}), frozenset({check.meta.pack})
    )


def _document(check: Check, base: str | None) -> dict[str, Any]:
    """Build the hashed document of spec 4.7; `members` is sorted because a set has no stable order."""
    model: Any = check.inputs  # a CheckInputs subclass, checked when the check is defined
    meta = check.meta.model_dump(mode="json")
    meta["members"] = sorted(meta["members"])
    return {
        "format": _FORMAT,
        "meta": meta,
        "inputs_schema": model.model_json_schema(),
        "preconditions": [{"id": p.id, "outcome": p.outcome.value, "clause": p.clause} for p in check.preconditions],
        "modules": {name: hashlib.sha256(text.encode("utf-8")).hexdigest() for name, text in _closure(check).items()},
        "eng_contract": eng_contract.__version__,
        "base": base,
    }


def content_hash(check: Check, *, base: str | None = None) -> str:
    """Return the lower-case hex SHA-256 of the check's content document (spec 4.7).

    `base` is the content hash of the base check of an inherited overlay entry, or `None`; an `InheritedCheck` takes
    the hash of its own base check when none is given (AC18). Sources are LF-normalized,
    so line endings do not change the hash; a pack module that the check does not import does not either.

    Raises:
        CheckDefinitionError: `base` is not 64 lower-case hex digits, or the closure is invalid (AC22).
    """
    if base is not None and not _SHA256.fullmatch(base):
        raise CheckDefinitionError(f"base content hash must be 64 lower-case hex digits, got {base!r}")
    if base is None and isinstance(check, InheritedCheck):
        base = content_hash(check.base)
    return payload_sha256(_document(check, base))


def lint_scope_violations(check: Check, check_modules: Iterable[str]) -> tuple[str, ...]:
    """Return the dotted names of the pack modules in the check's closure that match none of `check_modules`.

    Each module's path is taken as `src/<dotted name as path>.py` (`<...>/__init__.py` for a package), relative to
    the pack project root, and matched with `PurePosixPath.full_match`; the result is sorted by name (AC22a).

    Raises:
        CheckDefinitionError: the closure is invalid (see `content_hash`).
    """
    globs = tuple(check_modules)
    violations: list[str] = []
    for name in _closure(check):
        if name.partition(".")[0] != check.meta.pack:
            continue
        parts = [*name.split(".")]
        path = (
            PurePosixPath("src", *parts, "__init__.py")
            if is_package(name)
            else PurePosixPath("src", *parts[:-1], f"{parts[-1]}.py")
        )
        if not any(path.full_match(glob) for glob in globs):
            violations.append(name)
    return tuple(violations)
