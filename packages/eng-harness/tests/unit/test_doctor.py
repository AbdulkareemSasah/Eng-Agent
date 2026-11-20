"""eng-harness doctor (plan 0002 T18; spec 0002 AC37, AC39, section 4.9)."""

import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from eng_contract.store import FakeLocationProbe, LocationClass

from eng_harness.adapters import Allowlist
from eng_harness.servers import ServersConfig
from eng_harness.servers._buildcheck import tool_list_fingerprint
from eng_harness.servers._procinfo import ProcessIdentity, ProcessInspector

SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}
COMMIT = "a" * 40


def _sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _tool(name: str, **extra: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "name": name,
        "kind": "session",
        "timeout_class": "session",
        "effect": "read",
        "action": "plain",
        "args_model": "StatusArgs",
        "units": "none",
        "confirm": "never",
        "products": ["ETABS"],
    }
    entry.update(extra)
    return entry


def _allowlist(entries: list[dict[str, object]], schemas: Mapping[str, Any]) -> Allowlist:
    return Allowlist.model_validate(
        {
            "adapter": "sasaah-csi-mcp",
            "sasaah_commit": COMMIT,
            "fingerprint": {"ETABS": tool_list_fingerprint(schemas)},
            "fingerprint_source": "s12-inventory",
            "tool": entries,
        }
    )


def _write(
    path: Path,
    command: str,
    sha: str,
    install: str,
    roles: list[tuple[str, str, int]],
    *,
    args: list[str] | None = None,
    cli: bool = False,
) -> None:
    blocks = [
        "[servers.csi]",
        'adapter = "sasaah-csi-mcp"',
        f"command = {json.dumps(command)}",
        f"args = {json.dumps(args if args is not None else ['--disable-script'])}",
        "client_grace_s = 5",
        "shutdown_grace_s = 1",
        f'build = {{ sasaah_commit = "{COMMIT}", exe_sha256 = "{sha}" }}',
        'host_key = "csi"',
        'product = "ETABS"',
        "",
    ]
    for name, classes, timeout in roles:
        blocks += [f"[servers.csi.roles.{name}]", f"classes = [{classes}]", f"call_timeout_s = {timeout}", ""]
    blocks += ["[host_programs.etabs]", 'executables = ["ETABS.exe"]', f"install_dirs = [{json.dumps(install)}]", ""]
    if cli:
        blocks += [
            "[cli_tools.prep]",
            'shell = "/bin/sh"',
            'script = "/opt/prep.sh"',
            "timeout_s = 15",
            'release = "unreleased"',
            'release_record = "docs/gaps/prep.md"',
            "",
        ]
    path.write_text("\n".join(blocks), encoding="utf-8")


class _Roles:
    def __init__(self, facts: Mapping[tuple[str, str], Any]) -> None:
        self._facts = facts

    def inspect(self, config: ServersConfig, run_dir: Path) -> Mapping[tuple[str, str], Any]:
        return self._facts


class _Dirs:
    def __init__(self, present: set[str]) -> None:
        self.present = present

    def exists(self, directory: str) -> bool:
        return directory in self.present


class _Procs(ProcessInspector):
    def __init__(self, ids: Mapping[int, ProcessIdentity]) -> None:
        self._ids = dict(ids)

    def identity(self, pid: int) -> ProcessIdentity | None:
        return self._ids.get(pid)

    def alive(self, identity: ProcessIdentity) -> bool:
        return self._ids.get(identity.pid) == identity

    def children(self, pid: int) -> list[ProcessIdentity]:
        return []

    def snapshot(self, exe_names: list[str]) -> list[ProcessIdentity]:
        return [item for item in self._ids.values() if item.exe_name in exe_names]

    def terminate(self, identity: ProcessIdentity) -> bool:
        return False


