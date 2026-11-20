"""Internal shared string types (spec 4.2.1). Imports nothing from this package."""

from typing import Annotated

from pydantic import StringConstraints

FieldPath = Annotated[
    str,
    StringConstraints(
        max_length=512,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*|\[(0|[1-9][0-9]*)\])*$",
    ),
]
"""Name of an input field: `name ( "." name | "[" index "]" )*`."""

Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
"""Lower-case hexadecimal SHA-256 digest."""

KindName = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+/[1-9][0-9]{0,3}$"),
]
"""Result kind name with version, for example `model.info/1` (spec 4.10.1)."""
