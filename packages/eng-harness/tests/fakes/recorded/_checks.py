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


def fidelity_problems(host: RecordedHost, run_dir: Path) -> list[str]:
    """Replay the recorded requests on a fresh synthetic fake and compare reply shape and error codes (AC34)."""
    problems: list[str] = []
    for exchange, answer in replay_on_fake(host, run_dir):
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


def _call_problems(exchange: Exchange, store: ResultStore, clock: FixedClock, ids: SeededIdSource) -> list[str]:
    label = f"{exchange.seq} {exchange.tool}"
    allowlist = csi_allowlist().for_product("ETABS")
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
        binding = Binding(target=HostTarget(product="ETABS", pid=1), units_system=TOKENS.get(exchange.tool))
        payload, summary = reader(body, binding)
        envelope = make_envelope(
            store, tool=f"csi/{exchange.tool}", kind=str(allowlist.descriptor(exchange.tool).result_kind),
            payload=payload, summary=summary, reply=body, check=_CHECK, host=None, inputs={},
            started_at=clock.now(), duration_ms=0,
        )  # fmt: skip
    except (ContractError, ValueError, KeyError) as error:
        return [f"{label}: the adapter cannot read the reply: {error}"]
    return [] if isinstance(envelope, SuccessEnvelope) else [f"{label}: no success envelope"]


def _state_problems(host: RecordedHost) -> list[str]:
    """Run the adapter's model-state read over the recording when it holds the read of `csi_model_info`."""
    first = next((e for e in host.calls if e.tool == "csi_model_info" and e.result is not None), None)
    if first is None:
        return []
    pid = first.arguments["target"]["pid"]
    path = (_body(first.result or {}) or {}).get("model_path")
    replay = RecordedHost(host.directory)
    reader = CsiStateReader(product="ETABS", call=replay.host_call)
    try:
        anyio.run(reader.read, pid, Path(path) if isinstance(path, str) else None)
    except (AssertionError, ContractError) as error:
        return [f"model-state read: {error}"]
    return []


def adapter_problems(host: RecordedHost, workspace: Path) -> list[str]:
    """The adapter on a recording (AC34): the tool-list fingerprint, every recorded reply, the model-state read."""
    allowlist = csi_allowlist().for_product("ETABS")
    listed = {n: s for n, s in host.tool_schemas.items() if n in allowlist.tool_names}
    problems: list[str] = []
    if host.manifest["tool_fingerprint"] != tool_list_fingerprint(listed):
        problems.append("the manifest's tool fingerprint is not that of the recorded tool list")
    if host.manifest["tool_fingerprint"] != allowlist.tool_fingerprint:
        problems.append("the recorded tool fingerprint is not the allowlist's")
    store, clock, ids = _store(workspace)
    for exchange in host.calls:
        problems += _call_problems(exchange, store, clock, ids)
    return problems + _state_problems(host)