def _deps(doctor: Any, home: Path, **overrides: Any) -> Any:
    values: dict[str, Any] = {
        "env": {"ENG_WORKSPACE": str(home / "ws")},
        "which": lambda name: "/usr/bin/uv" if name == "uv" else None,
        "uv_version": lambda: "uv 0.9.0",
        "implementation": "CPython",
        "version": (3, 14),
        "location": FakeLocationProbe(),
        "programs": _Dirs(set()),
        "roles": _Roles({}),
        "allowlist_for": lambda _adapter: None,
        "inspector": _Procs({}),
        "tokens": None,
        "home": home,
        "windows": False,
    }
    values.update(overrides)
    return doctor.DoctorDeps(**values)


def _run(
    doctor: Any, path: Path, deps: Any, *, json_output: bool, show_paths: bool, extra: tuple[Any, ...] = ()
) -> tuple[int, str]:
    from io import StringIO

    buf = StringIO()
    code = doctor.run(path, json_output=json_output, show_paths=show_paths, extra_checks=extra, out=buf, deps=deps)
    return code, buf.getvalue()


def test_checks_and_output(tmp_path: Path) -> None:
    """AC37: every check, table and JSON with base names, exit 0 without a failure and 1 with any."""
    import eng_harness.doctor as doctor

    exe = tmp_path / "sasaah-csi-mcp"
    exe.write_bytes(b"server-bytes")
    sha = _sha(exe)
    install = tmp_path / "ETABS"
    install.mkdir()
    schemas = {"csi_status": SCHEMA}
    allowlist = _allowlist([_tool("csi_status")], schemas)
    status = {"read_only": False, "script_enabled": False, "products": ["ETABS 22"]}
    facts = {
        ("csi", "main"): doctor.RoleFacts(schemas, status, None),
        ("csi", "long"): doctor.RoleFacts(schemas, status, None),
    }
    live = ProcessIdentity(pid=7, started_at="a:b", exe_name="ETABS.exe")
    home = tmp_path / "home"
    lock_dir = home / ".local" / "state" / "eng" / "locks"
    lock_dir.mkdir(parents=True)
    (lock_dir / "host-etabs-99-100.lock").write_text("stale", encoding="utf-8")
    (lock_dir / "host-etabs-7-a_b.lock").write_text("live", encoding="utf-8")
    config = tmp_path / "harness.toml"
    _write(
        config,
        str(exe),
        sha,
        str(install),
        [("main", '"session", "call"', 30), ("long", '"long"', 900)],
    )
    deps = _deps(
        doctor,
        home,
        programs=_Dirs({str(install)}),
        roles=_Roles(facts),
        allowlist_for=lambda _adapter: allowlist,
        inspector=_Procs({7: live}),
    )
    code, table = _run(doctor, config, deps, json_output=False, show_paths=False)
    assert code == 0
    lines = [line.split(" | ") for line in table.splitlines()]
    assert [item[0] for item in lines] == ["ok"] * 5 + ["skip"] + ["ok"] * 4
    assert [item[1] for item in lines] == [
        "uv and Python",
        "server executable csi",
        "tool-list fingerprint csi/main",
        "tool-list fingerprint csi/long",
        "installed host programs",
        "integrity level",
        "workspace",
        "timeouts",
        "lock directory",
        "unreleased tools",
    ]
    joined = "\n".join(item[2] for item in lines)
    assert "uv 0.9.0" in joined
    assert "CPython 3.14" in joined
    assert "matches the allowlist" in joined
    assert "read_only=False" in joined
    assert "script_enabled=False" in joined
    assert "ETABS 22" in joined
    assert "local" in joined
    assert "Sasaah default 120 s" in joined
    assert "host-etabs-99-100.lock" in joined
    assert "host-etabs-7-a_b.lock" not in joined
    assert str(exe) not in table
    assert exe.name in table
    assert str(install) not in table
    assert "single topology" not in table
    code, text = _run(doctor, config, deps, json_output=True, show_paths=False)
    report = doctor.DoctorReport.model_validate_json(text)
    assert code == 0
    assert [(c.name, c.status) for c in report.checks] == [(item[1], item[0]) for item in lines]
    assert str(exe) not in text
    code, shown = _run(doctor, config, deps, json_output=True, show_paths=True)
    assert str(exe) in shown
    assert str(install) in shown

    _write(config, str(exe), "c" * 64, str(install), [("main", '"session", "call"', 30), ("long", '"long"', 900)])
    code, bad = _run(doctor, config, deps, json_output=True, show_paths=False)
    assert code == 1
    assert "differs" in bad

    missing = tmp_path / "missing-server"
    _write(config, str(missing), sha, str(install), [("main", '"session", "call"', 30)])
    code, gone = _run(doctor, config, deps, json_output=False, show_paths=False)
    assert code == 1
    assert "missing" in gone
    assert "single topology" in gone
    assert "30" in gone
    assert "120" in gone

    _write(
        config, str(exe), sha, str(tmp_path / "absent"), [("main", '"session", "call"', 30), ("long", '"long"', 900)]
    )
    code, absent = _run(doctor, config, deps, json_output=False, show_paths=False)
    assert code == 1
    assert "missing" in absent

    net = _deps(
        doctor,
        home,
        programs=_Dirs({str(install)}),
        roles=_Roles(facts),
        allowlist_for=lambda _adapter: allowlist,
        inspector=_Procs({}),
        location=FakeLocationProbe(default=LocationClass.NETWORK),
    )
    _write(config, str(exe), sha, str(install), [("main", '"session", "call"', 30), ("long", '"long"', 900)])
    code, network = _run(doctor, config, net, json_output=False, show_paths=False)
    assert code == 1
    assert "not local" in network

    no_uv = _deps(
        doctor,
        home,
        which=lambda _name: None,
        programs=_Dirs({str(install)}),
        roles=_Roles(facts),
        allowlist_for=lambda _adapter: allowlist,
        inspector=_Procs({}),
    )
    code, pathless = _run(doctor, config, no_uv, json_output=False, show_paths=False)
    assert code == 1
    assert "PATH" in pathless

    other = _deps(
        doctor,
        home,
        implementation="PyPy",
        version=(3, 13),
        programs=_Dirs({str(install)}),
        roles=_Roles(facts),
        allowlist_for=lambda _adapter: allowlist,
        inspector=_Procs({}),
    )
    code, python = _run(doctor, config, other, json_output=False, show_paths=False)
    assert code == 1
    assert "CPython 3.14" in python

    flagged = dict(facts)
    flagged["csi", "main"] = doctor.RoleFacts(schemas, {"read_only": True, "script_enabled": False}, None)
    flagged_deps = _deps(
        doctor,
        home,
        programs=_Dirs({str(install)}),
        roles=_Roles(flagged),
        allowlist_for=lambda _adapter: allowlist,
        inspector=_Procs({}),
    )
    code, flags = _run(doctor, config, flagged_deps, json_output=False, show_paths=False)
    assert code == 1
    assert "read_only is not false" in flags

    blocked = tmp_path / "not-a-directory"
    blocked.write_text("x", encoding="utf-8")
    blocked_deps = _deps(
        doctor,
        blocked,
        programs=_Dirs({str(install)}),
        roles=_Roles(facts),
        allowlist_for=lambda _adapter: allowlist,
        inspector=_Procs({}),
    )
    code, locked = _run(doctor, config, blocked_deps, json_output=False, show_paths=False)
    assert code == 1
    assert "not writable" in locked

    live_config = tmp_path / "live.toml"
    fake = Path(__file__).resolve().parents[1] / "fakes" / "sasaah_csi" / "server.py"
    _write(
        live_config,
        sys.executable,
        _sha(Path(sys.executable)),
        str(install),
        [("main", '"session", "call"', 30)],
        args=[str(fake), "--disable-script"],
    )
    live_deps = _deps(
        doctor,
        home,
        programs=_Dirs({str(install)}),
        roles=doctor.LiveRoles(),
        allowlist_for=lambda _adapter: allowlist,
        inspector=_Procs({}),
    )
    code, started = _run(doctor, live_config, live_deps, json_output=False, show_paths=False)
    assert "read_only=False" in started
    assert "script_enabled=False" in started
    assert code == 1  # the one-tool allowlist fingerprint is not the fake's csi_status schema


