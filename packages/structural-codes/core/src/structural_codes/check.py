"""The `@check` decorator and the `Check` it builds (spec 0001 sections 4.4 and 4.6).

Purpose: wrap a check body with its metadata, input model and declared preconditions, and enforce at definition
that every check makes a reviewed applicability decision (AC5b).
Errors: `CheckDefinitionError` for any wrong definition.
"""

from collections.abc import Callable
from dataclasses import dataclass

from structural_codes.applicability import Precondition
from structural_codes.errors import CheckDefinitionError
from structural_codes.inputs import check_inputs_definition
from structural_codes.meta import CheckMeta

__all__ = ["Check", "check"]

Body = Callable[..., None]


@dataclass(frozen=True, slots=True)
class Check:
    """A defined check: metadata, input model, ordered preconditions, body and the body's module name."""

    meta: CheckMeta
    inputs: type
    preconditions: tuple[Precondition, ...]
    body: Body
    module: str


def check(*, meta: CheckMeta, inputs: type, preconditions: tuple[Precondition, ...]) -> Callable[[Body], Check]:
    """Return the decorator that turns a body `def body(inp, t) -> None` into a `Check`.

    Raises:
        CheckDefinitionError: `inputs` breaks the input rules (AC3), a precondition is not a `Precondition` or its
            id is repeated, or the applicability declaration is wrong: an empty `preconditions` needs
            `meta.unconditional`, and a non-empty one must not have it (AC5b).
    """
    check_inputs_definition(inputs)
    if not all(isinstance(p, Precondition) for p in preconditions):
        raise CheckDefinitionError(f"{meta.check_id}: preconditions must be Precondition objects")
    ids = [p.id for p in preconditions]
    if len(set(ids)) != len(ids):
        raise CheckDefinitionError(f"{meta.check_id}: a precondition id is declared twice")
    if not preconditions and meta.unconditional is None:
        raise CheckDefinitionError(f"{meta.check_id}: declare preconditions or set CheckMeta.unconditional")
    if preconditions and meta.unconditional is not None:
        raise CheckDefinitionError(f"{meta.check_id}: both preconditions and unconditional are declared")

    def decorate(body: Body) -> Check:
        return Check(meta=meta, inputs=inputs, preconditions=tuple(preconditions), body=body, module=body.__module__)

    return decorate
