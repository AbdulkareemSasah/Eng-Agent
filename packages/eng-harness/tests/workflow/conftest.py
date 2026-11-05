"""Fixtures of the fake-host workflow tests: server configuration over the synthetic fakes (spec 0002 section 9)."""

import hashlib
import json
import sys
from collections.abc import Callable
from functools import cache
from pathlib import Path

import pytest

from eng_harness.adapters.csi import csi_allowlist
from eng_harness.servers import ServerConfig, ServersConfig

FAKE_CSI = Path(__file__).resolve().parents[1] / "fakes" / "sasaah_csi" / "server.py"
COMMIT = csi_allowlist().sasaah_commit  # the build pins are the real ones (plan 0002 T6b), so the build check passes

ConfigFactory = Callable[..., ServersConfig]


@cache
def exe_sha256() -> str:
    """SHA-256 of the interpreter, the "server executable" of the fakes."""
    with Path(sys.executable).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


@pytest.fixture
def control(tmp_path: Path) -> Path:
    """The fake's fault control file, empty."""
    path = tmp_path / "control.json"
    path.write_text(json.dumps({"faults": [], "seed": {}}))
    return path


@pytest.fixture
def make_config(control: Path) -> ConfigFactory:
    """Build a `ServersConfig` with one server `csi` (roles `main` and `long`) that runs a Python script.

    The section names the adapter `sasaah-csi-mcp`, with `--disable-script` (spec 0002 section 4.2 rule 3), only when
    the script is the CSI fake; other doubles keep the adapter `synthetic-csi` and their arguments.
    """

    def make(
        script: Path = FAKE_CSI,
        *,
        max_restarts: int = 1,
        call_timeout_s: int = 30,
        client_grace_s: int = 5,
        shutdown_grace_s: int = 5,
        command: str = sys.executable,
        audit_log: bool = True,
        env: dict[str, str] | None = None,
    ) -> ServersConfig:
        is_csi = script == FAKE_CSI
        server = ServerConfig.model_validate(
            {
                "adapter": "sasaah-csi-mcp" if is_csi else "synthetic-csi",
                "command": command,
                "audit_log": audit_log,
                "args": [str(script), *(["--disable-script"] if is_csi else [])],
                "env": {"SASAAH_CSI_FAKE_CONTROL": str(control), **(env or {})},
                "client_grace_s": client_grace_s,
                "max_restarts_per_run": max_restarts,
                "shutdown_grace_s": shutdown_grace_s,
                "build": {"sasaah_commit": COMMIT, "exe_sha256": exe_sha256()},
                "host_key": "csi",
                "roles": {
                    "main": {"classes": ["session", "call"], "call_timeout_s": call_timeout_s},
                    "long": {"classes": ["long"], "call_timeout_s": call_timeout_s},
                },
            }
        )
        return ServersConfig(servers={"csi": server})

    return make
