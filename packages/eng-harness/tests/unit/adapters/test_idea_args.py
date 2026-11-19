"""IDEA argument models: confirm under approval and design code from the basis only (plan 0014 T3; spec 0014 AC4, AC15)."""

import pytest
from eng_contract.errors import ContractError, ErrorCode


def test_confirm_only_under_approval() -> None:
    """AC4: confirm: true is set only under an approval for tools that require it; save stays false."""
    from eng_harness.adapters.idea import idea_allowlist
    from eng_harness.adapters.idea import _tools as idea_tools

    allowlist = idea_allowlist()
    assert allowlist.descriptor("idea_calculate").confirm == "approved"
    assert allowlist.descriptor("idea_native_set_loads").confirm == "approved"
    assert allowlist.descriptor("idea_native_calculate").confirm == "never"

    approved = idea_tools.build_calculate_args(connection_ids=[1, 2], approved=True)
    assert approved == {"connection_ids": [1, 2], "confirm": True}

    refused = idea_tools.build_calculate_args(connection_ids=[1], approved=False)
    assert refused == {"connection_ids": [1]}
    assert "confirm" not in refused

    with pytest.raises(ContractError) as missing:
        idea_tools.build_calculate_args(connection_ids=None, approved=True)
    assert missing.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert missing.value.detail.field == "connection_ids"

    loads = idea_tools.build_native_set_loads_args(
        path="/run/a.ideaCon",
        loads=[{"name": "LC1", "forcesOnSegments": []}],
        connection_id="C1",
        out_path="/run/b.ideaCon",
        approved=True,
    )
    assert loads["confirm"] is True
    assert loads["path"] == "/run/a.ideaCon"
    assert loads["out_path"] == "/run/b.ideaCon"
    assert loads["path"] != loads["out_path"]

    without = idea_tools.build_native_set_loads_args(
        path="/run/a.ideaCon",
        loads=[{"name": "LC1", "forcesOnSegments": []}],
        connection_id="C1",
        out_path="/run/b.ideaCon",
        approved=False,
    )
    assert "confirm" not in without

    native = idea_tools.build_native_calculate_args(path="/run/a.ideaCon", connection_id="C1")
    assert native == {"path": "/run/a.ideaCon", "connection_id": "C1", "save": False}
    assert "out_path" not in native
    assert "confirm" not in native


def test_design_code_from_basis_only() -> None:
    """AC15: the design code is taken from the basis field only; the server default ECEN is never used."""
    from eng_harness.adapters.idea import _tools as idea_tools

    assert idea_tools.design_code_from_basis({"connection.design_code": "AISC"}) == "AISC"

    with pytest.raises(ContractError) as missing:
        idea_tools.design_code_from_basis({})
    assert missing.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert missing.value.detail.field == "connection.design_code"
    assert "ECEN" not in missing.value.detail.message

    with pytest.raises(ContractError) as blank:
        idea_tools.design_code_from_basis({"connection.design_code": "  "})
    assert blank.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert blank.value.detail.field == "connection.design_code"

    for built in (
        idea_tools.build_calculate_args(connection_ids=[1], approved=True),
        idea_tools.build_native_calculate_args(path="/run/a.ideaCon"),
        idea_tools.build_native_set_loads_args(
            path="/run/a.ideaCon",
            loads=[],
            connection_id="C1",
            out_path="/run/b.ideaCon",
            approved=True,
        ),
        idea_tools.build_status_args(),
    ):
        assert "design_code" not in built