class _Warn:
    name = "page"

    def checks(self) -> tuple[Any, ...]:
        import eng_harness.doctor as doctor

        return (doctor.Check(name="page binding", status="warn", detail="127.0.0.1"),)


class _Fail:
    name = "calendar"

    def checks(self) -> tuple[Any, ...]:
        import eng_harness.doctor as doctor

        return (doctor.Check(name="calendar", status="fail", detail="not gregorian"),)


class _Boom:
    name = "locale"

    def checks(self) -> tuple[Any, ...]:
        raise RuntimeError("boom")


def test_extra_checks_and_unreleased_tools(tmp_path: Path) -> None:
    """AC39: extra checks follow section 4.9, a failure exits 1, a raising provider is one fail; unreleased warns."""
    import eng_harness.doctor as doctor

    exe = tmp_path / "sasaah-csi-mcp"
    exe.write_bytes(b"server-bytes")
    install = tmp_path / "ETABS"
    install.mkdir()
    schemas = {"csi_status": SCHEMA, "csi_attach": SCHEMA}
    entries = [
        _tool("csi_status"),
        _tool("csi_attach", release="unreleased", release_record="docs/gaps/attach.md"),
    ]
    allowlist = _allowlist(entries, schemas)
    status = {"read_only": False, "script_enabled": False}
    facts = {("csi", "main"): doctor.RoleFacts(schemas, status, None)}
    config = tmp_path / "harness.toml"
    _write(config, str(exe), _sha(exe), str(install), [("main", '"session"', 30)], cli=True)
    home = tmp_path / "home"
    deps = _deps(
        doctor,
        home,
        programs=_Dirs({str(install)}),
        roles=_Roles(facts),
        allowlist_for=lambda _adapter: allowlist,
        inspector=_Procs({}),
    )
    code, text = _run(doctor, config, deps, json_output=True, show_paths=False, extra=(_Warn(),))
    report = doctor.DoctorReport.model_validate_json(text)
    assert code == 0
    names = [item.name for item in report.checks]
    assert names[-1] == "page binding"
    assert names.index("unreleased tools") < names.index("page binding")
    released = next(item for item in report.checks if item.name == "unreleased tools")
    assert released.status == "warn"
    assert "csi_attach (docs/gaps/attach.md)" in released.detail
    assert "prep (docs/gaps/prep.md)" in released.detail

    code, failed = _run(doctor, config, deps, json_output=True, show_paths=False, extra=(_Fail(),))
    assert code == 1
    assert "not gregorian" in failed

    code, blown = _run(doctor, config, deps, json_output=True, show_paths=False, extra=(_Boom(), _Warn()))
    blown_report = doctor.DoctorReport.model_validate_json(blown)
    assert code == 1
    by_name = {item.name: item for item in blown_report.checks}
    assert by_name["locale"].status == "fail"
    assert by_name["locale"].detail == "RuntimeError"
    assert by_name["page binding"].status == "warn"
    assert blown_report.checks[-2].name == "locale"
    assert blown_report.checks[-1].name == "page binding"


