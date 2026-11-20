"""Unit tests for RevitReconciler helpers (plan 0011 T10; spec 0011 §4.10).

No host process: HostRead is a stub. Covers combine, open_model, bound-document, setters,
duplicate and change_element_type branches that workflow faults do not hit alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.errors import ContractError, ErrorCode
from pydantic import JsonValue

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._toolport import Binding, LostWrite
from eng_harness.adapters.revit import revit_allowlist
from eng_harness.adapters.revit._reconcile import RevitReconciler, _host_args
from eng_harness.adapters.revit._tools import (
    ChangeElementTypeArgs,
    DuplicateFamilyTypeArgs,
    OpenModelArgs,
    SetElementParameterValuesArgs,
)
from eng_harness.servers import CallEffect

BOUND = Path(r"C:\models\edits.rvt")


def _desc(name: str) -> Any:
    return revit_allowlist(role="write").descriptor(name)


def _lost(tool: str, model: Any, *, known: bool = True, pre_image: JsonValue = None) -> LostWrite:
    return LostWrite(
        _desc(tool),
        model,
        Binding(target=HostTarget(product="revit", pid=7), owned=True),
        known,
        pre_image,
    )


def test_combine_outcomes() -> None:
    combine = RevitReconciler._combine
    assert combine(()) == "unknown"
    assert combine(("applied",)) == "applied"
    assert combine(("not_applied", "not_applied")) == "not_applied"
    assert combine(("applied", "not_applied")) == "partial"
    assert combine(("applied", "unknown")) == "unknown"
    assert combine(("not_applied", "unknown")) == "unknown"


def test_host_args_setters_and_open() -> None:
    setter = SetElementParameterValuesArgs(
        element_ids=[1], parameter_name="b", value="450", value_type="double"
    )
    assert _host_args(setter)["parameterName"] == "b"
    open_args = OpenModelArgs(path=str(BOUND))
    assert _host_args(open_args) == {"path": str(BOUND), "activate": True}
    with pytest.raises(TypeError):
        _host_args(object())


def test_open_model_path_rules() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
        calls: list[str] = []

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            calls.append(tool)
            assert effect is CallEffect.READ
            return {"path": str(BOUND), "active_path": str(BOUND)}

        applied = await reconciler.decide(
            _lost("revit_open_model", OpenModelArgs(path=str(BOUND))),
            read,
        )
        assert applied.outcome == "applied"
        other = await reconciler.decide(
            _lost("revit_open_model", OpenModelArgs(path=r"C:\models\copy.rvt")),
            read,
        )
        assert other.outcome == "not_applied"

    anyio.run(body)


def test_active_document_not_bound_is_unknown() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return {"path": r"C:\models\other.rvt", "active_path": r"C:\models\other.rvt"}

        found = await reconciler.decide(
            _lost(
                "revit_set_element_parameter_values",
                SetElementParameterValuesArgs(
                    element_ids=[3001], parameter_name="b", value="450", value_type="double"
                ),
            ),
            read,
        )
        assert found.outcome == "unknown"
        assert found.evidence["reason"] == "active document is not the bound document"

    anyio.run(body)


def test_duplicate_absent_and_present_branches() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
        model = DuplicateFamilyTypeArgs(source_type_id="2001", new_type_name="C450x450")
        state: dict[str, Any] = {"items": []}

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return {"path": str(BOUND), "active_path": str(BOUND)}
            if tool == "revit_list_family_types_in_family":
                return {"items": list(state["items"])}
            if tool == "revit_get_type_parameters":
                return {"items": [{"parameters": [{"name": "b", "rawValue": 1.0, "specId": "x"}]}]}
            raise AssertionError(tool)

        not_applied = await reconciler.decide(_lost("revit_duplicate_family_type", model, pre_image=None), read)
        assert not_applied.outcome == "not_applied"

        state["items"] = [{"name": "C450x450", "type_id": 2100}]
        applied = await reconciler.decide(_lost("revit_duplicate_family_type", model, pre_image=None), read)
        assert applied.outcome == "applied"
        assert applied.evidence["observed"]["type_id"] == 2100

        unknown = await reconciler.decide(
            _lost("revit_duplicate_family_type", model, pre_image={"name": "C450x450"}),
            read,
        )
        assert unknown.outcome == "unknown"

        no_pre = await reconciler.decide(
            _lost("revit_duplicate_family_type", model, known=False, pre_image=None),
            read,
        )
        assert no_pre.outcome == "unknown"

    anyio.run(body)


def test_change_type_partial_and_unknown_missing() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(
            tolerance_ratio=0.001,
            bound_path=BOUND,
            unique_ids={3001: "col-3001", 3002: "col-3002"},
        )
        model = ChangeElementTypeArgs(element_ids=[3001, 3002], type_id=2002)
        details: dict[int, dict[str, Any]] = {
            3001: {"unique_id": "col-3001", "type_id": 2002},
            3002: {"unique_id": "col-3002", "type_id": 2001},
        }

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return {"path": str(BOUND), "active_path": str(BOUND)}
            if tool == "revit_get_element_details":
                eid = int(arguments["elementIds"][0])
                row = details.get(eid)
                if row is None:
                    raise ContractError(ErrorCode.NOT_FOUND, "element was not found")
                return {"items": [row]}
            raise AssertionError(tool)

        partial = await reconciler.decide(
            _lost("revit_change_element_type", model, pre_image={"type_id": 2001}),
            read,
        )
        assert partial.outcome == "partial"
        assert partial.missing == ("col-3002",)

        details.pop(3001)
        unknown = await reconciler.decide(
            _lost(
                "revit_change_element_type",
                ChangeElementTypeArgs(element_ids=[3001], type_id=2002),
                pre_image={"type_id": 2001},
            ),
            read,
        )
        assert unknown.outcome == "unknown"

    anyio.run(body)


def test_observe_open_and_setter() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return {"path": str(BOUND)}
            if tool == "revit_get_element_parameters":
                return {
                    "items": [
                        {
                            "parameters": [
                                {
                                    "name": "b",
                                    "rawValue": 1.4763779527559055,
                                    "specId": "autodesk.spec.aec:length-2.0.0",
                                    "storageType": "Double",
                                }
                            ]
                        }
                    ]
                }
            raise AssertionError(tool)

        open_obs = await reconciler.observe(_lost("revit_open_model", OpenModelArgs(path=str(BOUND))), read)
        assert open_obs == {"observed": {"path": str(BOUND)}}

        setter = SetElementParameterValuesArgs(
            element_ids=[3001], parameter_name="b", value="450", value_type="double"
        )
        lost = _lost("revit_set_element_parameter_values", setter)
        observed = await reconciler.observe(lost, read)
        assert observed is not None
        assert "observed" in observed

    anyio.run(body)


def test_setter_applied_when_request_matches() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(
            tolerance_ratio=0.001, bound_path=BOUND, unique_ids={3001: "col-3001"}
        )
        # 450 mm in feet (spec §4.6 rawValue).
        feet = 450.0 / 304.8

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return {"path": str(BOUND), "active_path": str(BOUND)}
            if tool == "revit_get_element_parameters":
                return {
                    "items": [
                        {
                            "parameters": [
                                {
                                    "name": "b",
                                    "rawValue": feet,
                                    "specId": "autodesk.spec.aec:length-2.0.0",
                                    "storageType": "Double",
                                }
                            ]
                        }
                    ]
                }
            raise AssertionError(tool)

        found = await reconciler.decide(
            _lost(
                "revit_set_element_parameter_values",
                SetElementParameterValuesArgs(
                    element_ids=[3001], parameter_name="b", value="450", value_type="double"
                ),
                pre_image={"b": 304.8},
            ),
            read,
        )
        assert found.outcome == "applied"

    anyio.run(body)
