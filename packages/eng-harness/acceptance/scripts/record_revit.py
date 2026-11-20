"""Record a session with the real Sasaah Revit server on a COPY of a model (owner only; spec 0011 section 4.13).

    uv run python acceptance/scripts/record_revit.py --config harness.toml --model D:/copies/copy.rvt

Starts the configured Revit server, opens the copy, reads the model state as the adapter does, and leaves the copy
open in Revit (there is no close tool; R-G2). Everything goes through record mode into
`acceptance/recordings/<adapter>-<build>/`; read acceptance/recordings/README.md before committing it.
Exit code 0: recorded; 1: the server refused a step (the recording is written anyway); 2: usage.

Do not run this against a real host from an agent session (AGENTS.md section 10, live acceptance scripts).
"""

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Any

import anyio
from mcp import Client
from mcp.client.stdio import get_default_environment

from eng_harness.adapters.revit import revit_allowlist
from eng_harness.adapters.revit._parameters import load_role_map
from eng_harness.adapters.revit._state import RevitStateReader
from eng_harness.servers import (
    CallEffect,
    Recording,
    RecordMode,
    ServerConfig,
    load_servers_config,
    platform_inspector,
    platform_launcher,
)
from eng_harness.servers._launch_args import launch_argv
from eng_harness.servers._launcher import JobPolicy, LaunchSpec
from eng_harness.servers._session import reply_body
from eng_harness.servers._transport import ProcessTransport


class RefusedError(Exception):
    """The server answered a step with an error reply (it has been recorded by then)."""


async def _body(client: Client, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    reply = await client.call_tool(tool, arguments)
    if (body := reply_body(reply)) is None or reply.is_error:
        raise RefusedError(f"{tool}: {body}")
    return body


async def _session(client: Client, model: Path, *, role_map: Any, catalog_version: str) -> None:
    await client.list_tools()
    status = await _body(client, "revit_connection_status", {})
    catalog = str(status.get("catalog_version") or catalog_version)
    await _body(client, "revit_open_model", {"path": str(model), "activate": True})

    async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
        reply = await client.call_tool(tool, arguments)
        if reply.is_error:
            raise RefusedError(f"{tool}: {reply_body(reply)}")
        return reply.model_dump(mode="json", by_alias=True, exclude_none=True)

    await RevitStateReader(call=call, role_map=role_map, catalog_version=catalog).read(bound_path=model)


async def record(server: ServerConfig, model: Path, out: Path, run_dir: Path) -> Path:
    """Record one session on the copy `model` into a folder under `out`; `RefusedError` after writing it."""
    role_name, role = next(iter(server.roles.items()))
    build = f"{server.build.sasaah_commit[:12]}+{server.build.exe_sha256[:12]}"
    folder = out / f"{server.adapter}-{build}"
    spec = LaunchSpec(
        argv=launch_argv(server, server.host_key, role_name, role, run_dir),
        env={**get_default_environment(), **server.env}, cwd=run_dir,
        stderr_path=run_dir / "servers" / f"{server.host_key}-{role_name}.stderr.log", job=JobPolicy.SERVER,
    )  # fmt: skip
    allowlist = revit_allowlist(role="write")
    recording = Recording(folder, run_dir, adapter=server.adapter, build=build, tool_names=allowlist.tool_names)
    transport = RecordMode(
        ProcessTransport(platform_launcher(platform_inspector()).start(spec), grace_s=server.shutdown_grace_s),
        recording,
    )
    role_map = load_role_map(server.parameters)
    refusal: RefusedError | None = None
    async with Client(transport, mode=server.mcp_mode, cache=None, read_timeout_seconds=None) as client:
        try:
            await _session(client, model, role_map=role_map, catalog_version="")
        except RefusedError as error:
            refusal = error
    if refusal is not None:
        raise refusal
    return folder


def main(argv: list[str] | None = None) -> int:
    """The command line; see the module text."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=Path("harness.toml"))
    parser.add_argument("--model", type=Path, required=True, help="a COPY of the model to open")
    parser.add_argument("--out", type=Path, default=Path("acceptance/recordings"))
    parser.add_argument("--run-dir", type=Path, help="keeps the name mapping (default: a new temporary folder)")
    args = parser.parse_args(argv)
    servers = [s for s in load_servers_config(args.config).servers.values() if s.adapter == "sasaah-revit-mcp"]
    server = servers[0] if servers else None
    if server is None or not args.model.is_file():
        parser.error("no sasaah-revit-mcp server in the configuration, or the model copy was not found")
    run_dir = args.run_dir or Path(tempfile.mkdtemp(prefix="record-revit-"))
    try:
        folder = anyio.run(lambda: record(server, args.model, args.out, run_dir))
    except RefusedError as refusal:
        sys.stderr.write(f"refused: {refusal} (the recording was written)\n")
        return 1
    sys.stdout.write(f"recorded {folder}; name mapping in {run_dir}; review the files before committing them\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
