"""SBC 304-2018 overlay pack of the structural-codes folder (plan 0003).

Purpose: version constant, `PACK`, `check_id_for` and the public map types. Every shipped row is unconfirmed and
returns `NEEDS_ENGINEER` until the owner confirms it against SBC 304-2018 text.
"""

from typing import cast

from aci318_14 import PACK as _BASE_PACK
from eng_contract.errors import ContractError, ErrorCode
from structural_codes.meta import clause_token
from structural_codes.overlay import Inherited, Overlay, Overridden
from structural_codes.pack import Pack

from sbc304_2018._overlay import GapReason as GapReason
from sbc304_2018._overlay import MapRow as MapRow
from sbc304_2018._overlay import MapStatus as MapStatus
from sbc304_2018._overlay import build_overlay
from sbc304_2018.clause_map import CLAUSE_MAP as CLAUSE_MAP

__version__ = "0.1.0.dev0"

# `PACK` stays out of `__all__` because tests/unit/test_package.py (T1, outside T3's files) asserts the list.
# Public names of spec 0003 §5 remain importable: PACK, check_id_for, GapReason, MapRow, MapStatus, CLAUSE_MAP.
__all__ = ["__version__"]

_CHECKS, _OVERLAY = build_overlay(CLAUSE_MAP, _BASE_PACK)

PACK = Pack(
    "sbc304_2018",
    "SBC 304-2018",
    "2018",
    __version__,
    checks=_CHECKS,
    approvals="approvals.yaml",
    base="aci318_14",
    overlay=_OVERLAY,
)


def check_id_for(base_check_id: str) -> str:
    """Return the overlay check id for a base ACI check id (spec 0003 AC9).

    Raises:
        ContractError: code `NOT_FOUND`, field `base_check_id`, when the id has no overlay entry.
    """
    overlay = cast("Overlay", PACK.overlay)
    for entry in overlay.entries:
        if isinstance(entry, Overridden) and entry.base_check_id == base_check_id:
            return entry.check.meta.check_id
        if isinstance(entry, Inherited) and entry.base_check_id == base_check_id:
            if entry.short_name is not None:
                short = entry.short_name
            else:
                _, _, short = base_check_id.rpartition(".")
            return f"{PACK.name}.{clause_token(entry.clause)}.{short}"
    raise ContractError(
        ErrorCode.NOT_FOUND,
        f"no overlay check for base check id {base_check_id!r}",
        field="base_check_id",
    )
