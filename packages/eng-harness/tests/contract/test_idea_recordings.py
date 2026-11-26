"""Spec 0014 AC21 and spec 0002 §4.8: IDEA's recorded adapter contract and fake fidelity."""

import hashlib
import json
import sys
from argparse import Namespace
from contextlib import closing
from functools import partial
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from fakes.recorded import RecordedHost
from fakes.recorded._checks import _body, committed_recordings, shape_differences
from fakes.sasaah_idea.test_server import SERVER, Rpc, make_ideacon
from workflow.adapters.test_idea_calculate import _DESIGN_CODE, _idea_config, _provenance, _store

from eng_harness.adapters.idea import _checks, _loads, _replies, idea_allowlist
from eng_harness.adapters.idea._calculate import _process_success, _raise_host
from eng_harness.adapters.idea._errors import IDEA_ERROR_TABLE, IDEA_HOST_ERROR_CODES
from eng_harness.servers import CallEffect
from eng_harness.servers._buildcheck import tool_list_fingerprint

_ADAPTER = "sasaah-idea-mcp"
_CALCULATIONS = {"idea_native_calculate", "idea_calculate", "idea_get_check_results"}
_PACKAGE = Path(__file__).resolve().parents[2]


def _recording_params() -> list[pytest.ParameterSet]:
    committed = [
        pytest.param(path, id=path.name, marks=pytest.mark.recorded)
        for path in committed_recordings()
        if json.loads((path / "manifest.json").read_text(encoding="utf-8"))["adapter"] == _ADAPTER
    ]
    return [
        pytest.param("native", id="synthetic-native", marks=pytest.mark.synthetic),
        pytest.param("rest", id="synthetic-rest", marks=pytest.mark.synthetic),
        *committed,
    ]


def _record_synthetic(root: Path, route: str) -> Path:
    # Exercise the T9 acceptance recorder itself. Its absence is the red case before T9.
    assert (_PACKAGE / "acceptance" / "scripts" / "record_idea.py").is_file(), (
        "the IDEA record-mode scenario is missing"
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(_PACKAGE))
        from acceptance.scripts.record_idea import _record

    control = root / "control.json"
    server = _idea_config(root, control, route=route).servers["idea"]
    # Launch the Python fake directly so recording exercises the platform transport on Windows as well.
    exe = Path(sys.executable)
    pin = server.build.model_copy(update={"exe_sha256": hashlib.sha256(exe.read_bytes()).hexdigest()})
    server = server.model_copy(
        update={
            "command": str(exe),
            "args": (str(SERVER), *server.args),
            "env": {"SASAAH_IDEA_FAKE_CONTROL": str(control)},
            "build": pin,
        }
    )
    model = make_ideacon(root / "joint.ideaCon")
    loads = None
    if route == "native":
        loads = root / "loads.json"
        source = json.loads(model.read_text(encoding="utf-8"))
        loads.write_text(json.dumps(source["connections"][0]["loads"]), encoding="utf-8")
    args = Namespace(
        model=model,
        out=root / "recordings",
        connection="CON1" if route == "native" else "1",
        calculate=True,
        apply_loads=loads,
    )
    run = root / "run"
    run.mkdir()
    return anyio.run(_record, server, route, args, run)


