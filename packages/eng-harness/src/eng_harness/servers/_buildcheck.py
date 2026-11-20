"""Build check of a Sasaah server (plan 0002 T6b; spec 0002 section 4.3.4, AC9, AC10).

A mismatch is `ServerCheck(ok=False)` with the first reason, never an exception (the engine stops the run). No units.
"""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eng_contract.canonical import payload_sha256
from mcp import types

from eng_harness.ports import ServerCheck
from eng_harness.servers._config import BuildPin

# Hidden by the required start options; `csi_db_tables_apply` is always listed (S12-G7), tolerated, never callable.
# IDEA: `idea_run_script` is hidden by `--disable-script` (spec 0014 section 4.3 item 4).
_HATCH = re.compile(r"csi_(run_script|invoke|object_\w+)|idea_run_script")


@dataclass(frozen=True)
class BuildExpectation:
    """What an adapter allowlist pins about the server build (header of spec 4.5.1)."""

    sasaah_commit: str
    also_tested_commits: tuple[str, ...]
    tool_fingerprint: str  # over the tools that list `product` (spec 0008 4.1)
    tool_names: frozenset[str]  # every allowlisted tool of `product`, whatever its route
    product: str  # the product the allowlist was loaded for
    status_tool: str = "csi_status"  # status tool the build check calls (spec 0014 AC3: idea_status)


@dataclass(frozen=True)
class Observed:
    """Facts read off a started server; `tools` is name to schema, `status` is the status-tool reply."""

    exe_sha256: str
    server_info: types.Implementation | None
    tools: Mapping[str, Any]
    status: Mapping[str, Any]


def _strip(node: Any, names: bool = False) -> Any:
    """Drop `description` and `title` members holding a string; `names` marks a `properties` object."""
    if isinstance(node, list):
        return [_strip(item) for item in node]
    if not isinstance(node, dict):
        return node
    return {
        key: _strip(value, key == "properties" and not names)
        for key, value in node.items()
        if names or not (key in ("description", "title") and isinstance(value, str))
    }


def tool_list_fingerprint(schemas: Mapping[str, Any]) -> str:
    """SHA-256 (hex) over the tools sorted by name, each with its description-free input schema (canonical JSON)."""
    return payload_sha256([{"name": n, "input_schema": _strip(schemas[n])} for n in sorted(schemas)])


def check_build(
    server: str, pin: BuildPin, want: BuildExpectation, seen: Observed, minimum: str = "", *, product: str
) -> ServerCheck:
    """Compare a started server with the build its adapter was tested with (spec 4.3.4 items 1 to 5).

    `minimum` is the workflow's minimum Sasaah commit ("" for none), met by the allowlist's or a tested commit.
    `product` is the server's product: the expectation must have been loaded for it (a SAFE server is never checked
    against the ETABS fingerprint). The result is `ok`, or not `ok` with the first reason.
    """
    fingerprint = tool_list_fingerprint({n: s for n, s in seen.tools.items() if n in want.tool_names})
    version = seen.server_info.version if seen.server_info else None
    missing = sorted(want.tool_names - seen.tools.keys())
    hatch = sorted(n for n in seen.tools if _HATCH.fullmatch(n))
    tested = (want.sasaah_commit, *want.also_tested_commits)
    flags = [f for f in ("read_only", "script_enabled") if seen.status.get(f) is not False]
    try:
        addin_hashes = tuple(hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in pin.addin_paths)
    except OSError:
        addin_hashes = ()
    failures = [
        (addin_hashes != pin.addin_sha256, "add-in SHA-256 differs from the pinned build or cannot be read"),
        (want.product != product, f"the allowlist is for {want.product}, the server's product is {product}"),
        (seen.exe_sha256 != pin.exe_sha256, "executable SHA-256 differs from the pinned build"),
        (pin.server_info_version not in (None, version), "serverInfo version is not the pinned one"),
        (pin.sasaah_commit != want.sasaah_commit, "the pinned Sasaah commit is not the allowlist's commit"),
        (bool(minimum) and minimum not in tested, "the workflow's minimum build was not tested with the allowlist"),
        (bool(missing), f"allowlisted tool {', '.join(missing)} is not listed"),
        (bool(hatch), f"{', '.join(hatch)} is listed: the start options failed"),
        (fingerprint != want.tool_fingerprint, "tool-list fingerprint differs from the allowlist's"),
        (bool(flags), f"{want.status_tool} {' and '.join(flags)} is not false"),
    ]
    reason = next((why for failed, why in failures if failed), None)
    build = f"{pin.sasaah_commit[:12]}+{seen.exe_sha256[:12]}"
    return ServerCheck(
        server=server,
        build=build,
        min_build=minimum,
        fingerprint=fingerprint,
        expected_fingerprint=want.tool_fingerprint,
        ok=reason is None,
        reason=reason,
    )
