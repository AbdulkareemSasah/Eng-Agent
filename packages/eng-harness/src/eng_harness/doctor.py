"""`eng-harness doctor` (plan 0002 T18; spec 0002 section 4.9, AC37, AC39).

Reports each check as `ok`, `warn`, `fail` or `skip` and changes nothing. Paths are base names unless `show_paths`.
Exit 0 when no check is `fail`, and 1 otherwise.
"""

import hashlib
import importlib
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Protocol, TextIO

import anyio
from eng_contract.errors import ContractError
from eng_contract.store import LocationProbe, default_location_probe, resolve_workspace
from mcp import types
from pydantic import BaseModel, ConfigDict

from eng_harness.adapters import Allowlist
from eng_harness.adapters.csi import csi_allowlist
from eng_harness.errors import ToolFailed
from eng_harness.servers import CallEffect, ServerManager, ServersConfig, load_servers_config
from eng_harness.servers._buildcheck import tool_list_fingerprint
from eng_harness.servers._hostlock import default_lock_dir
from eng_harness.servers._procinfo import PosixProcessInspector, ProcessIdentity, ProcessInspector

logger = logging.getLogger(__name__)

# ADR-0028 section 5. Sasaah default: spec 0002 section 4.2, CsiServerConfig.cs:18. uv bound: cli/_opener.py.
_PYTHON, _SASAAH_DEFAULT_TIMEOUT_S, _UV_TIMEOUT_S, _MEDIUM = (3, 14), 120, 30, 0x2000
# winnt.h SECURITY_MANDATORY_*_RID. Medium is the user's standard level (architecture 16 section 6).
_LEVELS = {
    0x0000: "untrusted", 0x1000: "low", 0x2000: "medium", 0x2100: "medium plus",
    0x3000: "high", 0x4000: "system", 0x5000: "protected",
}  # fmt: skip
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")  # file-name rule of servers/_hostlock.py (spec 0002 section 4.4.1)
_STATUS_KEYS = frozenset({"read_only", "script_enabled", "instances", "current_target"})
_MODEL = ConfigDict(extra="forbid", frozen=True)


class Check(BaseModel):
    """One doctor row (spec 0002 section 4.9)."""

    model_config = _MODEL
    name: str
    status: str
    detail: str


class DoctorReport(BaseModel):
    """The checks in report order, including extension checks (AC39)."""

    model_config = _MODEL
    checks: tuple[Check, ...]


class CheckProvider(Protocol):
    """A later spec's checks. `name` is used when `checks` raises (AC39)."""

    name: str

    def checks(self) -> Sequence[Check]: ...


class InstalledProgramsProbe(Protocol):
    """v1 checks directories. A registry probe waits on gap H-G6."""

    def exists(self, directory: str) -> bool: ...


class TokenReader(Protocol):
    """Mandatory integrity RID. A failed read returns None and writes nothing."""

    def current(self) -> int | None: ...

    def of_pid(self, pid: int) -> int | None: ...


@dataclass(frozen=True)
class RoleFacts:
    """A brief role start: the tool list and `csi_status`, or why it could not."""

    tools: Mapping[str, Any]
    status: Mapping[str, Any] | None
    error: str | None


class RoleInspector(Protocol):
    """Reads `tools/list` and `csi_status`. No host program is launched (spec 0002 section 4.9)."""

    def inspect(self, config: ServersConfig, run_dir: Path) -> Mapping[tuple[str, str], RoleFacts]: ...


@dataclass(frozen=True)
class DoctorDeps:
    """Collaborators of `run`. Defaults read this machine; tests pass fakes."""

    env: Mapping[str, str]
    which: Callable[[str], str | None]
    uv_version: Callable[[], str | None]
    implementation: str
    version: tuple[int, int]
    location: LocationProbe
    programs: InstalledProgramsProbe
    roles: RoleInspector
    allowlist_for: Callable[[str], Allowlist | None]
    inspector: ProcessInspector
    tokens: TokenReader | None
    home: Path
    windows: bool


class DirectoryInstallProbe:
    """v1: a declared `install_dirs` entry exists. Registry keys are gap H-G6."""

    def exists(self, directory: str) -> bool:
        return Path(directory).is_dir()


class LiveRoles:
    """Starts each role, reads `tools/list` and `csi_status`, and stops it. No host program is launched."""

    def inspect(self, config: ServersConfig, run_dir: Path) -> Mapping[tuple[str, str], RoleFacts]:
        return anyio.run(_gather, config, run_dir)


class WindowsTokens:
    """Mandatory integrity RID (`GetTokenInformation`, `TokenIntegrityLevel` = 25). Read only (16 section 6)."""

    def current(self) -> int | None:
        return _windows_rid(None)

    def of_pid(self, pid: int) -> int | None:
        return _windows_rid(pid)


