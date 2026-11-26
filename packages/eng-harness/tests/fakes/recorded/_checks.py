"""What a recording must satisfy (plan 0002 T17; spec 0002 AC34, section 4.8.2): the adapter's side and the fake's.

Each check returns the list of problems it found (empty when the recording is fine), so that a test can also show
that a doctored recording is caught.
"""

import json
from pathlib import Path
from typing import Any

import anyio
from eng_contract.envelope import SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._envelope import make_envelope, parse_reply
from eng_harness.adapters._errors import parse_error_reply
from eng_harness.adapters._toolport import Binding
from eng_harness.adapters.csi import csi_allowlist
from eng_harness.adapters.csi._errors import CSI_ERROR_TABLE, CsiErrorMapper
from eng_harness.adapters.csi._state import CsiStateReader
from eng_harness.adapters.csi._tools import READERS, TOKENS
from eng_harness.ports import ServerCheck
from eng_harness.servers import CallEffect
from eng_harness.servers._buildcheck import tool_list_fingerprint
from fakes.recorded._host import Exchange, RecordedHost
from fakes.recorded._session import replay_on_fake

RECORDINGS = Path(__file__).resolve().parents[3] / "acceptance" / "recordings"
_CHECK = ServerCheck(
    server="csi", build="recorded", min_build="", fingerprint="", expected_fingerprint="", ok=True, reason=None
)
_ERROR_KEYS = {"code", "message", "data"}  # the Sasaah error reply (S-12 report section 6)


def committed_recordings(root: Path = RECORDINGS) -> list[Path]:
    """The recording folders the owner committed under `root` (those with a manifest), by name."""
    return sorted(manifest.parent for manifest in root.glob("*/manifest.json"))


def applicable_recordings(product: str, root: Path = RECORDINGS) -> list[Path]:
    """Committed recordings whose tool fingerprint is that of `product` (spec 0008 AC28, amendment B-573)."""
    fingerprint = csi_allowlist().for_product(product).tool_fingerprint
    found: list[Path] = []
    for path in committed_recordings(root):
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("tool_fingerprint") == fingerprint:
            found.append(path)
    return found


