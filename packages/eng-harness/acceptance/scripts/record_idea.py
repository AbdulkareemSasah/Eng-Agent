"""Record an attended IDEA session on an anonymized .ideaCon copy (spec 0014 §12).

Run from packages/eng-harness. Review every recording file before committing it.
"""

import argparse
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import anyio
from mcp import Client
from mcp.client.stdio import get_default_environment
from pydantic import JsonValue, TypeAdapter

from eng_harness.adapters.idea import idea_allowlist
from eng_harness.adapters.idea._tools import build_native_calculate_args, build_native_set_loads_args
from eng_harness.servers import (
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

_BUILD_PREFIX = 12  # build identifier format in spec 0002 §4.3.4
_REFUSED = 1  # command exit code
_OK = 0  # command exit code
_LOADS = TypeAdapter(list[dict[str, JsonValue]])


class RefusedError(Exception):
    """A tool refused an operation during the recording."""


async def _call(client: Client, name: str, args: dict[str, Any]) -> dict[str, Any]:
    reply = await client.call_tool(name, args)
    body = reply_body(reply)
    if reply.is_error or body is None:
        raise RefusedError(name)
    return body


async def _scenario(
    client: Client, model: Path, route: str, connection: str, calculate: bool, loads: list[dict[str, JsonValue]] | None
) -> None:
    page = await client.list_tools()
    while page.next_cursor is not None:
        page = await client.list_tools(cursor=page.next_cursor)
    await _call(client, "idea_status", {})
    if route == "native":
        read = {"path": str(model), "connection_id": connection}
        await _call(client, "idea_native_get_loads", read)
        if loads is not None:
            destination = model.with_name("updated.ideaCon")
            await _call(
                client,
                "idea_native_set_loads",
                build_native_set_loads_args(
                    path=str(model), out_path=str(destination), connection_id=connection, loads=loads, approved=True
                ),
            )
            model = destination
            await _call(client, "idea_native_get_loads", {**read, "path": str(model)})
        if calculate:
            request = build_native_calculate_args(path=str(model), connection_id=connection)
            await _call(client, "idea_native_calculate", request)
        return
    opened = await _call(client, "idea_open_project", {"path": str(model)})
    try:
        if opened.get("backend") != "rest" or opened.get("live_project") is not True:
            raise RefusedError("IDEA did not open a live REST project")
        listed = await _call(client, "idea_list_connections", {})
        if calculate:
            selected = next((c["id"] for c in listed["connections"] if str(c["id"]) == connection), None)
            if selected is None:
                raise RefusedError("the requested REST connection ID was not listed")
            await _call(client, "idea_calculate", {"connection_ids": [selected], "confirm": True})
            await _call(client, "idea_get_check_results", {"connection_id": selected})
    finally:
        await _call(client, "idea_close_project", {})


async def _record(server: ServerConfig, route: str, args: argparse.Namespace, run_dir: Path) -> Path:
    role_name, role = next(iter(server.roles.items()))
    commit, executable = server.build.sasaah_commit, server.build.exe_sha256
    build = f"{commit[:_BUILD_PREFIX]}+{executable[:_BUILD_PREFIX]}"
    folder = Path(args.out) / f"{server.adapter}-{build}-{route}"
    # Use one manifest folder per route, even when both configurations pin the same build.
    if folder.exists():
        raise RefusedError("the output already exists")
    loads = _LOADS.validate_json(args.apply_loads.read_bytes()) if args.apply_loads else None
    model = Path(shutil.copyfile(args.model, run_dir / "connection.ideaCon"))
    spec = LaunchSpec(
        argv=launch_argv(server, server.host_key, role_name, role, run_dir),
        env={**get_default_environment(), **server.env},
        cwd=run_dir,
        stderr_path=run_dir / "server.stderr.log",
        job=JobPolicy.SERVER,
    )
    allow = idea_allowlist(route)
    recording = Recording(folder, run_dir, adapter=server.adapter, build=build, tool_names=allow.tool_names)
    transport = RecordMode(
        ProcessTransport(platform_launcher(platform_inspector()).start(spec), grace_s=server.shutdown_grace_s),
        recording,
    )
    refusal = None
    backstop = role.call_timeout_s + server.client_grace_s
    async with Client(transport, mode=server.mcp_mode, cache=None, read_timeout_seconds=backstop) as client:
        try:
            await _scenario(client, model, route, args.connection, args.calculate, loads)
        except RefusedError as error:
            refusal = error
    if refusal is not None:
        raise refusal
    return folder


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("harness.toml"))
    parser.add_argument("--model", type=Path, required=True, help="an anonymized .ideaCon copy")
    parser.add_argument("--connection", required=True, help="native connection name or REST connection ID")
    parser.add_argument("--calculate", action="store_true", help="explicitly authorize calculation on the copy")
    parser.add_argument("--apply-loads", type=Path, help="authorize native load write using this owner-prepared JSON")
    parser.add_argument("--out", type=Path, default=Path("acceptance/recordings"))
    args = parser.parse_args()
    servers = load_servers_config(args.config).servers.values()
    server = next((s for s in servers if s.adapter == "sasaah-idea-mcp"), None)
    if server is None or server.route is None or not args.model.is_file() or args.model.suffix != ".ideaCon":
        parser.error("supply an IDEA server configuration and a .ideaCon copy")
    if args.apply_loads and server.route != "native":
        parser.error("--apply-loads requires the native route")
    run_dir = Path(tempfile.mkdtemp(prefix="record-idea-"))
    sys.stdout.write(f"Private working files and name mapping: {run_dir}\n")
    try:
        folder = anyio.run(_record, server, server.route, args, run_dir)
    except RefusedError as refusal:
        sys.stderr.write(f"IDEA recording stopped: {refusal}. Review any files written under {args.out}.\n")
        return _REFUSED
    sys.stdout.write(f"Recorded {folder}. Review every exchange before committing.\n")
    return _OK


if __name__ == "__main__":
    raise SystemExit(main())