def _read_uv() -> str | None:
    uv = shutil.which("uv")
    if uv is None:
        return None
    try:
        done = subprocess.run(  # noqa: S603  # B-137: absolute path from shutil.which, fixed arguments
            [uv, "--version"], check=False, capture_output=True, text=True, timeout=_UV_TIMEOUT_S
        )
    except OSError, subprocess.SubprocessError:
        return None
    line = done.stdout.strip().splitlines()
    return line[0] if done.returncode == 0 and line else None


def _inspector() -> ProcessInspector:
    if os.name != "nt":
        return PosixProcessInspector()
    module = importlib.import_module("eng_harness.servers._procinfo")
    found: ProcessInspector = module.WindowsProcessInspector(module.CtypesKernel32(module.PROCESS_SIGNATURES))
    return found


def default_deps() -> DoctorDeps:
    """The probes of this machine."""
    return DoctorDeps(
        env=os.environ, which=shutil.which, uv_version=_read_uv, implementation=platform.python_implementation(),
        version=(sys.version_info[0], sys.version_info[1]), location=default_location_probe(),
        programs=DirectoryInstallProbe(), roles=LiveRoles(), allowlist_for=_allowlist, inspector=_inspector(),
        tokens=WindowsTokens() if os.name == "nt" else None, home=Path.home(), windows=os.name == "nt",
    )  # fmt: skip


def _allowlist(adapter: str) -> Allowlist | None:
    return csi_allowlist() if adapter == "sasaah-csi-mcp" else None


def _shown(path: str, show: bool) -> str:
    if show:
        return path
    return PureWindowsPath(path).name if "\\" in path else Path(path).name


def _products(status: Mapping[str, Any]) -> str:
    """Members of `csi_status` besides the flags and the instance list (S-12 names no JSON member)."""
    rest = {key: status[key] for key in sorted(status) if key not in _STATUS_KEYS}
    return "installed products " + json.dumps(rest, sort_keys=True, default=str)


def _row(name: str, status: str, detail: str) -> Check:
    return Check(name=name, status=status, detail=detail)


def _collect(config: ServersConfig, deps: DoctorDeps, show: bool, extra: Sequence[CheckProvider]) -> DoctorReport:
    with tempfile.TemporaryDirectory(prefix="eng-doctor-") as folder:
        facts = deps.roles.inspect(config, Path(folder)) if config.servers else {}
    rows = [_python_row(deps)]
    for name, server in config.servers.items():
        rows.append(_exe_row(name, server.command, server.build.exe_sha256, show))
    for name, server in config.servers.items():
        allowlist = deps.allowlist_for(server.adapter)
        for role in server.roles:
            record = facts.get((name, role)) or RoleFacts({}, None, "the role was not inspected")
            rows.append(_print_row(name, role, record, allowlist))
    statuses = [
        found.status
        for server, body in config.servers.items()
        for role in body.roles
        if (found := facts.get((server, role))) is not None and found.status is not None
    ]
    rows.append(_dirs_row(config, statuses, deps, show))
    rows += _integrity(config, deps)
    rows += [_workspace(deps), _timeouts(config), _locks(config, deps), _unreleased(config, deps), *_extra(extra)]
    return DoctorReport(checks=tuple(rows))


def _python_row(deps: DoctorDeps) -> Check:
    version = deps.uv_version() if deps.which("uv") else None
    detail = f"{version or 'uv is not on PATH'}; {deps.implementation} {deps.version[0]}.{deps.version[1]}"
    right = deps.implementation == "CPython" and deps.version == _PYTHON
    return _row(
        "uv and Python", "ok" if version and right else "fail", detail if right else detail + "; need CPython 3.14"
    )


def _exe_row(name: str, command: str, pin: str, show: bool) -> Check:
    shown, path = _shown(command, show), Path(command)
    if not path.is_file():
        return _row(f"server executable {name}", "fail", f"{shown} is missing")
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    state = "matches" if digest == pin else "differs from"
    return _row(
        f"server executable {name}", "ok" if digest == pin else "fail", f"{shown} SHA-256 {digest} {state} {pin}"
    )


