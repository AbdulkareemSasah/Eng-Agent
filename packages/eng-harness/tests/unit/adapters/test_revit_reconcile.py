"""Unit tests for RevitReconciler helpers (plan 0011 T10; spec 0011 §4.10).

No host process: HostRead is a stub. Covers combine, open_model, bound-document, setters
(multi-target), duplicate (read failure, truncation, other parameters), and change_element_type
(None pre-image, per-element) branches that workflow faults do not hit alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import anyio
import pytest
from eng_contract.errors import ContractError, ErrorCode
from pydantic import JsonValue

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._toolport import Binding, LostWrite
from eng_harness.adapters.revit import revit_allowlist
from eng_harness.adapters.revit._reconcile import (
    _MAX_PAGES,
    _NO_PRE,
    _PAGE,
    RevitReconciler,
    _host_args,
)
from eng_harness.adapters.revit._tools import (
    ChangeElementTypeArgs,
    DuplicateFamilyTypeArgs,
    OpenModelArgs,
    SetElementParameterValuesArgs,
    SetParameterValueByGuidArgs,
    SetTypeParameterValuesArgs,
)
from eng_harness.servers import CallEffect

BOUND = Path(r"C:\models\edits.rvt")
FEET_450 = 450.0 / 304.8
FEET_300 = 300.0 / 304.8
FEET_400 = 400.0 / 304.8
LENGTH_SPEC = "autodesk.spec.aec:length-2.0.0"


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


def _param(raw: float, *, name: str = "b") -> dict[str, Any]:
    return {
        "name": name,
        "rawValue": raw,
        "specId": LENGTH_SPEC,
        "storageType": "Double",
    }


def _meta_bound() -> dict[str, Any]:
    return {"path": str(BOUND)}


def test_combine_outcomes() -> None:
    combine = RevitReconciler._combine
    assert combine(()) == "unknown"
    assert combine(("applied",)) == "applied"
    assert combine(("not_applied", "not_applied")) == "not_applied"
    assert combine(("applied", "not_applied")) == "partial"
    assert combine(("applied", "unknown")) == "unknown"
    assert combine(("not_applied", "unknown")) == "unknown"


def test_host_args_all_write_models() -> None:
    from eng_harness.adapters.revit._tools import (
        SetParameterValueByGuidArgs,
        SetTypeParameterValuesArgs,
    )

    setter = SetElementParameterValuesArgs(element_ids=[1], parameter_name="b", value="450", value_type="double")
    assert _host_args(setter) == {
        "elementIds": [1],
        "parameterName": "b",
        "value": "450",
        "valueType": "double",
    }
    typed = SetTypeParameterValuesArgs(
        parameter_name="b",
        value="450",
        value_type="double",
        type_ids=[2001],
        expected_instances=[3001],
        element_ids=[3001],
    )
    type_args = _host_args(typed)
    assert type_args == {
        "typeIds": [2001],
        "parameterName": "b",
        "value": "450",
        "valueType": "double",
        "elementIds": [3001],
    }
    assert "expected_instances" not in type_args
    assert "expectedInstances" not in type_args
    typed_no_elements = SetTypeParameterValuesArgs(
        parameter_name="b",
        value="450",
        value_type="double",
        type_ids=[2001],
        expected_instances=[3001],
        element_ids=None,
    )
    assert "elementIds" not in _host_args(typed_no_elements)
    guid = SetParameterValueByGuidArgs(
        element_ids=[3001],
        guid="11111111-1111-1111-1111-111111111111",
        value="450",
        value_type="double",
        unit="mm",
        target="type",  # non-default so dropping target= in _host_args is killed
        all_or_nothing=False,  # non-default so dropping all_or_nothing= is killed
    )
    guid_args = _host_args(guid)
    assert guid_args["elementIds"] == [3001]
    assert guid_args["guid"] == "11111111-1111-1111-1111-111111111111"
    assert guid_args["value"] == "450"
    assert guid_args["valueType"] == "double"
    assert guid_args["unit"] == "mm"
    assert guid_args["target"] == "type"
    assert guid_args["allOrNothing"] is False
    change = ChangeElementTypeArgs(element_ids=[3001], type_id=2002)
    assert _host_args(change) == {"elementIds": [3001], "typeId": 2002}
    dup = DuplicateFamilyTypeArgs(source_type_id="2001", new_type_name="C450x450")
    assert _host_args(dup) == {"source_type_id": "2001", "new_type_name": "C450x450"}
    open_args = OpenModelArgs(path=str(BOUND), activate=False)
    assert _host_args(open_args) == {"path": str(BOUND), "activate": False}
    with pytest.raises(TypeError):
        _host_args(cast(Any, object()))


def test_open_model_path_rules() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            assert effect is CallEffect.READ
            return {"path": str(BOUND)}

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


def test_open_model_without_activation_cannot_be_decided_from_active_path() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return {"path": str(BOUND)}

        found = await reconciler.decide(
            _lost("revit_open_model", OpenModelArgs(path=r"C:\models\background.rvt", activate=False)),
            read,
        )
        assert found.outcome == "unknown"
        assert found.evidence["activate"] is False

    anyio.run(body)


def test_active_document_not_bound_is_unknown() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return {"path": r"C:\models\other.rvt"}

        found = await reconciler.decide(
            _lost(
                "revit_set_element_parameter_values",
                SetElementParameterValuesArgs(element_ids=[3001], parameter_name="b", value="450", value_type="double"),
            ),
            read,
        )
        assert found.outcome == "unknown"
        assert found.evidence["reason"] == "active document is not the bound document"

    anyio.run(body)


def test_bound_none_is_unknown() -> None:
    """§4.10 always checks the bound document; a missing binding is unknown, never a skip."""

    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=None)

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return {"path": r"C:\other.rvt"}
            if tool == "revit_get_element_parameters":
                return {"items": [{"parameters": [_param(FEET_450)]}]}
            raise AssertionError(tool)

        found = await reconciler.decide(
            _lost(
                "revit_set_element_parameter_values",
                SetElementParameterValuesArgs(element_ids=[3001], parameter_name="b", value="450", value_type="double"),
            ),
            read,
        )
        assert found.outcome == "unknown"
        assert found.evidence["reason"] == "bound document is not known"

    anyio.run(body)


def test_duplicate_absent_and_present_branches() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
        model = DuplicateFamilyTypeArgs(source_type_id="2001", new_type_name="C450x450")
        source = {
            "name": "C300x300",
            "type_id": 2001,
            "family": "Concrete-Rectangular-Column",
            "family_id": 1001,
        }
        state: dict[str, Any] = {"types": [dict(source)], "params": {2001: [_param(1.0)]}}

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_list_family_types_in_family":
                family_id = arguments.get("family_id")
                family_name = arguments.get("family_name")
                rows = [
                    row
                    for row in state["types"]
                    if (family_id is None or str(row.get("family_id")) == family_id)
                    and (family_name is None or row.get("family") == family_name)
                ]
                return {"items": list(rows), "truncated": False}
            if tool == "revit_get_type_parameters":
                tid = int(arguments["typeIds"][0])
                return {"items": [{"id": tid, "parameters": list(state["params"].get(tid, []))}]}
            raise AssertionError(tool)

        not_applied = await reconciler.decide(_lost("revit_duplicate_family_type", model, pre_image=None), read)
        assert not_applied.outcome == "not_applied"

        state["types"].append(
            {
                "name": "C450x450",
                "type_id": 2100,
                "family": "Concrete-Rectangular-Column",
                "family_id": 1001,
            }
        )
        state["params"][2100] = [_param(1.0)]
        applied = await reconciler.decide(_lost("revit_duplicate_family_type", model, pre_image=None), read)
        assert applied.outcome == "applied"
        observed = cast(dict[str, Any], applied.evidence["observed"])
        assert observed["type_id"] == 2100

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


def test_duplicate_other_parameters_is_unknown() -> None:
    """AC21: type absent before, present after with parameters that differ from the source → unknown."""

    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
        model = DuplicateFamilyTypeArgs(source_type_id="2001", new_type_name="C450x450")
        types = [
            {
                "name": "C300x300",
                "type_id": 2001,
                "family": "Concrete-Rectangular-Column",
                "family_id": 1001,
            },
            {
                "name": "C450x450",
                "type_id": 2100,
                "family": "Concrete-Rectangular-Column",
                "family_id": 1001,
            },
        ]
        params = {2001: [_param(1.0)], 2100: [_param(2.0)]}  # differs from source

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_list_family_types_in_family":
                return {"items": list(types), "truncated": False}
            if tool == "revit_get_type_parameters":
                tid = int(arguments["typeIds"][0])
                return {"items": [{"id": tid, "parameters": list(params[tid])}]}
            raise AssertionError(tool)

        found = await reconciler.decide(_lost("revit_duplicate_family_type", model, pre_image=None), read)
        assert found.outcome == "unknown"
        assert found.evidence["reason"] == "type exists with other parameters"

    anyio.run(body)


def test_duplicate_read_failure_is_unknown() -> None:
    """A failed second read must not look like absence (§4.10 / module docstring)."""

    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
        model = DuplicateFamilyTypeArgs(source_type_id="2001", new_type_name="N")
        types = [
            {"name": "C300x300", "type_id": 2001, "family": "F", "family_id": 1},
            {"name": "N", "type_id": 55, "family": "F", "family_id": 1},
        ]

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_list_family_types_in_family":
                return {"items": list(types), "truncated": False}
            if tool == "revit_get_type_parameters":
                return {"items": []}  # present in list, parameters unreadable
            raise AssertionError(tool)

        found = await reconciler.decide(_lost("revit_duplicate_family_type", model, pre_image=None), read)
        assert found.outcome == "unknown"
        assert "reason" in found.evidence

    anyio.run(body)


def test_duplicate_truncated_list_is_unknown() -> None:
    """A truncated family list cannot prove absence (§4.10)."""

    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
        model = DuplicateFamilyTypeArgs(source_type_id="2001", new_type_name="N")

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_list_family_types_in_family":
                # Truncated with no rows: incomplete read, not a complete absence.
                return {"items": [], "truncated": True}
            raise AssertionError(tool)

        found = await reconciler.decide(_lost("revit_duplicate_family_type", model, pre_image=None), read)
        assert found.outcome == "unknown"

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
                return _meta_bound()
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


def test_change_type_none_pre_image_is_unknown() -> None:
    """§4.10: not_applied only when every element has its pre-image type; None pre-image → unknown."""

    async def body() -> None:
        reconciler = RevitReconciler(
            tolerance_ratio=0.001,
            bound_path=BOUND,
            unique_ids={3001: "u1"},
        )

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_get_element_details":
                return {"items": [{"unique_id": "u1", "type_id": 77}]}
            raise AssertionError(tool)

        found = await reconciler.decide(
            _lost(
                "revit_change_element_type",
                ChangeElementTypeArgs(element_ids=[3001], type_id=99),
                pre_image=None,
            ),
            read,
        )
        assert found.outcome == "unknown"

    anyio.run(body)


def test_change_type_per_element_pre_image() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(
            tolerance_ratio=0.001,
            bound_path=BOUND,
            unique_ids={1: "u1", 2: "u2"},
        )
        details = {
            1: {"unique_id": "u1", "type_id": 99},
            2: {"unique_id": "u2", "type_id": 77},
        }

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_get_element_details":
                eid = int(arguments["elementIds"][0])
                return {"items": [details[eid]]}
            raise AssertionError(tool)

        pre: JsonValue = {"by_element": {"1": {"type_id": 10}, "2": {"type_id": 77}}}
        found = await reconciler.decide(
            _lost(
                "revit_change_element_type",
                ChangeElementTypeArgs(element_ids=[1, 2], type_id=99),
                pre_image=pre,
            ),
            read,
        )
        assert found.outcome == "partial"
        assert found.missing == ("u2",)

    anyio.run(body)


def test_observe_open_and_setter() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return {"path": str(BOUND)}
            if tool == "revit_get_element_parameters":
                return {"items": [{"parameters": [_param(FEET_450)]}]}
            raise AssertionError(tool)

        open_obs = await reconciler.observe(_lost("revit_open_model", OpenModelArgs(path=str(BOUND))), read)
        assert open_obs == {"observed": {"path": str(BOUND)}}

        setter = SetElementParameterValuesArgs(element_ids=[3001], parameter_name="b", value="450", value_type="double")
        lost = _lost("revit_set_element_parameter_values", setter)
        observed = await reconciler.observe(lost, read)
        assert observed is not None
        assert "observed" in observed
        by_target = cast(dict[str, Any], observed["observed"])["by_target"]
        assert "3001" in by_target

    anyio.run(body)


def test_setter_applied_when_request_matches() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND, unique_ids={3001: "col-3001"})

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_get_element_parameters":
                return {"items": [{"parameters": [_param(FEET_450)]}]}
            raise AssertionError(tool)

        found = await reconciler.decide(
            _lost(
                "revit_set_element_parameter_values",
                SetElementParameterValuesArgs(element_ids=[3001], parameter_name="b", value="450", value_type="double"),
                pre_image={"b": 304.8},
            ),
            read,
        )
        assert found.outcome == "applied"

    anyio.run(body)


def test_setter_not_applied_and_unknown() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND, unique_ids={3001: "col-3001"})
        state = {"raw": FEET_300}

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_get_element_parameters":
                return {"items": [{"parameters": [_param(state["raw"])]}]}
            raise AssertionError(tool)

        setter = SetElementParameterValuesArgs(element_ids=[3001], parameter_name="b", value="450", value_type="double")
        pre: JsonValue = {"b": 300.0}
        not_applied = await reconciler.decide(
            _lost("revit_set_element_parameter_values", setter, pre_image=pre),
            read,
        )
        assert not_applied.outcome == "not_applied"

        state["raw"] = FEET_400
        unknown = await reconciler.decide(
            _lost("revit_set_element_parameter_values", setter, pre_image=pre),
            read,
        )
        assert unknown.outcome == "unknown"

    anyio.run(body)


def test_setter_multi_target_outcomes() -> None:
    """§4.10 setters: all / none / some / one unreadable (two or more element ids)."""

    async def body() -> None:
        reconciler = RevitReconciler(
            tolerance_ratio=0.001,
            bound_path=BOUND,
            unique_ids={3001: "col-3001", 3002: "col-3002"},
        )
        values = {3001: FEET_450, 3002: FEET_450}

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_get_element_parameters":
                eid = int(arguments["elementIds"][0])
                raw = values.get(eid)
                if raw is None:
                    raise KeyError("unreadable")
                return {"items": [{"parameters": [_param(raw)]}]}
            raise AssertionError(tool)

        setter = SetElementParameterValuesArgs(
            element_ids=[3001, 3002], parameter_name="b", value="450", value_type="double"
        )
        pre: JsonValue = {"b": 300.0}

        all_applied = await reconciler.decide(_lost("revit_set_element_parameter_values", setter, pre_image=pre), read)
        assert all_applied.outcome == "applied"
        assert all_applied.missing == ()

        values[3001] = FEET_300
        values[3002] = FEET_300
        none = await reconciler.decide(_lost("revit_set_element_parameter_values", setter, pre_image=pre), read)
        assert none.outcome == "not_applied"

        values[3001] = FEET_450
        values[3002] = FEET_300
        some = await reconciler.decide(_lost("revit_set_element_parameter_values", setter, pre_image=pre), read)
        assert some.outcome == "partial"
        assert some.missing == ("col-3002",)

        values[3002] = cast(Any, None)
        unreadable = await reconciler.decide(_lost("revit_set_element_parameter_values", setter, pre_image=pre), read)
        assert unreadable.outcome == "unknown"

    anyio.run(body)


def test_observe_open_model_non_str_path() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)

        async def meta_bad(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return {"path": 12}

        obs = await reconciler.observe(_lost("revit_open_model", OpenModelArgs(path=str(BOUND))), meta_bad)
        assert obs == {"observed": {"path": None}}

    anyio.run(body)


def test_open_model_unknown_when_path_missing() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return {"path": None}

        found = await reconciler.decide(
            _lost("revit_open_model", OpenModelArgs(path=str(BOUND))),
            read,
        )
        assert found.outcome == "unknown"

    anyio.run(body)


def test_observe_read_failure_returns_none() -> None:
    """Unreadable state must not be stored as a known absence."""

    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
        model = DuplicateFamilyTypeArgs(source_type_id="2001", new_type_name="N")
        types = [
            {"name": "C300x300", "type_id": 2001, "family": "F", "family_id": 1},
            {"name": "N", "type_id": 55, "family": "F", "family_id": 1},
        ]

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_list_family_types_in_family":
                return {"items": list(types), "truncated": False}
            if tool == "revit_get_type_parameters":
                return {"items": []}
            raise AssertionError(tool)

        obs = await reconciler.observe(_lost("revit_duplicate_family_type", model), read)
        assert obs is None

    anyio.run(body)


def test_observe_duplicate_and_change_type_exact() -> None:
    """Pin observe payload keys so string/cast mutants on those paths die."""

    async def body() -> None:
        reconciler = RevitReconciler(
            tolerance_ratio=0.001,
            bound_path=BOUND,
            unique_ids={3001: "col-3001"},
        )
        types = [
            {"name": "C300x300", "type_id": 2001, "family": "F", "family_id": 1},
            {"name": "C450x450", "type_id": 2100, "family": "F", "family_id": 1},
        ]

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            assert effect is CallEffect.READ
            if tool == "revit_list_family_types_in_family":
                assert arguments.get("start_index") == 0
                assert arguments.get("max_types") == 100
                family_id = arguments.get("family_id")
                rows = [r for r in types if family_id is None or str(r.get("family_id")) == family_id]
                return {"items": rows, "truncated": False}
            if tool == "revit_get_type_parameters":
                return {"items": [{"id": int(arguments["typeIds"][0]), "parameters": [_param(1.0)]}]}
            if tool == "revit_get_element_details":
                return {"items": [{"unique_id": "col-3001", "type_id": 2001}]}
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            raise AssertionError(tool)

        dup_model = DuplicateFamilyTypeArgs(source_type_id="2001", new_type_name="C450x450")
        dup = await reconciler.observe(_lost("revit_duplicate_family_type", dup_model), read)
        assert dup == {
            "observed": {"name": "C450x450", "type_id": 2100, "parameters_present": True},
        }

        change = await reconciler.observe(
            _lost("revit_change_element_type", ChangeElementTypeArgs(element_ids=[3001], type_id=2002)),
            read,
        )
        assert change == {"observed": {"by_element": {"3001": {"type_id": 2001}}}}

    anyio.run(body)


def test_open_model_evidence_keys() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return {"path": str(BOUND)}

        found = await reconciler.decide(_lost("revit_open_model", OpenModelArgs(path=str(BOUND))), read)
        assert found.outcome == "applied"
        assert found.evidence["requested"] == {"path": str(BOUND)}
        assert found.evidence["observed"] == {"path": str(BOUND)}
        assert found.evidence["path"] == str(BOUND)
        assert found.evidence["pre_image_known"] is True

    anyio.run(body)


def test_active_not_bound_evidence_keys() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return {"path": r"C:\models\other.rvt"}

        found = await reconciler.decide(
            _lost(
                "revit_set_element_parameter_values",
                SetElementParameterValuesArgs(element_ids=[3001], parameter_name="b", value="450", value_type="double"),
            ),
            read,
        )
        assert found.outcome == "unknown"
        assert found.evidence["reason"] == "active document is not the bound document"
        assert found.evidence["path"] == r"C:\models\other.rvt"
        assert found.evidence["bound"] == str(BOUND)

    anyio.run(body)


def test_as_int_via_string_type_id() -> None:
    """_as_int accepts numeric strings from the host list (kills bool/None operator mutants)."""

    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
        model = DuplicateFamilyTypeArgs(source_type_id="2001", new_type_name="C450x450")
        types = [
            {"name": "C300x300", "type_id": "2001", "family": "F", "family_id": 1},
            {"name": "C450x450", "type_id": "2100", "family": "F", "family_id": 1},
        ]

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_list_family_types_in_family":
                return {"items": list(types), "truncated": False}
            if tool == "revit_get_type_parameters":
                return {"items": [{"id": int(arguments["typeIds"][0]), "parameters": [_param(1.0)]}]}
            raise AssertionError(tool)

        found = await reconciler.decide(_lost("revit_duplicate_family_type", model, pre_image=None), read)
        assert found.outcome == "applied"
        assert cast(dict[str, Any], found.evidence["observed"])["type_id"] == 2100

    anyio.run(body)


def test_list_family_types_pages_until_complete() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
        model = DuplicateFamilyTypeArgs(source_type_id="2001", new_type_name="N")
        pages = {
            0: {
                "items": [{"name": "C300x300", "type_id": 2001, "family": "F", "family_id": 1}],
                "truncated": True,
            },
            1: {
                "items": [{"name": "N", "type_id": 55, "family": "F", "family_id": 1}],
                "truncated": False,
            },
        }

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_list_family_types_in_family":
                start = int(arguments.get("start_index") or 0)
                # Unfiltered source lookup pages; family-scoped name lookup uses page 0 only after family known.
                if arguments.get("family_id") == "1":
                    return {"items": pages[1]["items"], "truncated": False}
                return pages[start]
            if tool == "revit_get_type_parameters":
                tid = int(arguments["typeIds"][0])
                return {"items": [{"id": tid, "parameters": [_param(1.0)]}]}
            raise AssertionError(tool)

        found = await reconciler.decide(_lost("revit_duplicate_family_type", model, pre_image=None), read)
        assert found.outcome == "applied"

    anyio.run(body)


def test_duplicate_scoped_to_source_family() -> None:
    """Same name in another family must not count as present (§4.10 exists in the family)."""

    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
        model = DuplicateFamilyTypeArgs(source_type_id="2001", new_type_name="N")
        types = [
            {"name": "C300x300", "type_id": 2001, "family": "F", "family_id": 1},
            {"name": "N", "type_id": 99, "family": "Other", "family_id": 2},
        ]

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_list_family_types_in_family":
                family_id = arguments.get("family_id")
                family_name = arguments.get("family_name")
                rows = [
                    row
                    for row in types
                    if (family_id is None or str(row.get("family_id")) == family_id)
                    and (family_name is None or row.get("family") == family_name)
                ]
                return {"items": rows, "truncated": False}
            raise AssertionError(tool)

        found = await reconciler.decide(_lost("revit_duplicate_family_type", model, pre_image=None), read)
        assert found.outcome == "not_applied"

    anyio.run(body)


def test_setter_by_target_pre_image() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(
            tolerance_ratio=0.001,
            bound_path=BOUND,
            unique_ids={3001: "col-3001", 3002: "col-3002"},
        )
        values = {3001: FEET_300, 3002: FEET_450}

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_get_element_parameters":
                eid = int(arguments["elementIds"][0])
                return {"items": [{"parameters": [_param(values[eid])]}]}
            raise AssertionError(tool)

        pre: JsonValue = {"by_target": {"3001": {"b": 300.0}, "3002": {"b": 300.0}}}
        found = await reconciler.decide(
            _lost(
                "revit_set_element_parameter_values",
                SetElementParameterValuesArgs(
                    element_ids=[3001, 3002], parameter_name="b", value="450", value_type="double"
                ),
                pre_image=pre,
            ),
            read,
        )
        assert found.outcome == "partial"
        assert found.missing == ("col-3001",)
        assert found.evidence["requested"] == {"b": 450.0}
        assert "3001" in cast(dict[str, Any], found.evidence["observed"])
        assert "3002" in cast(dict[str, Any], found.evidence["observed"])

    anyio.run(body)


def test_setter_truncated_reply_is_unknown() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND, unique_ids={3001: "col-3001"})

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_get_element_parameters":
                return {"items": [{"parameters": [_param(FEET_450)]}], "truncated": True}
            raise AssertionError(tool)

        found = await reconciler.decide(
            _lost(
                "revit_set_element_parameter_values",
                SetElementParameterValuesArgs(element_ids=[3001], parameter_name="b", value="450", value_type="double"),
                pre_image={"b": 300.0},
            ),
            read,
        )
        assert found.outcome == "unknown"
        assert cast(dict[str, Any], found.evidence["observed"])["3001"] is None

    anyio.run(body)


def test_host_args_raises_type_error_message() -> None:
    with pytest.raises(TypeError, match="no host args for"):
        _host_args(cast(Any, object()))


def test_decide_no_reconcile_rule() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            assert arguments == {}
            assert effect is CallEffect.READ
            return _meta_bound()

        lost = LostWrite(
            _desc("revit_get_model_metadata"),
            OpenModelArgs(path=str(BOUND)),
            Binding(target=HostTarget(product="revit", pid=7), owned=True),
            True,
            None,
        )
        found = await reconciler.decide(lost, read)
        assert found.outcome == "unknown"
        assert found.evidence == {"reason": "no reconcile rule for revit_get_model_metadata"}

    anyio.run(body)


def test_as_int_rejects_bool() -> None:
    """bool must not be treated as an int type_id (kills `or`→`and` on the None/bool guard)."""

    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
        model = DuplicateFamilyTypeArgs(source_type_id="2001", new_type_name="N")
        types = [
            {"name": "C300x300", "type_id": 2001, "family": "F", "family_id": 1},
            {"name": "N", "type_id": True, "family": "F", "family_id": 1},  # invalid
        ]

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_list_family_types_in_family":
                return {"items": list(types), "truncated": False}
            raise AssertionError(tool)

        found = await reconciler.decide(_lost("revit_duplicate_family_type", model, pre_image=None), read)
        assert found.outcome == "unknown"
        assert "type_id" in str(found.evidence.get("reason", "")).lower() or found.outcome == "unknown"

    anyio.run(body)


def test_observe_wrong_model_returns_none() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return _meta_bound()

        # Descriptor name says duplicate but model is a setter → observe returns None.
        lost = LostWrite(
            _desc("revit_duplicate_family_type"),
            SetElementParameterValuesArgs(element_ids=[1], parameter_name="b", value="1", value_type="integer"),
            Binding(target=HostTarget(product="revit", pid=7), owned=True),
            True,
            None,
        )
        assert await reconciler.observe(lost, read) is None

    anyio.run(body)


def test_guid_and_type_setters() -> None:
    from eng_harness.adapters.revit._tools import SetParameterValueByGuidArgs, SetTypeParameterValuesArgs

    async def body() -> None:
        reconciler = RevitReconciler(
            tolerance_ratio=0.001,
            bound_path=BOUND,
            unique_ids={3001: "col-3001", 3002: "col-3002"},
        )
        guid = "11111111-1111-1111-1111-111111111111"
        values = {3001: FEET_450, 3002: FEET_300}

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_get_element_parameters":
                eid = int(arguments["elementIds"][0])
                assert arguments.get("guid") is None or True
                return {
                    "items": [
                        {
                            "parameters": [
                                {
                                    "name": "b",
                                    "guid": guid,
                                    "rawValue": values[eid],
                                    "specId": LENGTH_SPEC,
                                    "storageType": "Double",
                                }
                            ]
                        }
                    ]
                }
            if tool == "revit_get_type_parameters":
                tid = int(arguments["typeIds"][0])
                raw = FEET_450 if tid == 2001 else FEET_300
                return {"items": [{"parameters": [_param(raw)]}]}
            raise AssertionError(tool)

        guid_model = SetParameterValueByGuidArgs(
            element_ids=[3001, 3002],
            guid=guid,
            value="450",
            value_type="double",
            unit="mm",
            target="instance",
            all_or_nothing=True,
        )
        guid_found = await reconciler.decide(
            _lost("revit_set_parameter_value_by_guid", guid_model, pre_image={guid: 300.0}),
            read,
        )
        assert guid_found.outcome == "partial"
        assert guid_found.missing == ("col-3002",)
        assert guid_found.evidence["requested"] == {guid: 450.0}

        type_model = SetTypeParameterValuesArgs(
            parameter_name="b",
            value="450",
            value_type="double",
            type_ids=[2001, 2002],
            expected_instances=[3001],
        )
        type_found = await reconciler.decide(
            _lost("revit_set_type_parameter_values", type_model, pre_image={"b": 300.0}),
            read,
        )
        assert type_found.outcome == "partial"
        assert type_found.missing == ("2002",)
        assert type_found.evidence["requested"] == {"b": 450.0}

    anyio.run(body)


def test_duplicate_family_name_only_scope() -> None:
    """When the source row has no family_id, family_name must still scope the lookup."""

    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
        model = DuplicateFamilyTypeArgs(source_type_id="2001", new_type_name="N")
        types = [
            {"name": "C300x300", "type_id": 2001, "family": "F"},  # no family_id
            {"name": "N", "type_id": 55, "family": "F"},
            {"name": "N", "type_id": 99, "family": "Other"},
        ]
        seen: list[dict[str, Any]] = []

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_list_family_types_in_family":
                seen.append(dict(arguments))
                family_name = arguments.get("family_name")
                rows = [row for row in types if family_name is None or row.get("family") == family_name]
                return {"items": rows, "truncated": False}
            if tool == "revit_get_type_parameters":
                return {"items": [{"id": int(arguments["typeIds"][0]), "parameters": [_param(1.0)]}]}
            raise AssertionError(tool)

        found = await reconciler.decide(_lost("revit_duplicate_family_type", model, pre_image=None), read)
        assert found.outcome == "applied"
        assert any(call.get("family_name") == "F" for call in seen)

    anyio.run(body)


def test_wrong_model_branches_unknown() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return _meta_bound()

        change = await reconciler.decide(
            LostWrite(
                _desc("revit_change_element_type"),
                OpenModelArgs(path=str(BOUND)),
                Binding(target=HostTarget(product="revit", pid=7), owned=True),
                True,
                None,
            ),
            read,
        )
        assert change.outcome == "unknown"
        assert change.evidence["reason"] == "not a change-element-type model"

        dup = await reconciler.decide(
            LostWrite(
                _desc("revit_duplicate_family_type"),
                OpenModelArgs(path=str(BOUND)),
                Binding(target=HostTarget(product="revit", pid=7), owned=True),
                True,
                None,
            ),
            read,
        )
        assert dup.outcome == "unknown"
        assert dup.evidence["reason"] == "not a duplicate-family-type model"

        open_wrong = await reconciler.decide(
            LostWrite(
                _desc("revit_open_model"),
                ChangeElementTypeArgs(element_ids=[1], type_id=2),
                Binding(target=HostTarget(product="revit", pid=7), owned=True),
                True,
                None,
            ),
            read,
        )
        assert open_wrong.outcome == "unknown"
        assert open_wrong.evidence["reason"] == "not an open-model model"

    anyio.run(body)


def test_read_error_paths_with_reasons() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
        model = DuplicateFamilyTypeArgs(source_type_id="2001", new_type_name="N")

        async def list_not_mapping(tool: str, arguments: dict[str, Any], effect: CallEffect) -> Any:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            return ["not", "a", "mapping"]

        found = await reconciler.decide(_lost("revit_duplicate_family_type", model, pre_image=None), list_not_mapping)
        assert found.outcome == "unknown"
        assert "mapping" in str(found.evidence.get("reason", ""))

        async def items_not_list(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            return {"items": "nope", "truncated": False}

        found2 = await reconciler.decide(_lost("revit_duplicate_family_type", model, pre_image=None), items_not_list)
        assert found2.outcome == "unknown"
        assert "items are not a list" in str(found2.evidence.get("reason", ""))

        async def source_missing(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            return {"items": [{"name": "Other", "type_id": 9, "family": "F", "family_id": 1}], "truncated": False}

        found3 = await reconciler.decide(_lost("revit_duplicate_family_type", model, pre_image=None), source_missing)
        assert found3.outcome == "unknown"
        assert "was not found" in str(found3.evidence.get("reason", ""))

        async def params_truncated(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_list_family_types_in_family":
                return {
                    "items": [
                        {"name": "C300x300", "type_id": 2001, "family": "F", "family_id": 1},
                        {"name": "N", "type_id": 55, "family": "F", "family_id": 1},
                    ],
                    "truncated": False,
                }
            return {"items": [{"id": 55, "parameters": [_param(1.0)]}], "truncated": True}

        found4 = await reconciler.decide(_lost("revit_duplicate_family_type", model, pre_image=None), params_truncated)
        assert found4.outcome == "unknown"
        assert "truncated" in str(found4.evidence.get("reason", "")).lower()

    anyio.run(body)


def test_change_type_continue_across_elements() -> None:
    """First element unknown must not stop the loop (continue, not break)."""

    async def body() -> None:
        reconciler = RevitReconciler(
            tolerance_ratio=0.001,
            bound_path=BOUND,
            unique_ids={1: "u1", 2: "u2"},
        )
        details = {
            1: None,  # missing → unknown
            2: {"unique_id": "u2", "type_id": 99},
        }

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_get_element_details":
                eid = int(arguments["elementIds"][0])
                row = details[eid]
                if row is None:
                    raise ContractError(ErrorCode.NOT_FOUND, "gone")
                return {"items": [row]}
            raise AssertionError(tool)

        found = await reconciler.decide(
            _lost(
                "revit_change_element_type",
                ChangeElementTypeArgs(element_ids=[1, 2], type_id=99),
                pre_image={"by_element": {"1": {"type_id": 1}, "2": {"type_id": 1}}},
            ),
            read,
        )
        # any unknown → unknown overall, but element 2 must still have been read (applied).
        assert found.outcome == "unknown"
        observed = cast(dict[str, Any], found.evidence["observed"])
        assert observed["2"] == {"type_id": 99}
        assert observed["1"] is None

    anyio.run(body)


def _family_scoped_read(scoped_pages: dict[int, dict[str, Any]], calls: list[dict[str, Any]]) -> Any:
    """Unscoped source lookup is complete; the family-scoped lookup pages by `start_index`."""
    source = {"name": "C300x300", "type_id": 2001, "family": "F", "family_id": 1}

    async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
        if tool == "revit_get_model_metadata":
            return _meta_bound()
        if tool == "revit_list_family_types_in_family":
            if "family_id" not in arguments:
                return {"items": [dict(source)], "truncated": False}
            calls.append(dict(arguments))
            return scoped_pages[int(arguments["start_index"])]
        if tool == "revit_get_type_parameters":
            tid = int(arguments["typeIds"][0])
            return {"items": [{"id": tid, "parameters": [_param(1.0)]}]}
        raise AssertionError(tool)

    return read


def test_duplicate_family_scoped_lookup_pages_past_truncation() -> None:
    """A truncated family-scoped page is not the whole family: the next page holds the new name (§4.10)."""

    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
        model = DuplicateFamilyTypeArgs(source_type_id="2001", new_type_name="N")
        calls: list[dict[str, Any]] = []
        pages = {
            0: {"items": [{"name": "C300x300", "type_id": 2001, "family": "F", "family_id": 1}], "truncated": True},
            1: {"items": [{"name": "N", "type_id": 55, "family": "F", "family_id": 1}], "truncated": False},
        }
        found = await reconciler.decide(
            _lost("revit_duplicate_family_type", model, pre_image=None), _family_scoped_read(pages, calls)
        )
        assert found.outcome == "applied"
        assert [c["start_index"] for c in calls] == [0, 1]
        # Inventory schema: family_id is a string (ListFamilyTypesInFamilyArgs.family_id).
        assert all(c["family_id"] == "1" for c in calls)

    anyio.run(body)


def test_duplicate_family_scoped_truncated_empty_page_is_unknown() -> None:
    """A truncated page with no rows cannot prove absence: unknown, never not_applied (§4.10, R1)."""

    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
        model = DuplicateFamilyTypeArgs(source_type_id="2001", new_type_name="N")
        calls: list[dict[str, Any]] = []
        pages = {
            0: {"items": [{"name": "C300x300", "type_id": 2001, "family": "F", "family_id": 1}], "truncated": True},
            1: {"items": [], "truncated": True},
        }
        found = await reconciler.decide(
            _lost("revit_duplicate_family_type", model, pre_image=None), _family_scoped_read(pages, calls)
        )
        assert found.outcome == "unknown"
        assert "truncated" in str(found.evidence.get("reason", ""))

    anyio.run(body)


def test_change_type_truncated_details_is_unknown() -> None:
    """A truncated get_element_details reply is a read issue: unknown, never not_applied (§4.10)."""

    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND, unique_ids={3001: "u1"})

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_get_element_details":
                return {"items": [{"unique_id": "u1", "type_id": 2001}], "truncated": True}
            raise AssertionError(tool)

        found = await reconciler.decide(
            _lost(
                "revit_change_element_type",
                ChangeElementTypeArgs(element_ids=[3001], type_id=2002),
                pre_image={"type_id": 2001},
            ),
            read,
        )
        assert found.outcome == "unknown"
        assert cast(dict[str, Any], found.evidence["observed"])["3001"] is None

    anyio.run(body)


def test_setter_none_pre_image_other_value_is_unknown() -> None:
    """Known pre-image None and a read showing another value: neither requested nor pre-image → unknown."""

    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND, unique_ids={3001: "col-3001"})

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_get_element_parameters":
                return {"items": [{"parameters": [_param(FEET_400)]}]}
            raise AssertionError(tool)

        found = await reconciler.decide(
            _lost(
                "revit_set_element_parameter_values",
                SetElementParameterValuesArgs(element_ids=[3001], parameter_name="b", value="450", value_type="double"),
                known=True,
                pre_image=None,
            ),
            read,
        )
        assert found.outcome == "unknown"

    anyio.run(body)


def test_paths_compare_as_windows_paths() -> None:
    """Metadata path differing only by case or slash direction is the same document (PureWindowsPath, §4.10)."""

    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND, unique_ids={3001: "col-3001"})
        same = "c:/MODELS/Edits.RVT"

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return {"path": same}
            if tool == "revit_get_element_parameters":
                return {"items": [{"parameters": [_param(FEET_450)]}]}
            raise AssertionError(tool)

        opened = await reconciler.decide(_lost("revit_open_model", OpenModelArgs(path=str(BOUND))), read)
        assert opened.outcome == "applied"
        setter = await reconciler.decide(
            _lost(
                "revit_set_element_parameter_values",
                SetElementParameterValuesArgs(element_ids=[3001], parameter_name="b", value="450", value_type="double"),
                pre_image={"b": 300.0},
            ),
            read,
        )
        assert setter.outcome == "applied"

    anyio.run(body)


def test_open_model_empty_path_is_unknown() -> None:
    """An empty metadata path names no document, so it cannot prove another document is active."""

    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return {"path": ""}

        found = await reconciler.decide(_lost("revit_open_model", OpenModelArgs(path=str(BOUND))), read)
        assert found.outcome == "unknown"

    anyio.run(body)


def test_setter_by_target_missing_key_has_no_pre_image() -> None:
    reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
    lost = _lost(
        "revit_set_element_parameter_values",
        SetElementParameterValuesArgs(element_ids=[3001], parameter_name="b", value="450", value_type="double"),
        pre_image={"by_target": {}},
    )
    assert reconciler._pre_for_target(lost, 3001) is _NO_PRE


@pytest.mark.parametrize(
    ("tool", "model", "read_tool"),
    [
        (
            "revit_set_element_parameter_values",
            SetElementParameterValuesArgs(element_ids=[3001], parameter_name="b", value="450", value_type="double"),
            "revit_get_element_parameters",
        ),
        (
            "revit_set_type_parameter_values",
            SetTypeParameterValuesArgs(
                parameter_name="b",
                value="450",
                value_type="double",
                type_ids=[2001],
                expected_instances=[3001],
            ),
            "revit_get_type_parameters",
        ),
        (
            "revit_set_parameter_value_by_guid",
            SetParameterValueByGuidArgs(
                element_ids=[3001],
                guid="11111111-1111-1111-1111-111111111111",
                value="450",
                value_type="double",
                unit="mm",
                target="instance",
                all_or_nothing=True,
            ),
            "revit_get_element_parameters",
        ),
    ],
    ids=["element-name", "type-name", "instance-guid"],
)
def test_setter_absent_before_and_after_is_unknown(tool: str, model: Any, read_tool: str) -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)

        async def read(name: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if name == "revit_get_model_metadata":
                return _meta_bound()
            if name == read_tool:
                return {"items": [{"parameters": []}]}
            raise AssertionError(name)

        found = await reconciler.decide(_lost(tool, model, pre_image=None), read)
        assert found.outcome == "unknown"

    anyio.run(body)


@pytest.mark.parametrize(
    "malformed",
    [
        {"items": []},
        {"items": "not-a-list"},
        {"items": ["not-a-mapping"]},
        {"items": [{"parameters": "not-a-list"}]},
    ],
    ids=["empty-items", "items-not-list", "item-not-mapping", "parameters-not-list"],
)
@pytest.mark.parametrize(
    ("tool", "model", "read_tool"),
    [
        (
            "revit_set_element_parameter_values",
            SetElementParameterValuesArgs(element_ids=[3001], parameter_name="b", value="450", value_type="double"),
            "revit_get_element_parameters",
        ),
        (
            "revit_set_type_parameter_values",
            SetTypeParameterValuesArgs(
                parameter_name="b",
                value="450",
                value_type="double",
                type_ids=[2001],
                expected_instances=[3001],
            ),
            "revit_get_type_parameters",
        ),
    ],
    ids=["element-parameters", "type-parameters"],
)
def test_setter_malformed_parameter_reply_is_unknown(
    tool: str,
    model: Any,
    read_tool: str,
    malformed: dict[str, Any],
) -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)

        async def read(name: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if name == "revit_get_model_metadata":
                return _meta_bound()
            if name == read_tool:
                return malformed
            raise AssertionError(name)

        found = await reconciler.decide(_lost(tool, model, pre_image=None), read)
        assert found.outcome == "unknown"
        assert "reply" in str(found.evidence.get("reason", ""))

    anyio.run(body)


def test_guid_type_target_is_unknown_but_instance_target_is_observed() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
        guid = "11111111-1111-1111-1111-111111111111"

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_get_element_parameters":
                return {
                    "items": [
                        {
                            "parameters": [
                                {
                                    "name": "b",
                                    "guid": guid,
                                    "rawValue": FEET_450,
                                    "specId": LENGTH_SPEC,
                                    "storageType": "Double",
                                }
                            ]
                        }
                    ]
                }
            raise AssertionError(tool)

        type_target = SetParameterValueByGuidArgs(
            element_ids=[3001],
            guid=guid,
            value="450",
            value_type="double",
            unit="mm",
            target="type",
            all_or_nothing=True,
        )
        type_found = await reconciler.decide(
            _lost("revit_set_parameter_value_by_guid", type_target, pre_image=None), read
        )
        assert type_found.outcome == "unknown"
        assert type_found.evidence["target"] == "type"
        assert "not read" in str(type_found.evidence["reason"])

        instance_target = type_target.model_copy(update={"target": "instance"})
        instance_found = await reconciler.decide(
            _lost("revit_set_parameter_value_by_guid", instance_target, pre_image={guid: 300.0}), read
        )
        assert instance_found.outcome == "applied"

    anyio.run(body)


def test_quantity_without_tolerance_is_unknown() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=None, bound_path=BOUND)

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_get_element_parameters":
                return {"items": [{"parameters": [_param(FEET_450)]}]}
            raise AssertionError(tool)

        found = await reconciler.decide(
            _lost(
                "revit_set_element_parameter_values",
                SetElementParameterValuesArgs(element_ids=[3001], parameter_name="b", value="450", value_type="double"),
                pre_image={"b": 300.0},
            ),
            read,
        )
        assert found.outcome == "unknown"

    anyio.run(body)


def test_duplicate_family_scoped_paging_stops_at_page_cap() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
        model = DuplicateFamilyTypeArgs(source_type_id="2001", new_type_name="N")
        calls: list[dict[str, Any]] = []

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_list_family_types_in_family":
                if "family_id" not in arguments:
                    return {
                        "items": [{"name": "C300x300", "type_id": 2001, "family": "F", "family_id": 1}],
                        "truncated": False,
                    }
                calls.append(dict(arguments))
                start = int(arguments["start_index"])
                return {
                    "items": [{"name": f"Other-{start}", "type_id": start + 3000, "family": "F"}],
                    "truncated": True,
                }
            raise AssertionError(tool)

        found = await reconciler.decide(_lost("revit_duplicate_family_type", model, pre_image=None), read)
        assert found.outcome == "unknown"
        assert found.evidence["reason"] == "revit_list_family_types_in_family paging did not complete"
        assert len(calls) == _MAX_PAGES

    anyio.run(body)


def test_duplicate_family_scoped_paging_advances_by_multirow_page_size() -> None:
    async def body() -> None:
        reconciler = RevitReconciler(tolerance_ratio=0.001, bound_path=BOUND)
        model = DuplicateFamilyTypeArgs(source_type_id="2001", new_type_name="N")
        calls: list[dict[str, Any]] = []
        rows = [
            {"name": f"Other-{index}", "type_id": 3000 + index, "family": "F", "family_id": 1} for index in range(_PAGE)
        ]

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "revit_get_model_metadata":
                return _meta_bound()
            if tool == "revit_list_family_types_in_family":
                if "family_id" not in arguments:
                    return {
                        "items": [{"name": "C300x300", "type_id": 2001, "family": "F", "family_id": 1}],
                        "truncated": False,
                    }
                calls.append(dict(arguments))
                if arguments["start_index"] == 0:
                    return {"items": rows, "truncated": True}
                return {
                    "items": [{"name": "N", "type_id": 5000, "family": "F", "family_id": 1}],
                    "truncated": False,
                }
            if tool == "revit_get_type_parameters":
                return {"items": [{"parameters": [_param(1.0)]}]}
            raise AssertionError(tool)

        found = await reconciler.decide(_lost("revit_duplicate_family_type", model, pre_image=None), read)
        assert found.outcome == "applied"
        assert [call["start_index"] for call in calls] == [0, _PAGE]

    anyio.run(body)