def test_live_roles_use_platform_launcher(tmp_path: Path, monkeypatch: Any) -> None:
    """AC49: the roles start through `platform_launcher` over the inspector the doctor reports with."""
    import eng_harness.doctor as doctor

    seen: list[object] = []
    inspector = _Procs({})
    sentinel = object()

    class _Manager:
        def __init__(self, config: object, run_dir: Path, *, launcher: object = None) -> None:
            seen.append(launcher)
            self.servers = config

        async def __aenter__(self) -> _Manager:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

    def launcher_of(given: object) -> object:
        seen.append(given)
        return sentinel

    monkeypatch.setattr(doctor, "platform_launcher", launcher_of)
    monkeypatch.setattr(doctor, "ServerManager", _Manager)
    assert doctor.LiveRoles(inspector).inspect(ServersConfig(), tmp_path) == {}
    assert seen == [inspector, sentinel]


def test_no_config_file_and_environment(tmp_path: Path) -> None:
    """AC49: `run(None, ...)` checks no server section; `env` replaces the environment of the dependencies."""
    from io import StringIO

    import eng_harness.doctor as doctor

    home = tmp_path / "home"
    blocked = tmp_path / "file"
    blocked.write_text("not a folder", encoding="utf-8")
    deps = _deps(doctor, home, env={"ENG_WORKSPACE": str(home / "ws"), "XDG_STATE_HOME": str(blocked)})
    own = StringIO()
    assert doctor.run(None, json_output=False, show_paths=False, out=own, deps=deps) == 1
    assert "lock directory | " in own.getvalue()
    assert "not writable" in own.getvalue()
    given = StringIO()
    env = {"ENG_WORKSPACE": str(home / "ws"), "XDG_STATE_HOME": str(tmp_path / "state")}
    assert doctor.run(None, json_output=False, show_paths=False, out=given, deps=deps, env=env) == 0
    rows = [line.split(" | ") for line in given.getvalue().splitlines()]
    names = [row[1] for row in rows]
    assert not any(name.startswith(("server executable", "tool-list fingerprint")) for name in names)
    assert ["ok", "lock directory", "writable; no stale lock"] in rows
    assert ["ok", "installed host programs", "none declared"] in rows