def _print_row(server: str, role: str, facts: RoleFacts, allowlist: Allowlist | None) -> Check:
    name = f"tool-list fingerprint {server}/{role}"
    if facts.error:
        return _row(name, "fail", facts.error)
    if facts.status is None:
        return _row(name, "fail", "csi_status gave no JSON object")
    if allowlist is None:
        return _row(name, "fail", "no allowlist is packaged for this adapter")
    flags = f"read_only={facts.status.get('read_only')} script_enabled={facts.status.get('script_enabled')}"
    body = f"{flags}; {_products(facts.status)}"
    missing = sorted(allowlist.tool_names - facts.tools.keys())
    seen = {tool: schema for tool, schema in facts.tools.items() if tool in allowlist.tool_names}
    bad = [flag for flag in ("read_only", "script_enabled") if facts.status.get(flag) is not False]
    if missing:
        return _row(name, "fail", f"allowlisted tool {', '.join(missing)} is not listed; {body}")
    if tool_list_fingerprint(seen) != allowlist.tool_fingerprint:
        return _row(name, "fail", f"differs from the allowlist; {body}")
    if bad:
        return _row(name, "fail", f"{' and '.join(bad)} is not false; {body}")
    return _row(name, "ok", f"matches the allowlist; {body}")


def _dirs_row(config: ServersConfig, statuses: Sequence[Mapping[str, Any]], deps: DoctorDeps, show: bool) -> Check:
    parts: list[str] = []
    failed = False
    for name, program in config.host_programs.items():
        if not program.install_dirs:
            parts.append(f"{name} no install_dirs")
        for directory in program.install_dirs:
            present = deps.programs.exists(directory)
            failed = failed or not present
            parts.append(f"{name} {_shown(directory, show)} {'present' if present else 'missing'}")
    if not config.host_programs:
        parts.append("none declared")
    parts += [_products(status) for status in statuses]
    return _row("installed host programs", "fail" if failed else "ok", "; ".join(parts))


def _integrity(config: ServersConfig, deps: DoctorDeps) -> list[Check]:
    if not deps.windows or deps.tokens is None:
        return [_row("integrity level", "skip", "Windows only (architecture 16 section 6)")]
    names = [exe for program in config.host_programs.values() for exe in program.executables]
    rows = [_level("integrity level", deps.tokens.current(), host=False)]
    return rows + [
        _level(f"integrity level {item.exe_name}", deps.tokens.of_pid(item.pid), host=True)
        for item in deps.inspector.snapshot(names)
    ]


def _level(name: str, rid: int | None, *, host: bool) -> Check:
    if rid is None:
        detail = "token cannot be read" if host else "the process token cannot be read"
        return _row(name, "skip" if host else "fail", detail)
    if rid == _MEDIUM:
        return _row(name, "ok", "medium")
    return _row(name, "warn", f"{_LEVELS.get(rid, f'RID {rid:#x}')}, not medium")


def _workspace(deps: DoctorDeps) -> Check:
    try:
        return _row("workspace", "ok", resolve_workspace(deps.env, deps.location).classification.value)
    except ContractError as error:
        return _row("workspace", "fail", str(error))


def _timeouts(config: ServersConfig) -> Check:
    single = any(len(server.roles) == 1 for server in config.servers.values())
    bits = [
        f"{n}/{role} call_timeout_s={body.call_timeout_s}"
        for n, server in config.servers.items()
        for role, body in server.roles.items()
    ]
    bits += [f"{n} client_grace_s={server.client_grace_s}" for n, server in config.servers.items()]
    bits += [f"{n} timeout_s={tool.timeout_s}" for n, tool in config.cli_tools.items()]
    detail = "; ".join(bits)
    if single:
        detail = "single topology: a hung read waits as long as an analysis; " + detail
    suffix = f"Sasaah default {_SASAAH_DEFAULT_TIMEOUT_S} s"
    return _row("timeouts", "warn" if single else "ok", f"{detail}; {suffix}" if detail else suffix)


def _locks(config: ServersConfig, deps: DoctorDeps) -> Check:
    directory = default_lock_dir(deps.env, home=deps.home, windows=deps.windows)
    shown = _shown(str(directory), False)
    if not _writable(directory):
        return _row("lock directory", "fail", f"{shown} is not writable")
    stale = _stale_locks(directory, list(config.host_programs), deps.inspector)
    detail = "writable; no stale lock" if not stale else "writable; stale " + ", ".join(stale)
    return _row("lock directory", "ok", detail)


def _writable(directory: Path) -> bool:
    current = directory
    while not current.exists():
        if current.parent == current:
            return False
        current = current.parent
    return current.is_dir() and os.access(current, os.W_OK)


def _stale_locks(directory: Path, programs: Sequence[str], inspector: ProcessInspector) -> list[str]:
    stale: list[str] = []
    for path in sorted(directory.glob("host-*.lock")) if directory.is_dir() else []:
        ident = _lock_identity(path.name, programs)
        if ident is None:
            continue
        try:
            live = inspector.identity(ident.pid)
        except OSError:
            logger.info("lock %s: pid %s cannot be queried", path.name, ident.pid)
            continue
        if live is None or _UNSAFE.sub("_", live.started_at) != ident.started_at:
            stale.append(path.name)
    return stale


