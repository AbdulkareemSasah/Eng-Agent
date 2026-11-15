"""Record a session with the real Sasaah CSI server on a COPY of a model (owner only; spec 0002 section 4.8.1).

    uv run python acceptance/scripts/record_csi.py --config harness.toml --model D:/copies/copy.EDB [--analysis ...]

Starts the configured CSI server, launches ETABS through it, opens the copy, reads the model state as the adapter does,
with `--analysis` runs the analysis (it locks the copy) and reads the status and the results of the named cases and
combinations, and ends the instance it launched. Everything goes through record mode into
`acceptance/recordings/<adapter>-<build>/`; read acceptance/recordings/README.md before committing it.
Exit code 0: recorded; 1: the server refused a step (the recording is written anyway); 2: usage.
"""

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Any

import anyio
from mcp import Client
from mcp.client.stdio import get_default_environment

from eng_harness.adapters.csi import csi_allowlist
from eng_harness.adapters.csi._state import CsiStateReader
from eng_harness.servers import CallEffect, Recording, RecordMode, ServerConfig, load_servers_config
from eng_harness.servers._launch_args import launch_argv
from eng_harness.servers._launcher import JobPolicy, LaunchSpec, PosixLauncher, ProcessLauncher
from eng_harness.servers._session import reply_body
from eng_harness.servers._transport import ProcessTransport

_PRODUCT = "ETABS"  # the product of the CSI allowlist (spec 0002 section 4.5.1)
_RESULTS = ("csi_results_joint_reactions", "csi_results_frame_forces", "csi_results_story_drifts")


class RefusedError(Exception):
    """The server answered a step with an error reply (it has been recorded by then)."""


def _launcher() -> ProcessLauncher:
    if sys.platform == "win32":
        from eng_harness.servers._launcher_windows import windows_launcher

        return windows_launcher()
    return PosixLauncher()


async def _body(client: Client, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    reply = await client.call_tool(tool, arguments)
    if (body := reply_body(reply)) is None or reply.is_error:
        raise RefusedError(f"{tool}: {body}")
    return body


async def _session(client: Client, model: Path, analysis: dict[str, list[str]] | None) -> None:
    await client.list_tools()
    await _body(client, "csi_status", {})
    pid = (await _body(client, "csi_launch", {"product": _PRODUCT}))["pid"]
    target = {"target": {"product": _PRODUCT, "pid": pid}}
    try:
        await _body(client, "csi_open_model", {"path": str(model), "confirm": True, **target})

        async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return await _body(client, tool, arguments)

        await CsiStateReader(product=_PRODUCT, call=call).read(pid, model)
        if analysis is not None:
            await _body(client, "csi_run_analysis", {"confirm": True, **target})
            await _body(client, "csi_analysis_status", target)
            for tool in _RESULTS:
                await _body(client, tool, {**analysis, "units": "kN_m_C", **target})
    finally:  # the instance this script launched is ended, whatever happened
        await client.call_tool("csi_exit", {"confirm": True})


async def record(
    server: ServerConfig, model: Path, out: Path, run_dir: Path, *, analysis: dict[str, list[str]] | None = None
) -> Path:
    """Record one session on the copy `model` into a folder under `out`; `RefusedError` after writing it."""
    role_name, role = next(iter(server.roles.items()))
    build = f"{server.build.sasaah_commit[:12]}+{server.build.exe_sha256[:12]}"
    folder = out / f"{server.adapter}-{build}"
    spec = LaunchSpec(
        argv=launch_argv(server, server.host_key, role_name, role, run_dir),
        env={**get_default_environment(), **server.env}, cwd=run_dir,
        stderr_path=run_dir / "servers" / f"{server.host_key}-{role_name}.stderr.log", job=JobPolicy.SERVER,
    )  # fmt: skip
    recording = Recording(folder, run_dir, adapter=server.adapter, build=build, tool_names=csi_allowlist().tool_names)
    transport = RecordMode(ProcessTransport(_launcher().start(spec), grace_s=server.shutdown_grace_s), recording)
    refusal: RefusedError | None = None
    async with Client(transport, mode=server.mcp_mode, cache=None, read_timeout_seconds=None) as client:
        try:
            await _session(client, model, analysis)
        except RefusedError as error:  # raised again outside the client, whose task group would wrap it
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
    parser.add_argument("--analysis", action="store_true", help="also run the analysis and read the results")
    parser.add_argument("--cases", nargs="*", default=[], help="load cases of the results to read")
    parser.add_argument("--combos", nargs="*", default=[], help="combinations of the results to read")
    args = parser.parse_args(argv)
    servers = load_servers_config(args.config).servers.values()
    server = next((s for s in servers if s.adapter == "sasaah-csi-mcp"), None)
    if server is None or not args.model.is_file():
        parser.error("no sasaah-csi-mcp server in the configuration, or the model copy was not found")
    run_dir = args.run_dir or Path(tempfile.mkdtemp(prefix="record-csi-"))
    analysis = {"cases": args.cases, "combos": args.combos} if args.analysis else None
    try:
        folder = anyio.run(lambda: record(server, args.model, args.out, run_dir, analysis=analysis))
    except RefusedError as refusal:
        sys.stderr.write(f"refused: {refusal} (the recording was written)\n")
        return 1
    sys.stdout.write(f"recorded {folder}; name mapping in {run_dir}; review the files before committing them\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
