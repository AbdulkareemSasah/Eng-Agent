"""Access to a frozen design basis through the contract result store (spec 0004 section 4.7, AC25).

Purpose: `StoreBasisPort` implements the engine `BasisPort`: it resolves the reference, checks the kind and the payload
hash and returns `LoadedBasis`. Nothing is rewritten; a basis changes only by a new result.
Errors: `BasisInvalid` with reason `not_a_basis` (another kind or an invalid payload), `not_found` (malformed or
unknown reference, or one that points inside the payload) or `hash_mismatch` (stored bytes damaged or not matching
`payload_sha256`).
"""

from eng_contract.errors import ContractError
from eng_contract.kinds.basis import DesignBasis
from eng_contract.refs import parse_ref
from eng_contract.store import ResultStore, StoreIntegrityError
from pydantic import ValidationError

from eng_harness.basis._fields import BasisInvalid
from eng_harness.basis._freeze import KIND
from eng_harness.ports import LoadedBasis


class StoreBasisPort:
    """The engine `BasisPort` over a `ResultStore`."""

    def __init__(self, store: ResultStore) -> None:
        """Read bases from `store`."""
        self._store = store

    def load(self, basis_ref: str) -> LoadedBasis:
        """Load the `basis.design_basis/1` result named by `basis_ref` (a whole-result reference)."""
        try:
            result_id, tokens = parse_ref(basis_ref)
            if tokens:
                raise BasisInvalid("not_found", basis_ref[:200])
            record = self._store.get(result_id)
            if record.kind != KIND:
                raise BasisInvalid("not_a_basis", result_id)
            payload = self._store.payload(result_id)
        except StoreIntegrityError as error:
            raise BasisInvalid("hash_mismatch", basis_ref[:200]) from error
        except BasisInvalid:
            raise
        except ContractError as error:
            raise BasisInvalid("not_found", basis_ref[:200]) from error
        try:
            basis = DesignBasis.model_validate(payload)
        except ValidationError as error:
            raise BasisInvalid("not_a_basis", result_id) from error
        return LoadedBasis(result_id=result_id, basis=basis)
