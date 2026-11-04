"""Fixtures of the fake-host workflow tests: server configuration over the synthetic fakes (spec 0002 section 9)."""

import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from eng_harness.servers import ServerConfig, ServersConfig

FAKE_CSI = Path(__file__).resolve().parents[1] / "fakes" / "sasaah_csi" / "server.py"
COMMIT = "a" * 40  # a placeholder build pin; the build check is plan task T6b
SHA = "b" * 64

ConfigFactory = Callable[..., ServersConfig]


@pytest.fixture
def control(tmp_path: Path) -> Path:
    """The fake's fault control file, empty."""
    path = tmp_path / "control.json"
    path.write_text(json.dumps({"faults": [], "seed": {}}))
    return path


@pytest.fixture
def make_config(control: Path) -> ConfigFactory:
    """Build a `ServersConfig` with one server `csi` (roles `main` and `long`) that runs a Python script."""

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
        server = ServerConfig.model_validate(
            {
                "adapter": "synthetic-csi",
                "command": command,
                "audit_log": audit_log,
                "args": [str(script)],
                "env": {"SASAAH_CSI_FAKE_CONTROL": str(control), **(env or {})},
                "client_grace_s": client_grace_s,
                "max_restarts_per_run": max_restarts,
                "shutdown_grace_s": shutdown_grace_s,
                "build": {"sasaah_commit": COMMIT, "exe_sha256": SHA},
                "host_key": "csi",
                "roles": {
                    "main": {"classes": ["session", "call"], "call_timeout_s": call_timeout_s},
                    "long": {"classes": ["long"], "call_timeout_s": call_timeout_s},
                },
            }
        )
        return ServersConfig(servers={"csi": server})

    return make