def shape(value: object) -> object:
    """The structure of a JSON value: object keys, the shape of the first item of a list, the kind of a scalar."""
    if isinstance(value, dict):
        return {key: shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    return "number" if isinstance(value, int | float) else "str"


def shape_differences(recorded: object, synthetic: object, where: str = "") -> list[str]:
    """Where the synthetic reply is not shaped like the recorded one; an empty list on either side is not compared."""
    if isinstance(recorded, dict) and isinstance(synthetic, dict):
        found = [f"{where}.{key}: missing in the synthetic reply" for key in recorded.keys() - synthetic.keys()]
        found += [f"{where}.{key}: not in the recorded reply" for key in synthetic.keys() - recorded.keys()]
        for key in recorded.keys() & synthetic.keys():
            found += shape_differences(recorded[key], synthetic[key], f"{where}.{key}")
        return sorted(found)
    if isinstance(recorded, list) and isinstance(synthetic, list):
        if recorded and synthetic:
            return shape_differences(recorded[0], synthetic[0], f"{where}[]")
        return []
    if shape(recorded) != shape(synthetic):
        return [f"{where}: recorded {shape(recorded)}, synthetic {shape(synthetic)}"]
    return []


def _body(result: dict[str, Any]) -> Any:
    """The JSON of the one text block of a recorded result (`None` for anything else)."""
    blocks = result.get("content") or []
    if len(blocks) != 1 or blocks[0].get("type") != "text":
        return None
    try:
        return json.loads(blocks[0]["text"])
    except ValueError:
        return None


def fidelity_problems(host: RecordedHost, run_dir: Path, *, product: str = "ETABS") -> list[str]:
    """Replay the recorded requests on a fresh synthetic fake and compare reply shape and error codes (AC34 / AC28)."""
    problems: list[str] = []
    for exchange, answer in replay_on_fake(host, run_dir, product=product):
        label = f"{exchange.seq} {exchange.tool}"
        if exchange.result is None:
            continue  # a JSON-RPC error has no reply to compare
        recorded, synthetic = _body(exchange.result), _body(answer)
        if bool(exchange.result.get("isError")) != bool(answer.get("isError")):
            problems.append(
                f"{label}: recorded isError {exchange.result.get('isError')}, synthetic {answer.get('isError')}"
            )
        elif isinstance(recorded, dict) and recorded.get("code") != (synthetic or {}).get("code"):
            problems.append(
                f"{label}: error code {recorded.get('code')} recorded, {(synthetic or {}).get('code')} synthetic"
            )
        else:
            problems += [f"{label}{p}" for p in shape_differences(recorded, synthetic)]
    return problems


def _store(workspace: Path) -> tuple[ResultStore, FixedClock, SeededIdSource]:
    clock = FixedClock(1_767_225_600_000, 1)
    ids = SeededIdSource(b"recorded", clock)
    store = ResultStore(Workspace(root=workspace, classification=LocationClass.LOCAL), HARNESS_KINDS, ids, clock)
    return store, clock, ids


def _call_problems(
    exchange: Exchange, store: ResultStore, clock: FixedClock, ids: SeededIdSource, *, product: str
) -> list[str]:
    label = f"{exchange.seq} {exchange.tool}"
    allowlist = csi_allowlist().for_product(product)
    if exchange.tool not in allowlist.tool_names:
        return [f"{label}: not an allowlisted tool"]
    if exchange.result is None:
        return [f"{label}: recorded as a JSON-RPC error {exchange.error}"]
    if (failure := parse_error_reply(exchange.result)) is not None:
        body = _body(exchange.result)
        if not isinstance(body, dict) or not body.keys() >= _ERROR_KEYS:
            return [f"{label}: an error reply without code, message and data"]
        known = failure.code in CSI_ERROR_TABLE or failure.code == "csi_error"
        mapped = CsiErrorMapper(ids).map(failure, effect=CallEffect(allowlist.descriptor(exchange.tool).effect),
                                         tool=exchange.tool, op_id="recorded")  # fmt: skip
        if not known or (mapped.code is ErrorCode.INTERNAL and failure.code not in CSI_ERROR_TABLE):
            return [f"{label}: the host error code {failure.code} is not in the error table"]
        return []
    try:
        body = parse_reply(exchange.result)
        reader = READERS.get(exchange.tool)
        if reader is None:
            return []
        binding = Binding(target=HostTarget(product=product, pid=1), units_system=TOKENS.get(exchange.tool))
        payload, summary = reader(body, binding)
        envelope = make_envelope(
            store, tool=f"csi/{exchange.tool}", kind=str(allowlist.descriptor(exchange.tool).result_kind),
            payload=payload, summary=summary, reply=body, check=_CHECK, host=None, inputs={},
            started_at=clock.now(), duration_ms=0,
        )  # fmt: skip
    except (ContractError, ValueError, KeyError) as error:
        return [f"{label}: the adapter cannot read the reply: {error}"]
    return [] if isinstance(envelope, SuccessEnvelope) else [f"{label}: no success envelope"]


def _state_problems(host: RecordedHost, *, product: str) -> list[str]:
    """Run the adapter's model-state read over the recording when it holds the read of `csi_model_info`."""
    first = next((e for e in host.calls if e.tool == "csi_model_info" and e.result is not None), None)
    if first is None:
        return []
    pid = first.arguments["target"]["pid"]
    path = (_body(first.result or {}) or {}).get("model_path")
    replay = RecordedHost(host.directory)
    # Profile dispatch (spec 0008 AC2 / 0012 AC8): declared absences → Sap2000StateReader;
    # joint_loads → SafeStateReader; else CsiStateReader. No product-name branch.
    from eng_harness.adapters.csi.products import profile

    prof = profile(product)
    tables = prof.tables
    if prof.declared_absences:
        from eng_harness.adapters.csi.products._sap2000_state import Sap2000StateReader

        reader: Any = Sap2000StateReader(product=product, call=replay.host_call)
    elif "joint_loads" in tables:
        from eng_harness.adapters.csi.products._safe_state import SafeStateReader

        reader = SafeStateReader(product=product, call=replay.host_call)
    else:
        reader = CsiStateReader(product=product, call=replay.host_call)
    try:
        anyio.run(reader.read, pid, Path(path) if isinstance(path, str) else None)
    except (AssertionError, ContractError) as error:
        return [f"model-state read: {error}"]
    return []


def adapter_problems(host: RecordedHost, workspace: Path, *, product: str = "ETABS") -> list[str]:
    """Adapter on a recording (AC34 / AC28): tool-list fingerprint, replies, model-state read."""
    allowlist = csi_allowlist().for_product(product)
    listed = {n: s for n, s in host.tool_schemas.items() if n in allowlist.tool_names}
    problems: list[str] = []
    if host.manifest["tool_fingerprint"] != tool_list_fingerprint(listed):
        problems.append("the manifest's tool fingerprint is not that of the recorded tool list")
    if host.manifest["tool_fingerprint"] != allowlist.tool_fingerprint:
        problems.append("the recorded tool fingerprint is not the allowlist's")
    store, clock, ids = _store(workspace)
    for exchange in host.calls:
        problems += _call_problems(exchange, store, clock, ids, product=product)
    return problems + _state_problems(host, product=product)


def applicable_revit_recordings(root: Path = RECORDINGS) -> list[Path]:
    """Committed recordings whose tool fingerprint is the Revit write-role allowlist's (spec 0011 AC31, B-573)."""
    from eng_harness.adapters.revit import revit_allowlist

    fingerprint = revit_allowlist(role="write").tool_fingerprint
    found: list[Path] = []
    for path in committed_recordings(root):
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("tool_fingerprint") == fingerprint:
            found.append(path)
    return found


def revit_fidelity_problems(host: RecordedHost, run_dir: Path) -> list[str]:
    """Replay recorded Revit requests on a fresh synthetic fake; compare reply shape and error codes (AC31)."""
    from fakes.recorded._session import replay_on_revit_fake

    problems: list[str] = []
    for exchange, answer in replay_on_revit_fake(host, run_dir):
        label = f"{exchange.seq} {exchange.tool}"
        if exchange.result is None:
            continue
        recorded, synthetic = _body(exchange.result), _body(answer)
        if bool(exchange.result.get("isError")) != bool(answer.get("isError")):
            problems.append(
                f"{label}: recorded isError {exchange.result.get('isError')}, synthetic {answer.get('isError')}"
            )
        elif isinstance(recorded, dict) and recorded.get("code") != (synthetic or {}).get("code"):
            # Revit errors are a single text; shape compare covers the success path. Code key only when JSON.
            if "code" in (recorded or {}) or "code" in (synthetic or {}):
                problems.append(
                    f"{label}: error code {recorded.get('code') if isinstance(recorded, dict) else recorded} "
                    f"recorded, {(synthetic or {}).get('code') if isinstance(synthetic, dict) else synthetic} synthetic"
                )
        else:
            problems += [f"{label}{p}" for p in shape_differences(recorded, synthetic)]
    return problems


def _revit_call_problems(exchange: Exchange, ids: SeededIdSource) -> list[str]:
    """Parse one recorded Revit reply through the adapter's parsers (AC31)."""
    from eng_harness.adapters.revit import revit_allowlist
    from eng_harness.adapters.revit._errors import REVIT_ERROR_TABLE, RevitErrorMapper, parse_revit_error_text
    from eng_harness.adapters.revit._replies import parse_revit_reply

    label = f"{exchange.seq} {exchange.tool}"
    allowlist = revit_allowlist(role="write")
    if exchange.tool not in allowlist.tool_names:
        return [f"{label}: not an allowlisted tool"]
    if exchange.result is None:
        return [f"{label}: recorded as a JSON-RPC error {exchange.error}"]
    if exchange.result.get("isError"):
        texts = []
        for block in exchange.result.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                texts.append(block["text"])
        failure = parse_revit_error_text("\n".join(texts))
        mapped = RevitErrorMapper(ids).map(
            failure, effect=CallEffect(allowlist.descriptor(exchange.tool).effect), tool=exchange.tool, op_id="recorded"
        )
        known = failure.code in REVIT_ERROR_TABLE or failure.code is None
        if not known and mapped.code is ErrorCode.INTERNAL:
            return [f"{label}: the host error code {failure.code} is not in the error table"]
        return []
    try:
        parse_revit_reply(exchange.result)
    except (ContractError, ValueError, KeyError) as error:
        return [f"{label}: the adapter cannot read the reply: {error}"]
    return []


def _revit_state_problems(host: RecordedHost) -> list[str]:
    """Run the Revit model-state reader over the recording when it holds a metadata read (AC31)."""
    from eng_harness.adapters.revit._parameters import load_role_map
    from eng_harness.adapters.revit._state import RevitStateReader

    first = next((e for e in host.calls if e.tool == "revit_get_model_metadata" and e.result is not None), None)
    if first is None:
        return []
    path = (_body(first.result or {}) or {}).get("path")
    replay = RecordedHost(host.directory)

    async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
        reply = await replay.call("revit", "read", tool, arguments, effect)
        return reply.model_dump(mode="json", by_alias=True, exclude_none=True)

    reader = RevitStateReader(call=call, role_map=load_role_map({}), catalog_version="recorded")
    bound = Path(path) if isinstance(path, str) else Path("<path>/<model-1>.rvt")

    async def run() -> None:
        await reader.read(bound_path=bound)

    try:
        anyio.run(run)
    except (AssertionError, ContractError, TypeError) as error:
        return [f"model-state read: {error}"]
    return []


def revit_adapter_problems(host: RecordedHost, workspace: Path) -> list[str]:
    """Adapter on a Revit recording (AC31): tool-list fingerprint, replies, model-state read."""
    from eng_harness.adapters.revit import revit_allowlist

    allowlist = revit_allowlist(role="write")
    listed = {n: s for n, s in host.tool_schemas.items() if n in allowlist.tool_names}
    problems: list[str] = []
    if host.manifest["tool_fingerprint"] != tool_list_fingerprint(listed):
        problems.append("the manifest's tool fingerprint is not that of the recorded tool list")
    if host.manifest["tool_fingerprint"] != allowlist.tool_fingerprint:
        problems.append("the recorded tool fingerprint is not the allowlist's")
    _, _, ids = _store(workspace)
    for exchange in host.calls:
        problems += _revit_call_problems(exchange, ids)
    return problems + _revit_state_problems(host)
