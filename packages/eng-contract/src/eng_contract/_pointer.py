"""JSON Pointer, string representation of RFC 6901 (spec 4.6.1). Internal; public as `refs.JsonPointer`.

Purpose: parse, format and evaluate pointers into a JSON document; there is no percent-decoding.
Errors: `ContractError` with code `REF_POINTER_INVALID`, `field` and the failing token in `received`.
"""

import re

from pydantic import JsonValue

from eng_contract.errors import ContractError, ErrorCode

_BAD_ESCAPE = re.compile(r"~(?![01])")
_INDEX = re.compile(r"0|[1-9][0-9]*")
_MAX_INDEX_DIGITS = 18


def _invalid(message: str, field: str | None, token: str) -> ContractError:
    return ContractError(ErrorCode.REF_POINTER_INVALID, message, field=field, received=token)


class JsonPointer:
    """Namespace of the RFC 6901 operations on token tuples."""

    @staticmethod
    def parse(text: str, field: str | None = None) -> tuple[str, ...]:
        """Split a pointer into unescaped tokens; the empty text is the whole document (no tokens).

        Raises:
            ContractError: `REF_POINTER_INVALID` when `text` does not start with `/` or has a `~` not followed by
                `0` or `1`.
        """
        if text == "":
            return ()
        if not text.startswith("/"):
            raise _invalid("a pointer must be empty or start with '/'", field, text)
        if _BAD_ESCAPE.search(text):
            raise _invalid("'~' must be followed by '0' or '1'", field, text)
        return tuple(token.replace("~1", "/").replace("~0", "~") for token in text[1:].split("/"))

    @staticmethod
    def format(tokens: tuple[str, ...]) -> str:
        """Escape (`~` to `~0`, then `/` to `~1`) and join tokens; no tokens give the empty pointer."""
        return "".join("/" + token.replace("~", "~0").replace("/", "~1") for token in tokens)

    @staticmethod
    def evaluate(document: JsonValue, tokens: tuple[str, ...], field: str | None = None) -> JsonValue:
        """Return the value the tokens address (RFC 6901 section 4).

        Raises:
            ContractError: `REF_POINTER_INVALID` for a missing member, an array token that is not `0` or a number
                without a leading zero, an index past the end (`-` included), or a token applied to a scalar.
        """
        node = document
        for token in tokens:
            if isinstance(node, dict):
                if token not in node:
                    raise _invalid("no such member", field, token)
                node = node[token]
            elif isinstance(node, list):
                if not _INDEX.fullmatch(token):
                    raise _invalid("not an array index", field, token)
                if len(token) > _MAX_INDEX_DIGITS or int(token) >= len(node):
                    raise _invalid("array index out of range", field, token)
                node = node[int(token)]
            else:
                raise _invalid("token applied to a scalar", field, token)
        return node
