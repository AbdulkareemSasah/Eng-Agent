"""Doctor integrity level (plan 0002 T18; spec 0002 AC37, section 4.9, architecture 16 section 6).

The decision runs on every platform over a fake token reader. The read of this process's token is defined only on
Windows (marker ``windows``) and has not run there yet: it is an owner local test. Nothing writes a token.
"""

import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from eng_contract.store import FakeLocationProbe

from eng_harness.servers._procinfo import ProcessIdentity

# winnt.h SECURITY_MANDATORY_MEDIUM_RID and SECURITY_MANDATORY_HIGH_RID, the oracle of the fake.
MEDIUM, HIGH = 0x2000, 0x3000


class _Tokens:
    """Records every call. A pid mapped to None has a token that cannot be read."""

    def __init__(self, current: int | None, pids: Mapping[int, int | None]) -> None:
        self.current_rid = current
        self.pids = dict(pids)
        self.calls: list[str] = []

    def current(self) -> int | None:
        self.calls.append("current")
        return self.current_rid

    def of_pid(self, pid: int) -> int | None:
        self.calls.append(f"of_pid {pid}")
        if pid not in self.pids:
            return None
        return self.pids[pid]


class _Roles:
    def inspect(self, config: Any, run_dir: Path) -> Mapping[tuple[str, str], Any]:
        return {}


class _Dirs:
    def exists(self, directory: str) -> bool:
        return True


class _Procs:
    def __init__(self, running: list[ProcessIdentity]) -> None:
        self.running = running

    def identity(self, pid: int) -> ProcessIdentity | None:
        for item in self.running:
            if item.pid == pid:
                return item
        return None

    def alive(self, identity: ProcessIdentity) -> bool:
        return self.identity(identity.pid) == identity

    def children(self, pid: int) -> list[ProcessIdentity]:
        return []

    def snapshot(self, exe_names: list[str]) -> list[ProcessIdentity]:
        return [item for item in self.running if item.exe_name in exe_names]

    def terminate(self, identity: ProcessIdentity) -> bool:
        return False


def _report(doctor: Any, tmp_path: Path, tokens: Any, running: list[ProcessIdentity]) -> Any:
    from io import StringIO

    tmp_path.mkdir(parents=True, exist_ok=True)
    exe = tmp_path / "sasaah-csi-mcp"
    exe.write_bytes(b"server")
    install = str(tmp_path / "ETABS")
    config = tmp_path / "harness.toml"
    config.write_text(
        "\n".join(
            [
                "[servers.csi]",
                'adapter = "sasaah-csi-mcp"',
                f"command = {json.dumps(str(exe))}",
                'args = ["--disable-script"]',
                "client_grace_s = 5",
                f'build = {{ sasaah_commit = "{"a" * 40}", exe_sha256 = "{"b" * 64} }}',
                'host_key = "csi"',
                "",
                "[servers.csi.roles.main]",
                'classes = ["session"]',
                "call_timeout_s = 30",
                "",
                "[host_programs.etabs]",
                'executables = ["ETABS.exe"]',
                f"install_dirs = [{json.dumps(install)}]",
                "",
            ]
        ),
        encoding="utf-8",
    )
    with exe.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    config.write_text(config.read_text(encoding="utf-8").replace("b" * 64, digest), encoding="utf-8")
    deps = doctor.DoctorDeps(
        env={"ENG_WORKSPACE": str(tmp_path / "ws")},
        which=lambda name: "/usr/bin/uv" if name == "uv" else None,
        uv_version=lambda: "uv 0.9.0",
        implementation="CPython",
        version=(3, 14),
        location=FakeLocationProbe(),
        programs=_Dirs(),
        roles=_Roles(),
        allowlist_for=lambda _adapter: None,
        inspector=_Procs(running),
        tokens=tokens,
        home=tmp_path / "home",
        windows=True,
    )
    buf = StringIO()
    doctor.run(config, json_output=True, show_paths=False, out=buf, deps=deps)
    return doctor.DoctorReport.model_validate_json(buf.getvalue())


def test_integrity_level(tmp_path: Path) -> None:
    """Warn when the process is not medium; a host token that cannot be read is skip. Nothing is changed."""
    import eng_harness.doctor as doctor

    host = ProcessIdentity(pid=42, started_at="100", exe_name="ETABS.exe")
    high = _Tokens(HIGH, {42: None})
    report = _report(doctor, tmp_path / "high", high, [host])
    levels = [item for item in report.checks if item.name.startswith("integrity level")]
    assert [(item.name, item.status) for item in levels] == [
        ("integrity level", "warn"),
        ("integrity level ETABS.exe", "skip"),
    ]
    assert "not medium" in levels[0].detail
    assert "high" in levels[0].detail
    assert "cannot be read" in levels[1].detail
    assert all(not call.startswith("Set") for call in high.calls)

    medium = _Tokens(MEDIUM, {42: MEDIUM})
    ok = _report(doctor, tmp_path / "medium", medium, [host])
    ok_levels = [item for item in ok.checks if item.name.startswith("integrity level")]
    assert [(item.name, item.status) for item in ok_levels] == [
        ("integrity level", "ok"),
        ("integrity level ETABS.exe", "ok"),
    ]
    assert ok_levels[0].detail == "medium"
    assert all(not call.startswith("Set") for call in medium.calls)

    if sys.platform == "win32":
        real = doctor.WindowsTokens()
        first, second = real.current(), real.current()
        assert first is not None
        assert first == second
        probed = _report(doctor, tmp_path / "real", real, [])
        own = next(item for item in probed.checks if item.name == "integrity level")
        assert own.status in {"ok", "warn"}