@pytest.fixture(scope="module", params=_recording_params())
def recording(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> RecordedHost:
    case = request.param
    if isinstance(case, Path):
        return RecordedHost(case)
    return RecordedHost(_record_synthetic(tmp_path_factory.mktemp(f"recorded-idea-{case}"), case))


def test_adapter_on_recordings(recording: RecordedHost, tmp_path: Path) -> None:
    allow = idea_allowlist()
    clock = FixedClock(1_700_000_000_000, 1)
    ids = SeededIdSource(b"idea-recordings", clock)
    store = _store(tmp_path)
    host = recording
    schemas = {name: schema for name, schema in host.tool_schemas.items() if name in allow.tool_names}
    assert tool_list_fingerprint(schemas) == host.manifest["tool_fingerprint"] == allow.tool_fingerprint
    assert host.calls
    for exchange in host.calls:
        tool, reply = exchange.tool, exchange.result
        label = f"{host.directory.name}: {exchange.seq} {tool}"
        descriptor = allow.descriptor(tool)
        assert reply is not None, (label, exchange.error)
        if reply.get("isError"):
            body = _body(reply)
            code = body.get("code") if isinstance(body, dict) else None
            effect = CallEffect(descriptor.effect)
            with pytest.raises(ContractError) as failure:
                _raise_host(reply, tool=tool, effect=effect, ids=ids, op_id="recorded")
            if code in IDEA_ERROR_TABLE:
                row = IDEA_ERROR_TABLE[code]
                assert failure.value.detail.code == (row.write if effect is CallEffect.WRITE else row.read), label
            elif code in IDEA_HOST_ERROR_CODES:
                assert failure.value.detail.code == ErrorCode.HOST_ERROR, label
                assert failure.value.detail.host_code == code, label
            else:
                assert code is None, label
            continue
        body = _replies.parse_reply_json(reply)
        if tool in _CALCULATIONS:
            try:
                mapped = anyio.run(
                    partial(
                        _process_success,
                        reply,
                        tool=tool,
                        route="native" if tool == "idea_native_calculate" else "rest",
                        design_code=_DESIGN_CODE,
                        load_map_confirmed=False,
                        store=store,
                        provenance=_provenance(),
                        inputs={},
                        files=(),
                        started_at=clock.now(),
                        duration_ms=0,
                    )
                )
            except ContractError as failure:
                if failure.detail.host_code != "OFFLINE_STUB" and not (
                    failure.detail.code == ErrorCode.PRECONDITION_FAILED
                    and failure.detail.precondition == "analysis_current"
                ):
                    raise AssertionError(label) from failure
            else:
                assert mapped.verdict_envelope.kind == "verdicts.set/1", label
        elif tool == "idea_status":
            _replies.parse_status({key: body[key] for key in ("installed", "service", "read_only", "script_enabled")})
        elif tool in ("idea_open_project", "idea_list_connections"):
            keys = ("backend", "service_reachable", "live_project", "connections")
            _replies.parse_project({key: body[key] for key in keys if key in body})
        elif tool == "idea_native_get_loads":
            _loads.host_loads_to_canonical(connection=body["connection"], effects=body["loads"], file_sha256="0" * 64)
        elif tool == "idea_native_set_loads":
            _checks.issues_from_set_loads_reply(body, connection=body["connection"])
        else:
            assert tool == "idea_close_project", label


def _connection_seed(host: RecordedHost) -> dict[str, list[dict[str, Any]]]:
    # REST does not expose loading. Seed only observed case names so the fake can return
    # a case reference for a loaded connection while still calculating its own checks.
    case_names: dict[int, str] = {}
    for exchange in host.calls:
        if exchange.tool != "idea_calculate" or not exchange.result or exchange.result.get("isError"):
            continue
        for connection in _body(exchange.result).get("connections", []):
            for check in connection.get("checks", []):
                if isinstance(name := check.get("load_case_id"), str):
                    case_names.setdefault(connection["connection_id"], name)

    seeds: dict[str, list[dict[str, Any]]] = {}
    for exchange in host.calls:
        path = exchange.arguments.get("path")
        if not isinstance(path, str) or not exchange.result or exchange.result.get("isError"):
            continue
        body = _body(exchange.result)
        if exchange.tool == "idea_open_project" and body["connections"]:
            connections = [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "loads": [{"name": case_names[c["id"]]}] if c["id"] in case_names else [],
                }
                for c in body["connections"]
            ]
            seeds.setdefault(path, connections)
        elif exchange.tool == "idea_native_get_loads" and "loads" in body:
            seeds.setdefault(path, [{"id": body["connection_id"], "name": body["connection"], "loads": body["loads"]}])
    return seeds


def test_synthetic_matches_recordings(recording: RecordedHost, tmp_path: Path) -> None:
    host = recording
    root = tmp_path / "fake"
    root.mkdir()
    paths: dict[str, Path] = {}
    seeds = _connection_seed(host)
    with closing(Rpc(root / "control.json")) as fake:
        for exchange in host.calls:
            args: dict[str, Any] = dict(exchange.arguments)
            for key in ("path", "out_path"):
                if isinstance(value := args.get(key), str) and value:
                    local = paths.setdefault(value, root / f"model-{len(paths)}.ideaCon")
                    if key == "path" and not local.exists():
                        make_ideacon(local, connections=seeds.get(value))
                    args[key] = str(local)
            label = f"{host.directory.name}: {exchange.seq} {exchange.tool}"
            assert exchange.result is not None, (label, exchange.error)
            recorded = _body(exchange.result)
            is_error, synthetic = fake.call(exchange.tool, **args)
            assert is_error == bool(exchange.result.get("isError")), label
            assert shape_differences(recorded, synthetic) == [], label
            if is_error:
                assert synthetic.get("code") == recorded.get("code"), label
