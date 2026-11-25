"""IDEA calculate private helpers (plan 0014 T8; spec 0014 AC11 to AC13, AC18).

Exercises `_assumptions`, `_error_verdict`, `_verdicts_from_connections`, `_looks_like_check_reply`,
`_raise_host`, `_store_pair`, `_process_success`, `_require_service_reachable`, and the public
`calculate_native` / `calculate_rest` / `get_check_results` call shapes so mutmut survivors are killed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

import anyio
import pytest
from eng_contract.envelope import HostInfo, LiteralInput
from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from eng_contract.verdicts import SubjectKind, VerdictSource, VerdictStatus
from mcp.types import CallToolResult, TextContent
from pydantic import JsonValue

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.adapters.idea import _calculate as m
from eng_harness.adapters.idea._calculate import CalculateProvenance
from eng_harness.adapters.idea._replies import TEXT_LIMIT
from eng_harness.adapters.idea._verdicts import HOST_ASSUMPTION
from eng_harness.kinds.idea import IDEA_KINDS
from eng_harness.servers import CallEffect

_DESIGN_CODE = "AISC 360-16"  # design basis field connection.design_code (spec 0014 AC15); test label only
_START = 1_700_000_000_000


def _check(
    name: str = "Plates",
    value: float = 50.0,
    *,
    status: bool = True,
    skipped: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "check_value": value,
        "check_status": status,
        "skipped": skipped,
        "message": "OK",
        "load_case_id": "LC1",
    }


def _connection(
    name: str = "CON1",
    *,
    connection_id: int = 1,
    calculated: bool = True,
    passed: bool = True,
    checks: list[dict[str, Any]] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "connection_id": connection_id,
        "name": name,
        "passed": passed,
        "calculated": calculated,
        "checks": checks if checks is not None else [_check()],
        "errors": errors or [],
        "warnings": [],
    }


def _store(tmp_path: Any) -> ResultStore:
    clock = FixedClock(_START)
    ids = SeededIdSource(b"idea-calc-helpers", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    return ResultStore(workspace, HARNESS_KINDS.extend(IDEA_KINDS), ids, clock)


def _provenance(*, revision: int = 1, tick: int = 1) -> CalculateProvenance:
    """Caller-supplied clock/host/build for store provenance (spec 0002 section 4.5.3)."""
    return CalculateProvenance(
        clock=FixedClock(_START, tick),
        host=HostInfo(
            program="idea",
            version="",
            model_id="mdl_01HF7YAT00361949KDC0CXNRAC",
            model_revision=revision,
        ),
        tool_version="test-build+deadbeefdead",
    )


def _store_kwargs(store: ResultStore | None = None, **extra: Any) -> dict[str, Any]:
    """Common kwargs for _store_pair / _process_success after the fix-round provenance change."""
    clock = FixedClock(_START, 1)
    base: dict[str, Any] = {
        "provenance": _provenance(),
        "inputs": {"path": LiteralInput(literal="joint.ideaCon")},
        "files": (),
        "started_at": clock.now(),
        "duration_ms": 3,
    }
    base.update(extra)
    return base


def test_assumptions_native_and_rest() -> None:
    """AC12 / AC15: native keeps HOST_ASSUMPTION only; rest adds design-code and loads extras."""
    native = m._assumptions(route="native")
    assert native == [HOST_ASSUMPTION]

    with_extra = m._assumptions(route="native", extras=("extra note",))
    assert with_extra == [HOST_ASSUMPTION, "extra note"]

    rest = m._assumptions(route="rest")
    assert rest == [
        HOST_ASSUMPTION,
        m._REST_CODE_ASSUMPTION,
        m._REST_LOADS_ASSUMPTION,
    ]
    assert rest[1] == "design code declared in the design basis, not read from the host"
    assert rest[2] == "loads as stored in the opened file"

    rest_extra = m._assumptions(route="rest", extras=("host text",))
    assert rest_extra[0] == HOST_ASSUMPTION
    assert rest_extra[1] == "host text"
    assert rest_extra[2] == m._REST_CODE_ASSUMPTION
    assert rest_extra[3] == m._REST_LOADS_ASSUMPTION

    long_extra = "x" * (TEXT_LIMIT + 40)
    cut = m._assumptions(route="native", extras=(long_extra,))
    assert cut[1] == long_extra[:TEXT_LIMIT]
    assert len(cut[1]) == TEXT_LIMIT


def test_error_verdict_fields() -> None:
    """AC12: idea:connection ERROR; ratio None; governing False; empty errors → fallback; text cut at 500."""
    verdict = m._error_verdict(
        connection_name="CON1",
        design_code=_DESIGN_CODE,
        route="native",
        errors=["CBFEM singular", "second"],
    )
    assert verdict.check_id == "idea:connection"
    assert verdict.status is VerdictStatus.ERROR
    assert verdict.ratio is None
    assert verdict.governing is False
    assert verdict.source is VerdictSource.HOST
    assert verdict.code == _DESIGN_CODE
    assert verdict.subject.kind is SubjectKind.JOINT
    assert verdict.subject.id == "CON1"
    assert verdict.demand is None
    assert verdict.capacity is None
    assert verdict.clause is None
    assert verdict.trace_ref is None
    assert any("CBFEM singular" in a and "second" in a for a in verdict.assumptions)

    empty = m._error_verdict(
        connection_name="CON2",
        design_code=_DESIGN_CODE,
        route="rest",
        errors=["", ""],
    )
    # Empty/falsy error items → join empty → fallback message in assumptions extras.
    assert any("host text was empty" in a for a in empty.assumptions)
    assert empty.ratio is None
    assert empty.governing is False
    assert empty.status is VerdictStatus.ERROR
    assert m._REST_CODE_ASSUMPTION in empty.assumptions
    assert m._REST_LOADS_ASSUMPTION in empty.assumptions

    huge = "E" * (TEXT_LIMIT + 80)
    cut_verdict = m._error_verdict(
        connection_name="CON3",
        design_code=_DESIGN_CODE,
        route="native",
        errors=[huge],
    )
    assert all(len(a) <= TEXT_LIMIT for a in cut_verdict.assumptions)
    assert any(huge[:TEXT_LIMIT] == a or huge[:TEXT_LIMIT] in a for a in cut_verdict.assumptions)

    # Missing/empty name on the connection row becomes "connection" in the builder path.
    missing_name = m._verdicts_from_connections(
        [{"errors": ["boom"], "checks": []}],
        design_code=_DESIGN_CODE,
        route="native",
        load_map_confirmed=True,
    )
    assert missing_name.verdicts[0].subject.id == "connection"


def test_verdicts_from_connections_only_errors() -> None:
    """AC12: only-errors path builds ERROR verdicts without check-row mapping; draft from map/route."""
    rows = [_connection(errors=["singular matrix"], checks=[])]
    native_unconfirmed = m._verdicts_from_connections(
        rows,
        design_code=_DESIGN_CODE,
        route="native",
        load_map_confirmed=False,
    )
    assert len(native_unconfirmed.verdicts) == 1
    assert native_unconfirmed.verdicts[0].check_id == "idea:connection"
    assert native_unconfirmed.verdicts[0].status is VerdictStatus.ERROR
    assert native_unconfirmed.draft is True
    assert native_unconfirmed.traces == []
    assert native_unconfirmed.counts[VerdictStatus.ERROR] == 1

    rest_confirmed = m._verdicts_from_connections(
        rows,
        design_code=_DESIGN_CODE,
        route="rest",
        load_map_confirmed=True,
    )
    assert rest_confirmed.draft is True  # route rest always draft

    native_confirmed = m._verdicts_from_connections(
        rows,
        design_code=_DESIGN_CODE,
        route="native",
        load_map_confirmed=True,
    )
    assert native_confirmed.draft is False


def test_verdicts_from_connections_mix_and_filter() -> None:
    """AC12/AC13: mix error+check rows; skip non-Mapping entries; empty → PRECONDITION_FAILED."""
    mixed = [
        "skip-me",  # not a Mapping
        _connection(name="OK", connection_id=1, checks=[_check("Bolts", 40.0)]),
        _connection(name="BAD", connection_id=2, errors=["host failure"], checks=[]),
        42,  # not a Mapping
    ]
    payload = m._verdicts_from_connections(
        cast("Sequence[Mapping[str, Any]]", mixed),
        design_code=_DESIGN_CODE,
        route="native",
        load_map_confirmed=True,
    )
    assert payload.draft is False
    error_rows = [v for v in payload.verdicts if v.check_id == "idea:connection" and v.status is VerdictStatus.ERROR]
    check_rows = [v for v in payload.verdicts if v.check_id != "idea:connection" or v.status is not VerdictStatus.ERROR]
    assert len(error_rows) == 1
    assert error_rows[0].subject.id == "BAD"
    assert any(v.subject.id == "OK" for v in check_rows)
    assert payload.counts[VerdictStatus.ERROR] >= 1

    with pytest.raises(ContractError) as raised:
        m._verdicts_from_connections(
            [],
            design_code=_DESIGN_CODE,
            route="native",
            load_map_confirmed=True,
        )
    assert raised.value.detail.code is ErrorCode.PRECONDITION_FAILED
    assert raised.value.detail.precondition is Precondition.analysis_current


def test_verdicts_from_connections_checks_only_and_rest_draft() -> None:
    """AC13/AC14: check-only path returns base set; rest draft true even when load map confirmed."""
    rows = [_connection(checks=[_check("Plates", 55.0)])]
    native = m._verdicts_from_connections(
        rows,
        design_code=_DESIGN_CODE,
        route="native",
        load_map_confirmed=True,
    )
    assert native.draft is False
    assert all(v.status is not VerdictStatus.ERROR or v.check_id != "idea:connection" for v in native.verdicts)
    assert native.verdicts

    rest = m._verdicts_from_connections(
        rows,
        design_code=_DESIGN_CODE,
        route="rest",
        load_map_confirmed=True,
    )
    assert rest.draft is True


def test_looks_like_check_reply() -> None:
    """AC12: true when any check-reply field is present; false for bare unexpected shapes."""
    assert m._looks_like_check_reply({"connections": []}) is True
    assert m._looks_like_check_reply({"offline_stub": False}) is True
    assert m._looks_like_check_reply({"backend": "rest"}) is True
    assert m._looks_like_check_reply({"notice": "x"}) is True
    assert m._looks_like_check_reply({"connections": [], "extra": 1}) is True

    assert m._looks_like_check_reply({}) is False
    assert m._looks_like_check_reply({"unexpected": True, "payload": "malformed"}) is False
    assert m._looks_like_check_reply({"route": "rest"}) is False
    assert m._looks_like_check_reply({"checks": []}) is False


def test_raise_host_unexpected_and_mapped() -> None:
    """AC12/AC17: no parseable error → UNEXPECTED_REPLY; mapped host code becomes ContractError."""
    # Non-error / unparseable shape → parse_error_reply None → UNEXPECTED_REPLY.
    plain = {"isError": False, "content": [{"type": "text", "text": "{}"}]}
    with pytest.raises(ContractError) as unexpected:
        m._raise_host(
            plain,
            tool="idea_calculate",
            effect=CallEffect.WRITE,
            ids=SeededIdSource(b"rh", FixedClock(_START)),
        )
    assert unexpected.value.detail.code is ErrorCode.HOST_ERROR
    assert unexpected.value.detail.host_code == "UNEXPECTED_REPLY"
    assert unexpected.value.detail.host_method == "idea_calculate"

    err = CallToolResult(
        content=[TextContent(type="text", text='{"code":"timeout","message":"The call timed out."}')],
        is_error=True,
    )
    with pytest.raises(ContractError) as mapped:
        m._raise_host(
            err,
            tool="idea_calculate",
            effect=CallEffect.WRITE,
            ids=SeededIdSource(b"rh2", FixedClock(_START)),
            op_id="op-1",
        )
    assert mapped.value.detail.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME
    assert mapped.value.detail.host_method == "idea_calculate" or mapped.value.detail.op_id == "op-1"


def test_store_pair(tmp_path: Any) -> None:
    """AC14: stores harness.idea_check_raw/1 then verdicts.set/1 with raw as parent."""
    from eng_contract.kinds.verdicts import VerdictSet
    from eng_contract.verdicts import Subject, Verdict

    store = _store(tmp_path)
    verdict = Verdict(
        source=VerdictSource.HOST,
        check_id="idea:plates",
        code=_DESIGN_CODE,
        clause=None,
        subject=Subject(kind=SubjectKind.JOINT, id="CON1", station_mm=None, case=None),
        demand=None,
        capacity=None,
        ratio=0.5,
        ratio_limit=1.0,
        status=VerdictStatus.PASS,
        governing=True,
        trace_ref=None,
        assumptions=[HOST_ASSUMPTION],
    )
    counts = dict.fromkeys(VerdictStatus, 0)
    counts[VerdictStatus.PASS] = 1
    verdicts = VerdictSet(verdicts=[verdict], traces=[], counts=counts, draft=True)
    connection = {
        "connection_id": 1,
        "name": "CON1",
        "passed": True,
        "calculated": True,
        "checks": [
            {
                "name": "Plates",
                "check_value": 50.0,
                "check_status": True,
                "skipped": False,
                "message": "OK",
                "load_case_id": "LC1",
            }
        ],
        "errors": [],
        "warnings": [],
    }
    raw_payload: dict[str, Any] = {
        "route": "native",
        "backend": None,
        "offline_stub": False,
        "connections": [connection],
    }
    raw_env, verd_env = m._store_pair(
        store=store,
        tool="idea_native_calculate",
        raw_payload=raw_payload,
        verdicts=verdicts,
        **_store_kwargs(),
    )
    assert raw_env.kind == "harness.idea_check_raw/1"
    assert verd_env.kind == "verdicts.set/1"
    assert raw_env.summary["route"] == "native"
    assert raw_env.summary["connections"] == 1
    assert verd_env.summary["draft"] is True
    counts_summary = verd_env.summary["counts"]
    assert isinstance(counts_summary, dict)
    assert counts_summary["PASS"] == 1

    raw_empty: dict[str, Any] = {
        "route": "rest",
        "backend": "rest",
        "offline_stub": False,
        "connections": [],
    }
    raw2, _ = m._store_pair(
        store=store,
        tool="idea_calculate",
        raw_payload=raw_empty,
        verdicts=verdicts,
        **_store_kwargs(),
    )
    assert raw2.summary["connections"] == 0


def _status_result(*, reachable: bool | None, is_error: bool = False, empty: bool = False) -> CallToolResult:
    if empty:
        return CallToolResult(content=[], is_error=False)
    if is_error:
        return CallToolResult(
            content=[TextContent(type="text", text='{"code":"service_unavailable","message":"down"}')],
            is_error=True,
        )
    if reachable is None:
        body = '{"service":"not-a-map"}'
    else:
        flag = "true" if reachable else "false"
        body = '{"service":{"reachable":' + flag + "}}"
    return CallToolResult(content=[TextContent(type="text", text=body)], is_error=False)


def test_require_service_reachable_branches() -> None:
    """AC11: idea_status must report service.reachable true; otherwise HOST_NOT_CONNECTED."""

    class _Sessions:
        def __init__(self, result: Any) -> None:
            self._result = result

        async def call(self, *_args: Any, **_kwargs: Any) -> Any:
            return self._result

    async def body() -> None:
        await m._require_service_reachable(
            sessions=_Sessions(_status_result(reachable=True)),
            server="idea",
            role="main",
        )

        with pytest.raises(ContractError) as err:
            await m._require_service_reachable(
                sessions=_Sessions(_status_result(reachable=True, is_error=True)),
                server="idea",
                role="main",
            )
        assert err.value.detail.code is ErrorCode.HOST_NOT_CONNECTED

        with pytest.raises(ContractError) as nobody:
            await m._require_service_reachable(
                sessions=_Sessions(_status_result(reachable=True, empty=True)),
                server="idea",
                role="main",
            )
        assert nobody.value.detail.code is ErrorCode.HOST_NOT_CONNECTED

        with pytest.raises(ContractError) as down:
            await m._require_service_reachable(
                sessions=_Sessions(_status_result(reachable=False)),
                server="idea",
                role="main",
            )
        assert down.value.detail.code is ErrorCode.HOST_NOT_CONNECTED
        assert "not reachable" in down.value.detail.message

        with pytest.raises(ContractError) as bad_service:
            await m._require_service_reachable(
                sessions=_Sessions(_status_result(reachable=None)),
                server="idea",
                role="main",
            )
        assert bad_service.value.detail.code is ErrorCode.HOST_NOT_CONNECTED

    anyio.run(body)


def test_process_success_rejects_unexpected_shape(tmp_path: Any) -> None:
    """AC12: bare unexpected shape is UNEXPECTED_REPLY, not OFFLINE_STUB."""
    store = _store(tmp_path)
    bad = CallToolResult(
        content=[TextContent(type="text", text='{"unexpected":true,"payload":"malformed"}')],
        is_error=False,
    )

    async def body() -> None:
        with pytest.raises(ContractError) as raised:
            await m._process_success(
                bad,
                tool="idea_native_calculate",
                design_code=_DESIGN_CODE,
                route="native",
                load_map_confirmed=False,
                store=store,
                **_store_kwargs(),
            )
        assert raised.value.detail.code is ErrorCode.HOST_ERROR
        assert raised.value.detail.host_code == "UNEXPECTED_REPLY"

    anyio.run(body)


def test_raise_host_exact_unexpected_literals() -> None:
    """AC12: unparseable reply → HOST_ERROR / UNEXPECTED_REPLY with exact message, tool, retryable=False."""
    plain = {"isError": False, "content": [{"type": "text", "text": "{}"}]}
    with pytest.raises(ContractError) as unexpected:
        m._raise_host(
            plain,
            tool="idea_get_check_results",
            effect=CallEffect.READ,
            ids=SeededIdSource(b"rh-unexp", FixedClock(_START)),
        )
    detail = unexpected.value.detail
    assert detail.code is ErrorCode.HOST_ERROR
    assert detail.host_code == "UNEXPECTED_REPLY"
    assert detail.host_method == "idea_get_check_results"
    assert detail.message == "idea_get_check_results failed"
    assert detail.retryable is False


def test_raise_host_timeout_read_vs_write() -> None:
    """AC17: timeout maps READ→TIMEOUT_NO_EFFECT and WRITE→TIMEOUT_UNKNOWN_OUTCOME; op_id on write."""
    err = CallToolResult(
        content=[TextContent(type="text", text='{"code":"timeout","message":"The call timed out."}')],
        is_error=True,
    )
    ids = SeededIdSource(b"rh-to", FixedClock(_START))
    with pytest.raises(ContractError) as read_to:
        m._raise_host(err, tool="idea_native_calculate", effect=CallEffect.READ, ids=ids, op_id="op-read")
    assert read_to.value.detail.code is ErrorCode.TIMEOUT_NO_EFFECT

    with pytest.raises(ContractError) as write_to:
        m._raise_host(err, tool="idea_calculate", effect=CallEffect.WRITE, ids=ids, op_id="op-write")
    assert write_to.value.detail.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME
    assert write_to.value.detail.op_id == "op-write"


def test_raise_host_mapped_host_code_and_retryable() -> None:
    """AC17: idea_error / iom_error → HOST_ERROR with host_code from body; retryable False; host_method=tool."""
    ids = SeededIdSource(b"rh-map", FixedClock(_START))
    for code in ("idea_error", "iom_error"):
        err = CallToolResult(
            content=[TextContent(type="text", text=f'{{"code":"{code}","message":"host boom"}}')],
            is_error=True,
        )
        with pytest.raises(ContractError) as raised:
            m._raise_host(err, tool="idea_calculate", effect=CallEffect.WRITE, ids=ids)
        detail = raised.value.detail
        assert detail.code is ErrorCode.HOST_ERROR
        assert detail.host_code == code
        assert detail.host_method == "idea_calculate"
        assert detail.retryable is False


def test_raise_host_missing_body_no_code_fallback() -> None:
    """AC17: isError with missing body → no-code mapper path (not UNEXPECTED_REPLY)."""
    ids = SeededIdSource(b"rh-miss", FixedClock(_START))
    empty = CallToolResult(content=[], is_error=True)
    with pytest.raises(ContractError) as raised:
        m._raise_host(empty, tool="idea_get_check_results", effect=CallEffect.READ, ids=ids)
    # READ + no code → INTERNAL (not HOST_ERROR / UNEXPECTED_REPLY).
    assert raised.value.detail.code is ErrorCode.INTERNAL
    assert raised.value.detail.host_code != "UNEXPECTED_REPLY"

    # Analysis tool with no code on READ → TIMEOUT_UNKNOWN_OUTCOME.
    with pytest.raises(ContractError) as analysis:
        m._raise_host(empty, tool="idea_native_calculate", effect=CallEffect.READ, ids=ids, op_id="op-na")
    assert analysis.value.detail.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME
    assert analysis.value.detail.op_id == "op-na"


def test_store_pair_kinds_summary_parents_and_provenance(tmp_path: Any) -> None:
    """AC14 / 0002 §4.5.3: exact kinds, summary, parents, and <adapter>/<tool> provenance."""
    from eng_contract.kinds.verdicts import VerdictSet
    from eng_contract.verdicts import Subject, Verdict

    store = _store(tmp_path)
    verdict = Verdict(
        source=VerdictSource.HOST,
        check_id="idea:plates",
        code=_DESIGN_CODE,
        clause=None,
        subject=Subject(kind=SubjectKind.JOINT, id="CON1", station_mm=None, case=None),
        demand=None,
        capacity=None,
        ratio=0.4,
        ratio_limit=1.0,
        status=VerdictStatus.PASS,
        governing=True,
        trace_ref=None,
        assumptions=[HOST_ASSUMPTION],
    )
    counts = dict.fromkeys(VerdictStatus, 0)
    counts[VerdictStatus.PASS] = 1
    verdicts = VerdictSet(verdicts=[verdict], traces=[], counts=counts, draft=False)
    raw_payload: dict[str, Any] = {
        "route": "rest",
        "backend": "rest",
        "offline_stub": False,
        "connections": [
            {
                "connection_id": 7,
                "name": "CON7",
                "passed": True,
                "calculated": True,
                "checks": [
                    {
                        "name": "Plates",
                        "check_value": 40.0,
                        "check_status": True,
                        "skipped": False,
                        "message": "OK",
                        "load_case_id": "LC1",
                    }
                ],
                "errors": [],
                "warnings": [],
            }
        ],
    }
    raw_env, verd_env = m._store_pair(
        store=store,
        tool="idea_get_check_results",
        raw_payload=raw_payload,
        verdicts=verdicts,
        **_store_kwargs(),
    )
    assert raw_env.kind == "harness.idea_check_raw/1"
    assert verd_env.kind == "verdicts.set/1"
    assert set(raw_env.summary.keys()) == {"route", "connections"}
    assert raw_env.summary["route"] == "rest"
    assert raw_env.summary["connections"] == 1
    assert set(verd_env.summary.keys()) == {"draft", "counts"}
    assert verd_env.summary["draft"] is False
    counts_summary = verd_env.summary["counts"]
    assert isinstance(counts_summary, dict)
    assert counts_summary["PASS"] == 1
    assert raw_env.provenance.tool == "sasaah-idea-mcp/idea_get_check_results"
    assert verd_env.provenance.tool == "sasaah-idea-mcp/idea_get_check_results"
    assert verd_env.provenance.tool_version == "test-build+deadbeefdead"
    assert verd_env.provenance.host is not None
    assert verd_env.provenance.host.program == "idea"
    assert verd_env.provenance.host.model_revision == 1
    assert verd_env.provenance.duration_ms == 3
    stored = store.get(verd_env.result_id)
    assert stored.parents == [raw_env.result_id]


def test_store_pair_records_put_args_via_fake_store() -> None:
    """AC14: store.put receives exact kinds, parents=[raw_id], and connection_count 0 for non-list."""
    from types import SimpleNamespace

    from eng_contract.kinds.verdicts import VerdictSet
    from eng_contract.verdicts import Subject, Verdict

    puts: list[tuple[Any, ...]] = []

    class _FakeStore:
        def put(
            self,
            kind: str,
            payload: dict[str, Any],
            producer: Any,
            parents: Any = (),
            complete: bool = True,
        ) -> Any:
            ids_pool = ("res_01HF7YAT00361949KDC0CXNRAC", "res_01HF7YAT00361949KDC0CXNRAD")
            rid = ids_pool[len(puts)]
            puts.append((kind, payload, producer, list(parents), complete))
            return SimpleNamespace(
                result_id=rid,
                kind=kind,
                payload=payload,
                complete=complete,
                producer=producer,
            )

    verdict = Verdict(
        source=VerdictSource.HOST,
        check_id="idea:plates",
        code=_DESIGN_CODE,
        clause=None,
        subject=Subject(kind=SubjectKind.JOINT, id="CON1", station_mm=None, case=None),
        demand=None,
        capacity=None,
        ratio=0.1,
        ratio_limit=1.0,
        status=VerdictStatus.PASS,
        governing=False,
        trace_ref=None,
        assumptions=[HOST_ASSUMPTION],
    )
    counts = dict.fromkeys(VerdictStatus, 0)
    counts[VerdictStatus.PASS] = 1
    verdicts = VerdictSet(verdicts=[verdict], traces=[], counts=counts, draft=True)
    raw_env, verd_env = m._store_pair(
        store=cast(ResultStore, _FakeStore()),
        tool="idea_calculate",
        raw_payload=cast(dict[str, JsonValue], {"route": "rest", "connections": "not-a-list"}),
        verdicts=verdicts,
        **_store_kwargs(),
    )
    assert len(puts) == 2
    assert puts[0][0] == "harness.idea_check_raw/1"
    assert puts[1][0] == "verdicts.set/1"
    assert puts[1][3] == [raw_env.result_id]
    assert puts[0][2].tool == "sasaah-idea-mcp/idea_calculate"
    assert puts[1][2].tool == "sasaah-idea-mcp/idea_calculate"
    assert puts[0][2].tool_version == "test-build+deadbeefdead"
    assert puts[0][2].host is not None
    assert puts[0][2].host.model_revision == 1
    assert raw_env.summary["connections"] == 0
    assert raw_env.summary["route"] == "rest"
    assert verd_env.summary["draft"] is True


def test_process_success_offline_stub_refused(tmp_path: Any) -> None:
    """AC11/AC12: check-shaped offline stub → OFFLINE_STUB (not UNEXPECTED_REPLY)."""
    store = _store(tmp_path)
    stub = CallToolResult(
        content=[
            TextContent(
                type="text",
                text='{"offline_stub":true,"connections":[],"backend":"rest"}',
            )
        ],
        is_error=False,
    )

    async def body() -> None:
        with pytest.raises(ContractError) as raised:
            await m._process_success(
                stub,
                tool="idea_calculate",
                design_code=_DESIGN_CODE,
                route="rest",
                load_map_confirmed=False,
                store=store,
                **_store_kwargs(),
            )
        assert raised.value.detail.code is ErrorCode.HOST_ERROR
        assert raised.value.detail.host_code == "OFFLINE_STUB"
        assert raised.value.detail.host_method == "idea_calculate"
        assert raised.value.detail.retryable is False

    anyio.run(body)


def test_process_success_parses_minimal_native_connections(tmp_path: Any) -> None:
    """AC12: minimal valid check reply maps to IdeaCheckRaw + host verdicts and stores both kinds."""
    import json

    store = _store(tmp_path)
    body_obj = {
        "offline_stub": False,
        "backend": None,
        "connections": [
            {
                "connection_id": 1,
                "name": "CON1",
                "passed": True,
                "calculated": True,
                "checks": [
                    {
                        "name": "Plates",
                        "check_value": 50.0,
                        "check_status": True,
                        "skipped": False,
                        "message": "OK",
                        "load_case_id": "LC1",
                    }
                ],
                "errors": [],
                "warnings": [],
            }
        ],
    }
    ok = CallToolResult(
        content=[TextContent(type="text", text=json.dumps(body_obj))],
        is_error=False,
    )

    async def body() -> None:
        result = await m._process_success(
            ok,
            tool="idea_native_calculate",
            design_code=_DESIGN_CODE,
            route="native",
            load_map_confirmed=True,
            store=store,
            **_store_kwargs(),
        )
        assert result.raw.route == "native"
        assert result.raw.offline_stub is False
        assert len(result.raw.connections) == 1
        assert result.raw.connections[0].name == "CON1"
        assert result.verdicts.draft is False
        assert result.raw_envelope.kind == "harness.idea_check_raw/1"
        assert result.verdict_envelope.kind == "verdicts.set/1"
        assert result.raw_envelope.summary["route"] == "native"
        assert result.raw_envelope.summary["connections"] == 1

    anyio.run(body)


def test_process_success_unexpected_shape_exact_literals(tmp_path: Any) -> None:
    """AC12: unexpected shape uses exact message, host_method=tool, retryable=False."""
    store = _store(tmp_path)
    bad = CallToolResult(
        content=[TextContent(type="text", text='{"unexpected":true}')],
        is_error=False,
    )

    async def body() -> None:
        with pytest.raises(ContractError) as raised:
            await m._process_success(
                bad,
                tool="idea_get_check_results",
                design_code=_DESIGN_CODE,
                route="rest",
                load_map_confirmed=False,
                store=store,
                **_store_kwargs(),
            )
        detail = raised.value.detail
        assert detail.code is ErrorCode.HOST_ERROR
        assert detail.host_code == "UNEXPECTED_REPLY"
        assert detail.host_method == "idea_get_check_results"
        assert detail.message == "the host reply is not a valid harness.idea_check_raw/1"
        assert detail.retryable is False

    anyio.run(body)


def test_require_service_reachable_exact_messages_and_call_shape() -> None:
    """AC11: idea_status READ; exact HOST_NOT_CONNECTED messages for each failure branch."""
    calls: list[tuple[Any, ...]] = []

    class _Sessions:
        def __init__(self, result: Any) -> None:
            self._result = result

        async def call(self, server: str, role: str, tool: str, args: dict[str, Any], effect: CallEffect) -> Any:
            calls.append((server, role, tool, dict(args), effect))
            return self._result

    async def body() -> None:
        calls.clear()
        await m._require_service_reachable(
            sessions=_Sessions(_status_result(reachable=True)),
            server="idea",
            role="main",
        )
        assert calls == [("idea", "main", "idea_status", {}, CallEffect.READ)]

        with pytest.raises(ContractError) as err:
            await m._require_service_reachable(
                sessions=_Sessions(_status_result(reachable=True, is_error=True)),
                server="idea",
                role="main",
            )
        assert err.value.detail.code is ErrorCode.HOST_NOT_CONNECTED
        assert err.value.detail.message == "idea_status failed"

        with pytest.raises(ContractError) as nobody:
            await m._require_service_reachable(
                sessions=_Sessions(_status_result(reachable=True, empty=True)),
                server="idea",
                role="main",
            )
        assert nobody.value.detail.code is ErrorCode.HOST_NOT_CONNECTED
        assert nobody.value.detail.message == "idea_status returned no body"

        with pytest.raises(ContractError) as down:
            await m._require_service_reachable(
                sessions=_Sessions(_status_result(reachable=False)),
                server="idea",
                role="main",
            )
        assert down.value.detail.code is ErrorCode.HOST_NOT_CONNECTED
        assert down.value.detail.message == "IDEA Connection REST service is not reachable"

        with pytest.raises(ContractError) as bad_service:
            await m._require_service_reachable(
                sessions=_Sessions(_status_result(reachable=None)),
                server="idea",
                role="main",
            )
        assert bad_service.value.detail.code is ErrorCode.HOST_NOT_CONNECTED
        assert bad_service.value.detail.message == "IDEA Connection REST service is not reachable"

    anyio.run(body)


def test_calculate_native_success_tool_args_effect_and_route(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """AC12: calculate_native calls idea_native_calculate READ with save false; process gets route=native."""
    from pathlib import Path
    from types import SimpleNamespace

    calls: list[tuple[Any, ...]] = []
    process_kwargs: list[dict[str, Any]] = []
    sentinel = SimpleNamespace(marker="native-ok")

    class _Sessions:
        async def call(self, server: str, role: str, tool: str, args: dict[str, Any], effect: CallEffect) -> Any:
            calls.append((server, role, tool, dict(args), effect))
            return SimpleNamespace(is_error=False)

    async def _fake_process(result: Any, **kwargs: Any) -> Any:
        process_kwargs.append(dict(kwargs))
        return sentinel

    monkeypatch.setattr(m, "_process_success", _fake_process)
    work = Path(tmp_path) / "model.ideaCon"
    work.write_bytes(b"native-model")

    async def body() -> None:
        out: Any = await m.calculate_native(
            sessions=_Sessions(),
            server="idea",
            role="main",
            path=work,
            connection_id="CON1",
            design_code=_DESIGN_CODE,
            load_map_confirmed=True,
            store=_store(tmp_path),
            ids=SeededIdSource(b"nat-ok", FixedClock(_START)),
            provenance=_provenance(),
        )
        assert out is sentinel

    anyio.run(body)
    assert len(calls) == 1
    server, role, tool, args, effect = calls[0]
    assert server == "idea"
    assert role == "main"
    assert tool == "idea_native_calculate"
    assert effect is CallEffect.READ
    assert args["save"] is False
    assert args["path"] == str(work)
    assert args["connection_id"] == "CON1"
    assert "out_path" not in args
    assert len(process_kwargs) == 1
    assert process_kwargs[0]["tool"] == "idea_native_calculate"
    assert process_kwargs[0]["route"] == "native"
    assert process_kwargs[0]["design_code"] == _DESIGN_CODE
    assert process_kwargs[0]["load_map_confirmed"] is True


def test_calculate_native_error_raises_host(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """AC12: calculate_native error path calls _raise_host with tool + CallEffect.READ."""
    from pathlib import Path
    from types import SimpleNamespace

    raise_kwargs: list[dict[str, Any]] = []

    class _Sessions:
        async def call(self, *_a: Any, **_k: Any) -> Any:
            return SimpleNamespace(is_error=True)

    def _fake_raise(result: Any, **kwargs: Any) -> None:
        raise_kwargs.append(dict(kwargs))
        raise ContractError(
            ErrorCode.HOST_ERROR, "mapped", retryable=False, host_code="idea_error", host_method=kwargs["tool"]
        )

    monkeypatch.setattr(m, "_raise_host", _fake_raise)
    work = Path(tmp_path) / "model.ideaCon"
    work.write_bytes(b"native-model")

    async def body() -> None:
        with pytest.raises(ContractError) as raised:
            await m.calculate_native(
                sessions=_Sessions(),
                server="idea",
                role="main",
                path=work,
                connection_id=None,
                design_code=_DESIGN_CODE,
                load_map_confirmed=False,
                store=_store(tmp_path),
                ids=SeededIdSource(b"nat-err", FixedClock(_START)),
                provenance=_provenance(),
            )
        assert raised.value.detail.host_method == "idea_native_calculate"

    anyio.run(body)
    assert len(raise_kwargs) == 1
    assert raise_kwargs[0]["tool"] == "idea_native_calculate"
    assert raise_kwargs[0]["effect"] is CallEffect.READ


def test_calculate_rest_success_tool_args_effect_and_route(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """AC11/AC12: calculate_rest preflight then idea_calculate WRITE; process gets route=rest."""
    from types import SimpleNamespace

    calls: list[tuple[Any, ...]] = []
    process_kwargs: list[dict[str, Any]] = []
    preflight: list[int] = []
    sentinel = SimpleNamespace(marker="rest-ok")

    class _Sessions:
        async def call(self, server: str, role: str, tool: str, args: dict[str, Any], effect: CallEffect) -> Any:
            calls.append((server, role, tool, dict(args), effect))
            return SimpleNamespace(is_error=False)

    async def _fake_preflight(**_kwargs: Any) -> None:
        preflight.append(1)

    async def _fake_process(result: Any, **kwargs: Any) -> Any:
        process_kwargs.append(dict(kwargs))
        return sentinel

    monkeypatch.setattr(m, "_require_service_reachable", _fake_preflight)
    monkeypatch.setattr(m, "_process_success", _fake_process)

    async def body() -> None:
        out: Any = await m.calculate_rest(
            sessions=_Sessions(),
            server="idea",
            role="main",
            connection_ids=[1, 2],
            design_code=_DESIGN_CODE,
            load_map_confirmed=False,
            approved=True,
            store=_store(tmp_path),
            ids=SeededIdSource(b"rest-ok", FixedClock(_START)),
            provenance=_provenance(),
        )
        assert out is sentinel

    anyio.run(body)
    assert preflight == [1]
    assert len(calls) == 1
    _server, _role, tool, args, effect = calls[0]
    assert tool == "idea_calculate"
    assert effect is CallEffect.WRITE
    assert args["connection_ids"] == [1, 2]
    assert args["confirm"] is True
    assert process_kwargs[0]["tool"] == "idea_calculate"
    assert process_kwargs[0]["route"] == "rest"
    assert process_kwargs[0]["route"] is not None
    assert process_kwargs[0]["load_map_confirmed"] is False


def test_calculate_rest_error_raises_host_write(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """AC11: calculate_rest error path calls _raise_host with WRITE effect and idea_calculate tool."""
    from types import SimpleNamespace

    raise_kwargs: list[dict[str, Any]] = []

    class _Sessions:
        async def call(self, *_a: Any, **_k: Any) -> Any:
            return SimpleNamespace(is_error=True)

    async def _fake_preflight(**_kwargs: Any) -> None:
        return None

    def _fake_raise(result: Any, **kwargs: Any) -> None:
        raise_kwargs.append(dict(kwargs))
        raise ContractError(ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, "timeout", op_id="x")

    monkeypatch.setattr(m, "_require_service_reachable", _fake_preflight)
    monkeypatch.setattr(m, "_raise_host", _fake_raise)

    async def body() -> None:
        with pytest.raises(ContractError):
            await m.calculate_rest(
                sessions=_Sessions(),
                server="idea",
                role="main",
                connection_ids=[9],
                design_code=_DESIGN_CODE,
                load_map_confirmed=True,
                approved=False,
                store=_store(tmp_path),
                ids=SeededIdSource(b"rest-err", FixedClock(_START)),
                provenance=_provenance(),
            )

    anyio.run(body)
    assert raise_kwargs[0]["tool"] == "idea_calculate"
    assert raise_kwargs[0]["effect"] is CallEffect.WRITE


def test_get_check_results_success_with_and_without_connection_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """AC11: get_check_results uses idea_get_check_results READ; route=rest; optional connection_id."""
    from types import SimpleNamespace

    calls: list[tuple[Any, ...]] = []
    process_kwargs: list[dict[str, Any]] = []
    sentinel = SimpleNamespace(marker="get-ok")

    class _Sessions:
        async def call(self, server: str, role: str, tool: str, args: dict[str, Any], effect: CallEffect) -> Any:
            calls.append((server, role, tool, dict(args), effect))
            return SimpleNamespace(is_error=False)

    async def _fake_preflight(**_kwargs: Any) -> None:
        return None

    async def _fake_process(result: Any, **kwargs: Any) -> Any:
        process_kwargs.append(dict(kwargs))
        return sentinel

    monkeypatch.setattr(m, "_require_service_reachable", _fake_preflight)
    monkeypatch.setattr(m, "_process_success", _fake_process)

    async def body() -> None:
        store = _store(tmp_path)
        ids = SeededIdSource(b"get-ok", FixedClock(_START))
        out: Any = await m.get_check_results(
            sessions=_Sessions(),
            server="idea",
            role="main",
            connection_id=3,
            design_code=_DESIGN_CODE,
            load_map_confirmed=True,
            store=store,
            ids=ids,
            provenance=_provenance(),
        )
        assert out is sentinel
        out2: Any = await m.get_check_results(
            sessions=_Sessions(),
            server="idea",
            role="main",
            connection_id=None,
            design_code=_DESIGN_CODE,
            load_map_confirmed=False,
            store=store,
            ids=ids,
            provenance=_provenance(),
        )
        assert out2 is sentinel

    anyio.run(body)
    assert len(calls) == 2
    assert calls[0][2] == "idea_get_check_results"
    assert calls[0][4] is CallEffect.READ
    assert calls[0][3] == {"connection_id": 3}
    assert calls[1][2] == "idea_get_check_results"
    assert calls[1][4] is CallEffect.READ
    assert calls[1][3] == {}
    assert process_kwargs[0]["tool"] == "idea_get_check_results"
    assert process_kwargs[0]["route"] == "rest"
    assert process_kwargs[1]["route"] == "rest"
    assert process_kwargs[0]["route"] is not None


def test_get_check_results_error_raises_host_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """AC11: get_check_results error path calls _raise_host with READ and idea_get_check_results."""
    from types import SimpleNamespace

    raise_kwargs: list[dict[str, Any]] = []

    class _Sessions:
        async def call(self, *_a: Any, **_k: Any) -> Any:
            return SimpleNamespace(is_error=True)

    async def _fake_preflight(**_kwargs: Any) -> None:
        return None

    def _fake_raise(result: Any, **kwargs: Any) -> None:
        raise_kwargs.append(dict(kwargs))
        raise ContractError(ErrorCode.HOST_ERROR, "mapped", retryable=False, host_code="idea_error")

    monkeypatch.setattr(m, "_require_service_reachable", _fake_preflight)
    monkeypatch.setattr(m, "_raise_host", _fake_raise)

    async def body() -> None:
        with pytest.raises(ContractError):
            await m.get_check_results(
                sessions=_Sessions(),
                server="idea",
                role="main",
                connection_id=1,
                design_code=_DESIGN_CODE,
                load_map_confirmed=True,
                store=_store(tmp_path),
                ids=SeededIdSource(b"get-err", FixedClock(_START)),
                provenance=_provenance(),
            )

    anyio.run(body)
    assert raise_kwargs[0]["tool"] == "idea_get_check_results"
    assert raise_kwargs[0]["effect"] is CallEffect.READ


def test_calculate_rest_without_approval_omits_confirm(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """AC11: approved=False → idea_calculate args omit confirm; still WRITE + route rest."""
    from types import SimpleNamespace

    calls: list[dict[str, Any]] = []

    class _Sessions:
        async def call(self, server: str, role: str, tool: str, args: dict[str, Any], effect: CallEffect) -> Any:
            calls.append({"tool": tool, "args": dict(args), "effect": effect})
            return SimpleNamespace(is_error=False)

    async def _fake_preflight(**_kwargs: Any) -> None:
        return None

    async def _fake_process(result: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(route=kwargs["route"], tool=kwargs["tool"])

    monkeypatch.setattr(m, "_require_service_reachable", _fake_preflight)
    monkeypatch.setattr(m, "_process_success", _fake_process)

    async def body() -> None:
        result: Any = await m.calculate_rest(
            sessions=_Sessions(),
            server="idea",
            role="main",
            connection_ids=[5],
            design_code=_DESIGN_CODE,
            load_map_confirmed=True,
            approved=False,
            store=_store(tmp_path),
            ids=SeededIdSource(b"rest-no-confirm", FixedClock(_START)),
            provenance=_provenance(),
        )
        assert result.route == "rest"
        assert result.tool == "idea_calculate"

    anyio.run(body)
    assert calls[0]["tool"] == "idea_calculate"
    assert calls[0]["effect"] is CallEffect.WRITE
    assert calls[0]["args"] == {"connection_ids": [5]}
    assert "confirm" not in calls[0]["args"]


def test_process_success_route_mismatch_unexpected(tmp_path: Any) -> None:
    """AC11: host route native on a rest call is UNEXPECTED_REPLY; failure evidence stored."""
    store = _store(tmp_path)
    body = {
        "route": "native",
        "backend": "file",
        "offline_stub": False,
        "connections": [_connection()],
    }
    reply = CallToolResult(content=[TextContent(type="text", text=__import__("json").dumps(body))], is_error=False)

    async def run() -> None:
        with pytest.raises(ContractError) as raised:
            await m._process_success(
                reply,
                tool="idea_calculate",
                design_code=_DESIGN_CODE,
                route="rest",
                load_map_confirmed=False,
                store=store,
                **_store_kwargs(),
            )
        assert raised.value.detail.host_code == "UNEXPECTED_REPLY"

    anyio.run(run)


def test_verdicts_from_connections_errors_keep_fail_checks() -> None:
    """AC12 additive: connection with errors and a FAIL check keeps FAIL and adds ERROR."""
    rows = [
        _connection(
            name="CON1",
            passed=False,
            checks=[_check("Plates", 150.0, status=False)],
            errors=["kernel failed"],
        )
    ]
    payload = m._verdicts_from_connections(
        rows,
        design_code=_DESIGN_CODE,
        route="native",
        load_map_confirmed=True,
    )
    assert any(v.status is VerdictStatus.FAIL for v in payload.verdicts)
    assert any(v.check_id == "idea:connection" and v.status is VerdictStatus.ERROR for v in payload.verdicts)


def test_verdicts_from_connections_mixed_error_uncalculated() -> None:
    """AC12: calculated+errors with sibling uncalculated keeps ERROR (not PRECONDITION_FAILED)."""
    rows = [
        _connection(name="BAD", calculated=True, checks=[], errors=["kernel failed"]),
        _connection(name="PENDING", calculated=False, checks=[], errors=[]),
    ]
    payload = m._verdicts_from_connections(
        rows,
        design_code=_DESIGN_CODE,
        route="native",
        load_map_confirmed=True,
    )
    assert any(v.status is VerdictStatus.ERROR for v in payload.verdicts)


def test_calculate_rest_passes_op_id_on_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """AC18: calculate_rest forwards op_id to _raise_host for TIMEOUT_UNKNOWN_OUTCOME."""
    from types import SimpleNamespace

    raise_kwargs: list[dict[str, Any]] = []

    class _Sessions:
        async def call(self, *_a: Any, **_k: Any) -> Any:
            return SimpleNamespace(is_error=True)

    async def _fake_preflight(**_kwargs: Any) -> None:
        return None

    def _fake_raise(result: Any, **kwargs: Any) -> None:
        raise_kwargs.append(dict(kwargs))
        raise ContractError(ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, "timeout", op_id=kwargs.get("op_id", ""))

    monkeypatch.setattr(m, "_require_service_reachable", _fake_preflight)
    monkeypatch.setattr(m, "_raise_host", _fake_raise)

    async def body() -> None:
        with pytest.raises(ContractError) as raised:
            await m.calculate_rest(
                sessions=_Sessions(),
                server="idea",
                role="main",
                connection_ids=[1],
                design_code=_DESIGN_CODE,
                load_map_confirmed=True,
                approved=True,
                store=_store(tmp_path),
                ids=SeededIdSource(b"rest-op", FixedClock(_START)),
                provenance=_provenance(),
                op_id="op_from_caller",
            )
        assert raised.value.detail.op_id == "op_from_caller"

    anyio.run(body)
    assert raise_kwargs[0]["op_id"] == "op_from_caller"


@pytest.mark.parametrize("route", ["native", "rest"])
@pytest.mark.parametrize("extras", [(), ("host text",)])
def test_assumptions_match_verdicts_module(route: str, extras: tuple[str, ...]) -> None:
    """The REST assumption strings duplicated from `_verdicts` must stay identical (spec 0014 AC12, AC15)."""
    from eng_harness.adapters.idea import _verdicts

    assert m._assumptions(route=route, extras=extras) == _verdicts._assumptions(route=route, extras=extras)


def test_file_source_read_error_is_contract_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """0002 §4.5.3: an unreadable native file is refused as ContractError on `path`, never a bare OSError."""
    from pathlib import Path

    work = tmp_path / "locked.ideaCon"
    work.write_bytes(b"locked")

    def _deny(self: Path) -> bytes:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_bytes", _deny)
    with pytest.raises(ContractError) as raised:
        m._file_source(work)
    assert raised.value.detail.code is ErrorCode.PRECONDITION_FAILED
    assert raised.value.detail.field == "path"
    assert str(tmp_path) not in raised.value.detail.message