def _lock_identity(name: str, programs: Sequence[str]) -> ProcessIdentity | None:
    stem = name.removesuffix(".lock")
    for program in sorted(programs, key=len, reverse=True):
        prefix = f"host-{_UNSAFE.sub('_', program)}-"
        if stem.startswith(prefix):
            pid_text, sep, started = stem[len(prefix) :].partition("-")
            if sep and pid_text.isdigit():
                return ProcessIdentity(int(pid_text), started, program)
    return None


def _unreleased(config: ServersConfig, deps: DoctorDeps) -> Check:
    found: dict[str, str] = {}
    for server in config.servers.values():
        allowlist = deps.allowlist_for(server.adapter)
        if allowlist is not None:
            found.update(allowlist.unreleased_tools())
    found.update(config.unreleased_tools())
    listed = ", ".join(f"{name} ({record})" for name, record in sorted(found.items()))
    return _row("unreleased tools", "warn" if found else "ok", listed or "none")


def _extra(providers: Sequence[CheckProvider]) -> list[Check]:
    found: list[Check] = []
    for index, provider in enumerate(providers):
        label = f"extra[{index}]"
        try:
            label = provider.name
            found.extend(provider.checks())
        except Exception as error:  # AC39: one fail naming the provider and the exception type
            found.append(_row(label, "fail", type(error).__name__))
    return found


def _render(report: DoctorReport, *, json_output: bool) -> str:
    if json_output:
        return json.dumps({"checks": [item.model_dump() for item in report.checks]}, indent=2) + "\n"
    return "".join(f"{item.status} | {item.name} | {item.detail}\n" for item in report.checks)


def run(
    config_path: Path,
    *,
    json_output: bool,
    show_paths: bool,
    extra_checks: Sequence[CheckProvider] = (),
    out: TextIO | None = None,
    deps: DoctorDeps | None = None,
) -> int:
    """Run the section 4.9 checks. `extra_checks` follow them, in order (AC39).

    `out` defaults to standard output. Returns 1 when any check is `fail`. Raises `ConfigError` when the file
    cannot be read or a server section is invalid.
    """
    config = load_servers_config(config_path)
    report = _collect(config, deps or default_deps(), show_paths, extra_checks)
    (out or sys.stdout).write(_render(report, json_output=json_output))
    return 1 if any(item.status == "fail" for item in report.checks) else 0


def _body(result: types.CallToolResult) -> dict[str, Any] | None:
    block = result.content[0] if result.content else None
    if result.is_error or not isinstance(block, types.TextContent):
        return None
    try:
        parsed = json.loads(block.text)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def _one(manager: ServerManager, server: str, role: str) -> RoleFacts:
    try:
        listed = await manager.list_tools(server, role)
        result = await manager.call(server, role, "csi_status", {}, CallEffect.READ)
    except ToolFailed as error:
        return RoleFacts({}, None, error.detail.message)
    return RoleFacts({tool.name: tool.input_schema for tool in listed}, _body(result), None)


async def _gather(config: ServersConfig, run_dir: Path) -> dict[tuple[str, str], RoleFacts]:
    keys = [(name, role) for name, server in config.servers.items() for role in server.roles]
    async with ServerManager(config, run_dir) as manager:
        return {key: await _one(manager, *key) for key in keys}


if sys.platform == "win32":

    def _windows_rid(pid: int | None) -> int | None:
        import ctypes
        from ctypes import POINTER, byref, c_ubyte, c_uint32, c_void_p, create_string_buffer

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel.CloseHandle.argtypes = [c_void_p]
        token = c_void_p()
        # TOKEN_QUERY = 0x0008 and PROCESS_QUERY_LIMITED_INFORMATION = 0x1000 (winnt.h).
        process = kernel.GetCurrentProcess() if pid is None else kernel.OpenProcess(0x1000, False, pid)
        opened = bool(process) and bool(advapi.OpenProcessToken(process, 0x0008, byref(token)))
        if pid is not None and process:
            kernel.CloseHandle(process)
        if not opened:
            return None
        needed = c_uint32()
        advapi.GetTokenInformation(token, 25, None, 0, byref(needed))
        buffer = create_string_buffer(needed.value)
        read = bool(needed.value) and advapi.GetTokenInformation(token, 25, buffer, needed.value, byref(needed))
        kernel.CloseHandle(token)
        sid = c_void_p.from_buffer(buffer).value if read else None
        if not sid:
            return None
        count_fn, sub_fn = advapi.GetSidSubAuthorityCount, advapi.GetSidSubAuthority
        count_fn.restype, sub_fn.restype = POINTER(c_ubyte), POINTER(c_uint32)
        count = count_fn(sid).contents.value
        return int(sub_fn(sid, count - 1).contents.value) if count else None

else:

    def _windows_rid(_pid: int | None) -> int | None:
        return None
