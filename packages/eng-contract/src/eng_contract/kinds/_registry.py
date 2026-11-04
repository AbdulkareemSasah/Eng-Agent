"""The kind registry (spec 4.10.1): an immutable mapping from kind name to payload model.

Purpose: let consumers look up the payload model of a stored result by its kind name.
Errors: `KindNotRegistered` (code `INVALID_ARGUMENT`) for an unknown or malformed name on lookup;
`ContractDefinitionError` when `extend` is given a bad name, a neutral family or a duplicate (programming errors).
"""

from collections.abc import Iterator, Mapping
from types import MappingProxyType

from pydantic import BaseModel, TypeAdapter, ValidationError

from eng_contract._types import KindName
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import ContractDefinitionError

NEUTRAL_FAMILIES = frozenset({"geom", "model", "forces", "basis", "verdicts", "issues"})
"""Kind families reserved for this package (spec 4.10.1)."""
_NAME = TypeAdapter(KindName)


class KindNotRegistered(ContractError, KeyError):  # noqa: N818  # B-020: the name is fixed by spec 4.10.1
    """A kind name that the registry does not hold; code `INVALID_ARGUMENT`."""

    def __init__(self, kind: str) -> None:
        """Build the error for `kind`."""
        super().__init__(ErrorCode.INVALID_ARGUMENT, f"kind {kind!r} is not registered", received=kind)


def _checked(name: str) -> str:
    try:
        return _NAME.validate_python(name)
    except ValidationError as exc:
        raise ContractDefinitionError(f"{name!r} is not a kind name (family.name/version)") from exc


class KindRegistry(Mapping[str, type[BaseModel]]):
    """Immutable `KindName -> type[BaseModel]` mapping; there is no global registration."""

    def __init__(self, kinds: Mapping[str, type[BaseModel]]) -> None:
        """Hold `kinds`; every key must be a valid kind name."""
        self._kinds = MappingProxyType({_checked(name): model for name, model in kinds.items()})

    def __getitem__(self, kind: str) -> type[BaseModel]:
        """Return the payload model of `kind`.

        Raises:
            KindNotRegistered: `kind` is not registered (a malformed name is never registered).
        """
        try:
            return self._kinds[kind]
        except KeyError:
            raise KindNotRegistered(kind) from None

    def __iter__(self) -> Iterator[str]:
        """Iterate the registered kind names."""
        return iter(self._kinds)

    def __len__(self) -> int:
        """Number of registered kinds."""
        return len(self._kinds)

    def extend(self, mapping: Mapping[str, type[BaseModel]]) -> KindRegistry:
        """Return a new registry with `mapping` added; this registry is unchanged.

        Raises:
            ContractDefinitionError: a name is malformed, is in a neutral family, or is already registered.
        """
        for name in mapping:
            if _checked(name).split(".", 1)[0] in NEUTRAL_FAMILIES:
                raise ContractDefinitionError(f"{name!r} is in a family reserved for eng-contract")
            if name in self._kinds:
                raise ContractDefinitionError(f"kind {name!r} is already registered")
        return KindRegistry({**self._kinds, **mapping})