def _write_revit(
    path: Path,
    command: str,
    sha: str,
    addin: str,
    addin_sha: str,
    pipe: str,
    *,
    write_timeout_s: int,
    read_timeout_s: int = 90,
) -> None:
    """Minimal `[servers.revit]` section (spec 0011 section 4.2)."""
    path.write_text(
        "\n".join(
            [
                "[servers.revit]",
                'adapter = "sasaah-revit-mcp"',
                f"command = {json.dumps(command)}",
                f"pipe_name = {json.dumps(pipe)}",
                "client_grace_s = 5",
                "shutdown_grace_s = 1",
                (
                    f'build = {{ sasaah_commit = "{COMMIT}", exe_sha256 = "{sha}", '
                    f'addin_sha256 = ["{addin_sha}"], addin_paths = [{json.dumps(addin)}] }}'
                ),
                'host_key = "revit"',
                "",
                "[servers.revit.roles.read]",
                'classes = ["session", "call"]',
                f"call_timeout_s = {read_timeout_s}",
                "",
                "[servers.revit.roles.write]",
                'classes = ["attended"]',
                f"call_timeout_s = {write_timeout_s}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_revit_checks(tmp_path: Path) -> None:
    """AC32: Revit doctor rows for pipe/bridge, hashes, toolset, version, document, timeout warn; fail exits 1."""
    import eng_harness.doctor as doctor

    exe = tmp_path / "sasaah-revit-mcp"
    exe.write_bytes(b"revit-server-bytes")
    addin = tmp_path / "Sasaah.Agent.Revit.Bridge.dll"
    addin.write_bytes(b"revit-addin-bytes")
    sha, addin_sha = _sha(exe), _sha(addin)
    pipe = r"\\.\pipe\sasaah.revit.bridge.v1"
    # Spec 0011 section 4.4: bridge-destructive MCP names (kind destructive).
    destructive = {
        "revit_set_type_parameter_values",
        "revit_set_element_parameter_values",
        "revit_set_parameter_value_by_guid",
        "revit_change_element_type",
    }
    schemas = dict.fromkeys(("revit_connection_status", "revit_ping", *destructive), SCHEMA)
    status = {
        "ping_status": "ok",
        "catalog_version": "cat-1",
        "pipe_name": pipe,
        "revit_version": "2026",
        "title": "Tower",
        "path": r"C:\models\Tower.rvt",
    }
    facts = {
        ("revit", "read"): doctor.RoleFacts({"revit_connection_status": SCHEMA}, status, None),
        ("revit", "write"): doctor.RoleFacts(schemas, status, None),
    }
    home = tmp_path / "home"
    config = tmp_path / "harness.toml"
    _write_revit(config, str(exe), sha, str(addin), addin_sha, pipe, write_timeout_s=90)
    deps = _deps(doctor, home, roles=_Roles(facts), inspector=_Procs({}))
    code, table = _run(doctor, config, deps, json_output=False, show_paths=False)
    assert code == 0
    lines = [line.split(" | ", 2) for line in table.splitlines()]
    by_name = {name: (row_status, detail) for row_status, name, detail in lines}
    assert "pipe and bridge revit" in by_name
    assert by_name["pipe and bridge revit"][0] == "ok"
    assert "sasaah.revit.bridge.v1" in by_name["pipe and bridge revit"][1]
    assert "ping_status=ok" in by_name["pipe and bridge revit"][1]
    assert "add-in hashes revit" in by_name
    assert by_name["add-in hashes revit"][0] == "ok"
    assert "matches" in by_name["add-in hashes revit"][1]
    assert "destructive toolset revit" in by_name
    assert by_name["destructive toolset revit"][0] == "ok"
    assert "Revit version revit" in by_name
    assert "2026" in by_name["Revit version revit"][1]
    assert "open document revit" in by_name
    assert "Tower.rvt" in by_name["open document revit"][1]
    assert "write call_timeout_s revit" in by_name
    assert by_name["write call_timeout_s revit"][0] == "ok"
    assert "60" in by_name["write call_timeout_s revit"][1]
    assert by_name["server executable revit"][0] == "ok"
    # No CSI fingerprint rows for Revit (spec 0011 AC32; CSI flags do not apply).
    assert not any(name.startswith("tool-list fingerprint revit/") for name in by_name)

    # Write timeout not greater than the add-in queue deadline (60 s, §4.2 rule 1) → warn, exit still 0.
    _write_revit(config, str(exe), sha, str(addin), addin_sha, pipe, write_timeout_s=60)
    code, warned = _run(doctor, config, deps, json_output=False, show_paths=False)
    assert code == 0
    warn_row = next(line for line in warned.splitlines() if "write call_timeout_s revit" in line)
    assert warn_row.startswith("warn |")
    assert "60" in warn_row

    # Bridge down → fail and exit 1.
    down = dict(status, ping_status="down")
    down_facts = {
        ("revit", "read"): doctor.RoleFacts({"revit_connection_status": SCHEMA}, down, None),
        ("revit", "write"): doctor.RoleFacts(schemas, down, None),
    }
    _write_revit(config, str(exe), sha, str(addin), addin_sha, pipe, write_timeout_s=90)
    code, failed = _run(
        doctor,
        config,
        _deps(doctor, home, roles=_Roles(down_facts), inspector=_Procs({})),
        json_output=False,
        show_paths=False,
    )
    assert code == 1
    assert "ping_status" in failed
    assert "fail | pipe and bridge revit |" in failed

    # Destructive toolset off (write tools missing) → fail naming bridgeToolsets.
    off_facts = {
        ("revit", "read"): doctor.RoleFacts({"revit_connection_status": SCHEMA}, status, None),
        ("revit", "write"): doctor.RoleFacts({"revit_connection_status": SCHEMA}, status, None),
    }
    code, toolset = _run(
        doctor,
        config,
        _deps(doctor, home, roles=_Roles(off_facts), inspector=_Procs({})),
        json_output=False,
        show_paths=False,
    )
    assert code == 1
    assert "bridgeToolsets" in toolset
    assert "fail | destructive toolset revit |" in toolset

    # Add-in hash mismatch → fail.
    _write_revit(config, str(exe), sha, str(addin), "b" * 64, pipe, write_timeout_s=90)
    code, bad_addin = _run(doctor, config, deps, json_output=False, show_paths=False)
    assert code == 1
    assert "fail | add-in hashes revit |" in bad_addin
