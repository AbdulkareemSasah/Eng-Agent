"""`eng-harness doctor` (plan 0002 T18; spec 0002 section 4.9, AC37, AC39)."""

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
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
from eng_harness.servers._launcher import ProcessLauncher
from eng_harness.servers._platform import platform_inspector, platform_launcher
from eng_harness.servers._procinfo import ProcessIdentity, ProcessInspector

# ADR-0028 §5; spec 0002 §4.2 (CsiServerConfig.cs:18); uv bound of cli/_opener.py; medium RID (winnt.h).
_PY, _SASAAH_S, _UV_S, _MEDIUM = (3, 14), 120, 30, 0x2000
_LEVELS = {  # winnt.h SECURITY_MANDATORY_*_RID
    0x0000: "untrusted", 0x1000: "low", 0x2000: "medium", 0x2100: "medium plus",
    0x3000: "high", 0x4000: "system", 0x5000: "protected",
}  # fmt: skip
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")  # file-name rule of servers/_hostlock.py (spec 0002 §4.4.1)
_FLAGS = ("read_only", "script_enabled")
_STATUS = frozenset({*_FLAGS, "instances", "current_target"})


class Check(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    status: str
    detail: str


class DoctorReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    checks: tuple[Check, ...]


class CheckProvider(Protocol):
    name: str

    def checks(self) -> Sequence[Check]: ...


@dataclass(frozen=True)
class RoleFacts:
    tools: Mapping[str, Any]
    status: Mapping[str, Any] | None
    error: str | None


@dataclass(frozen=True)
class DoctorDeps:
    env: Mapping[str, str]
    which: Callable[[str], str | None]
    uv_version: Callable[[], str | None]
    implementation: str
    version: tuple[int, int]
    location: LocationProbe
    programs: Any
    roles: Any
    allowlist_for: Callable[[str], Allowlist | None]
    inspector: ProcessInspector
    tokens: Any | None
    home: Path
    windows: bool


class LiveRoles:
    def __init__(self, inspector: ProcessInspector) -> None:
        self._inspector = inspector

    def inspect(self, config: ServersConfig, run_dir: Path) -> Mapping[tuple[str, str], RoleFacts]:
        return anyio.run(_gather, config, run_dir, platform_launcher(self._inspector))


def _uv() -> str | None:
    uv = shutil.which("uv")
    if uv is None:
        return None
    try:
        done = subprocess.run(  # noqa: S603  # B-137: absolute path from shutil.which, fixed arguments
            [uv, "--version"], check=False, capture_output=True, text=True, timeout=_UV_S
        )
    except OSError, subprocess.SubprocessError:
        return None
    line = done.stdout.strip().splitlines()
    return line[0] if done.returncode == 0 and line else None


def default_deps() -> DoctorDeps:
    inspector = platform_inspector()
    return DoctorDeps(
        env=os.environ, which=shutil.which, uv_version=_uv, implementation=platform.python_implementation(),
        version=(sys.version_info[0], sys.version_info[1]), location=default_location_probe(),
        programs=type("_Dir", (), {"exists": staticmethod(lambda d: Path(d).is_dir())})(),
        roles=LiveRoles(inspector),
        allowlist_for=lambda a: csi_allowlist() if a == "sasaah-csi-mcp" else None,
        inspector=inspector, tokens=WindowsTokens() if os.name == "nt" else None,
        home=Path.home(), windows=os.name == "nt",
    )  # fmt: skip


def _shown(path: str, show: bool) -> str:
    return path if show else PureWindowsPath(path).name if "\\" in path else Path(path).name


def _prod(status: Mapping[str, Any]) -> str:
    rest = {k: status[k] for k in sorted(status) if k not in _STATUS}
    return "installed products " + json.dumps(rest, sort_keys=True, default=str)


def _row(name: str, status: str, detail: str) -> Check:
    return Check(name=name, status=status, detail=detail)


def _collect(config: ServersConfig, deps: DoctorDeps, show: bool, extra: Sequence[CheckProvider]) -> DoctorReport:
    with tempfile.TemporaryDirectory(prefix="eng-doctor-") as folder:
        facts = deps.roles.inspect(config, Path(folder)) if config.servers else {}
    version = deps.uv_version() if deps.which("uv") else None
    right = deps.implementation == "CPython" and deps.version == _PY
    base = f"{version or 'uv is not on PATH'}; {deps.implementation} {deps.version[0]}.{deps.version[1]}"
    rows: list[Check] = [
        _row("uv and Python", "ok" if version and right else "fail", base if right else base + "; need CPython 3.14")
    ]
    missed, statuses = RoleFacts({}, None, "the role was not inspected"), []
    for name, server in config.servers.items():
        shown, path, title = _shown(server.command, show), Path(server.command), f"server executable {name}"
        if not path.is_file():
            rows.append(_row(title, "fail", f"{shown} is missing"))
        else:
            digest, pin = hashlib.sha256(path.read_bytes()).hexdigest(), server.build.exe_sha256
            state = "matches" if digest == pin else "differs from"
            rows.append(_row(title, "ok" if digest == pin else "fail", f"{shown} SHA-256 {digest} {state} {pin}"))
        allow = deps.allowlist_for(server.adapter)
        for role in server.roles:
            hit = facts.get((name, role)) or missed
            rows.append(_fingerprint(name, role, hit, allow))
            if hit.status is not None:
                statuses.append(hit.status)
    parts, failed = [], False
    for name, program in config.host_programs.items():
        parts += [f"{name} no install_dirs"] if not program.install_dirs else []
        for directory in program.install_dirs:
            present = deps.programs.exists(directory)
            failed = failed or not present
            parts.append(f"{name} {_shown(directory, show)} {'present' if present else 'missing'}")
    parts += ["none declared"] if not config.host_programs else []
    parts += [_prod(s) for s in statuses]
    rows.append(_row("installed host programs", "fail" if failed else "ok", "; ".join(parts)))
    if not deps.windows or deps.tokens is None:
        rows.append(_row("integrity level", "skip", "Windows only (architecture 16 section 6)"))
    else:
        names = [exe for program in config.host_programs.values() for exe in program.executables]
        rows.append(_level("integrity level", deps.tokens.current(), host=False))
        for item in deps.inspector.snapshot(names):
            rows.append(_level(f"integrity level {item.exe_name}", deps.tokens.of_pid(item.pid), host=True))
    try:
        rows.append(_row("workspace", "ok", resolve_workspace(deps.env, deps.location).classification.value))
    except ContractError as error:
        rows.append(_row("workspace", "fail", str(error)))
    single = any(len(server.roles) == 1 for server in config.servers.values())
    bits = [f"{n}/{k} call_timeout_s={v.call_timeout_s}" for n, s in config.servers.items() for k, v in s.roles.items()]
    bits += [f"{n} client_grace_s={s.client_grace_s}" for n, s in config.servers.items()]
    bits += [f"{n} timeout_s={t.timeout_s}" for n, t in config.cli_tools.items()]
    listed = "; ".join(bits)
    if single:
        listed = "single topology: a hung read waits as long as an analysis; " + listed
    suffix = f"Sasaah default {_SASAAH_S} s"
    rows.append(_row("timeouts", "warn" if single else "ok", f"{listed}; {suffix}" if listed else suffix))
    rows.append(_locks(config, deps))
    found: dict[str, str] = {}
    for server in config.servers.values():
        if (allow := deps.allowlist_for(server.adapter)) is not None:
            found.update(allow.unreleased_tools())
    found.update(config.unreleased_tools())
    released = ", ".join(f"{name} ({record})" for name, record in sorted(found.items()))
    rows.append(_row("unreleased tools", "warn" if found else "ok", released or "none"))
    for index, provider in enumerate(extra):
        label = f"extra[{index}]"
        try:
            label = provider.name
            rows.extend(provider.checks())
        except Exception as error:  # AC39: one fail naming the provider and the exception type
            rows.append(_row(label, "fail", type(error).__name__))
    return DoctorReport(checks=tuple(rows))


def _fingerprint(server: str, role: str, facts: RoleFacts, allowlist: Allowlist | None) -> Check:
    name, status = f"tool-list fingerprint {server}/{role}", facts.status
    if facts.error:
        return _row(name, "fail", facts.error)
    if status is None:
        return _row(name, "fail", "csi_status gave no JSON object")
    if allowlist is None:
        return _row(name, "fail", "no allowlist is packaged for this adapter")
    body = f"read_only={status.get('read_only')} script_enabled={status.get('script_enabled')}; {_prod(status)}"
    missing = sorted(allowlist.tool_names - facts.tools.keys())
    seen = {tool: schema for tool, schema in facts.tools.items() if tool in allowlist.tool_names}
    bad = [flag for flag in _FLAGS if status.get(flag) is not False]
    if missing:
        return _row(name, "fail", f"allowlisted tool {', '.join(missing)} is not listed; {body}")
    if tool_list_fingerprint(seen) != allowlist.tool_fingerprint:
        return _row(name, "fail", f"differs from the allowlist; {body}")
    if bad:
        return _row(name, "fail", f"{' and '.join(bad)} is not false; {body}")
    return _row(name, "ok", f"matches the allowlist; {body}")


def _level(name: str, rid: int | None, *, host: bool) -> Check:
    if rid is None:
        detail = "token cannot be read" if host else "the process token cannot be read"
        return _row(name, "skip" if host else "fail", detail)
    if rid == _MEDIUM:
        return _row(name, "ok", "medium")
    return _row(name, "warn", f"{_LEVELS.get(rid, f'RID {rid:#x}')}, not medium")


def _locks(config: ServersConfig, deps: DoctorDeps) -> Check:
    programs = list(config.host_programs)

    def lock_identity(name: str) -> ProcessIdentity | None:
        stem = name.removesuffix(".lock")
        for program in sorted(programs, key=len, reverse=True):
            prefix = f"host-{_UNSAFE.sub('_', program)}-"
            if not stem.startswith(prefix):
                continue
            pid_text, sep, started = stem[len(prefix) :].partition("-")
            if sep and pid_text.isdigit():
                return ProcessIdentity(int(pid_text), started, program)
        return None

    directory = default_lock_dir(deps.env, home=deps.home, windows=deps.windows)
    shown, current = _shown(str(directory), False), directory
    while not current.exists() and current.parent != current:
        current = current.parent
    if not (current.is_dir() and os.access(current, os.W_OK)):
        return _row("lock directory", "fail", f"{shown} is not writable")
    stale: list[str] = []
    for path in sorted(directory.glob("host-*.lock")) if directory.is_dir() else []:
        ident = lock_identity(path.name)
        if ident is None:
            continue
        try:
            live = deps.inspector.identity(ident.pid)
        except OSError:
            continue
        if live is None or _UNSAFE.sub("_", live.started_at) != ident.started_at:
            stale.append(path.name)
    detail = "writable; no stale lock" if not stale else "writable; stale " + ", ".join(stale)
    return _row("lock directory", "ok", detail)


def run(
    config_path: Path | None, *, json_output: bool, show_paths: bool, extra_checks: Sequence[CheckProvider] = (),
    out: TextIO | None = None, deps: DoctorDeps | None = None, env: Mapping[str, str] | None = None,
) -> int:  # fmt: skip
    config = ServersConfig() if config_path is None else load_servers_config(config_path)
    found = deps or default_deps()
    report = _collect(config, found if env is None else replace(found, env=env), show_paths, extra_checks)
    (out or sys.stdout).write(
        json.dumps({"checks": [c.model_dump() for c in report.checks]}, indent=2) + "\n"
        if json_output
        else "".join(f"{c.status} | {c.name} | {c.detail}\n" for c in report.checks)
    )
    return 1 if any(item.status == "fail" for item in report.checks) else 0


async def _one(manager: ServerManager, server: str, role: str) -> RoleFacts:
    try:
        listed = await manager.list_tools(server, role)
        result = await manager.call(server, role, "csi_status", {}, CallEffect.READ)
    except ToolFailed as error:
        return RoleFacts({}, None, error.detail.message)
    block = result.content[0] if result.content else None
    parsed = None
    if not result.is_error and isinstance(block, types.TextContent):
        try:
            parsed = json.loads(block.text)
        except ValueError:
            parsed = None
    status = parsed if isinstance(parsed, dict) else None
    return RoleFacts({tool.name: tool.input_schema for tool in listed}, status, None)


async def _gather(config: ServersConfig, run_dir: Path, launcher: ProcessLauncher) -> dict[tuple[str, str], RoleFacts]:
    pairs = [(name, role) for name, server in config.servers.items() for role in server.roles]
    async with ServerManager(config, run_dir, launcher=launcher) as manager:
        return {key: await _one(manager, *key) for key in pairs}


def _windows_rid(pid: int | None) -> int | None:
    if sys.platform == "win32":
        import ctypes
        from ctypes import POINTER, byref, c_ubyte, c_uint32, c_void_p, create_string_buffer

        kernel, advapi = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL("advapi32", use_last_error=True)
        kernel.CloseHandle.argtypes = [c_void_p]
        token, needed = c_void_p(), c_uint32()
        process = kernel.GetCurrentProcess() if pid is None else kernel.OpenProcess(0x1000, False, pid)
        opened = bool(process) and bool(advapi.OpenProcessToken(process, 0x0008, byref(token)))
        if pid is not None and process:
            kernel.CloseHandle(process)
        if not opened:
            return None
        advapi.GetTokenInformation(token, 25, None, 0, byref(needed))  # TokenIntegrityLevel = 25 (winnt.h)
        buffer = create_string_buffer(needed.value)
        read = bool(needed.value) and advapi.GetTokenInformation(token, 25, buffer, needed.value, byref(needed))
        kernel.CloseHandle(token)
        sid = c_void_p.from_buffer(buffer).value if read else None
        if not sid:
            return None
        advapi.GetSidSubAuthorityCount.restype, advapi.GetSidSubAuthority.restype = POINTER(c_ubyte), POINTER(c_uint32)
        count = advapi.GetSidSubAuthorityCount(sid).contents.value
        return int(advapi.GetSidSubAuthority(sid, count - 1).contents.value) if count else None
    return None


# fmt: off
class WindowsTokens:
    def current(self) -> int | None: return _windows_rid(None)
    def of_pid(self, pid: int) -> int | None: return _windows_rid(pid)
