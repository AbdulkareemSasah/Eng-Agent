"""IDEA reconciliation of set_loads and calculate (plan 0014 T8; spec 0014 AC18, section 4.8)."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import anyio
from fakes.sasaah_idea.test_server import make_ideacon

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._toolport import Binding, LostWrite
from eng_harness.adapters.idea import idea_allowlist
from eng_harness.adapters.idea._tools import NativeSetLoadsArgs
from eng_harness.servers import CallEffect, ServerManager, ServersConfig


def _idea_config(tmp_path: Path, control: Path) -> ServersConfig:
    fake = Path(__file__).resolve().parents[2] / "fakes" / "sasaah_idea" / "server.py"
    if not control.exists():
        control.write_text(json.dumps({"faults": [], "seed": {}}), encoding="utf-8")
    wrapper = tmp_path / "sasaah-idea-mcp"
    wrapper.write_text(
        f'#!/bin/sh\nexport SASAAH_IDEA_FAKE_CONTROL="{control}"\nexec "{sys.executable}" "{fake}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    exe = hashlib.sha256(wrapper.read_bytes()).hexdigest()
    allowlist = idea_allowlist()
    return ServersConfig.model_validate(
        {
            "servers": {
                "idea": {
                    "adapter": "sasaah-idea-mcp",
                    "command": str(wrapper),
                    "args": ["--disable-script"],
                    "route": "native",
                    "audit_log": False,
                    "client_grace_s": 2,
                    "shutdown_grace_s": 5,
                    "max_restarts_per_run": 1,
                    "build": {"sasaah_commit": allowlist.sasaah_commit, "exe_sha256": exe},
                    "host_key": "idea",
                    "roles": {
                        "main": {
                            "classes": ["session", "call", "long"],
                            "call_timeout_s": 5,
                        }
                    },
                }
            }
        }
    )


def _binding() -> Binding:
    return Binding(target=HostTarget(product="IDEA", pid=1), host=None, owned=True, pre_image_ref=None)


def _lost_set_loads(*, path: str, out_path: str, loads: list[dict[str, Any]], connection_id: str = "CON1") -> LostWrite:
    allowlist = idea_allowlist(route="native")
    descriptor = allowlist.descriptor("idea_native_set_loads")
    model = NativeSetLoadsArgs(
        path=path,
        loads=loads,
        connection_id=connection_id,
        out_path=out_path,
    )
    return LostWrite(descriptor=descriptor, model=model, binding=_binding(), known=True, pre_image=None)


def _lost_calculate() -> LostWrite:
    from eng_harness.adapters.idea._tools import CalculateArgs

    allowlist = idea_allowlist(route="rest")
    descriptor = allowlist.descriptor("idea_calculate")
    model = CalculateArgs(connection_ids=[1])
    return LostWrite(descriptor=descriptor, model=model, binding=_binding(), known=False, pre_image=None)


def _sample_loads() -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "name": "LE1",
            "checkEquilibrium": True,
            "forcesOnSegments": [
                {
                    "beamSegmentId": 1,
                    "position": 0.0,
                    "n": 25000.0,
                    "qy": 0.0,
                    "qz": 0.0,
                    "mx": 0.0,
                    "my": 0.0,
                    "mz": 0.0,
                }
            ],
            "forcesPercentageOnSegments": None,
        }
    ]


def test_set_loads_outcomes(tmp_path: Path) -> None:
    """AC18: idea_native_set_loads → applied (file+read-back), not_applied (no file), else unknown."""
    from eng_harness.adapters.idea._reconcile import IdeaReconciler

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    src = make_ideacon(run_dir / "src.ideaCon")
    loads = _sample_loads()
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)  # test-only synthetic value; not a cited engineering number

    async def body() -> None:
        async with ServerManager(config, run_dir) as manager:

            async def read(tool: str, args: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
                result = await manager.call("idea", "main", tool, args, effect)
                assert result.is_error is False
                from eng_harness.servers._session import reply_body

                body_json = reply_body(result)
                assert body_json is not None
                return body_json

            # applied: write succeeds (no timeout); out_path exists and reads back as requested
            out_ok = run_dir / "out_ok.ideaCon"
            write = await manager.call(
                "idea",
                "main",
                "idea_native_set_loads",
                {
                    "path": str(src),
                    "loads": loads,
                    "connection_id": "CON1",
                    "out_path": str(out_ok),
                    "confirm": True,
                },
                CallEffect.WRITE,
            )
            assert write.is_error is False
            assert out_ok.is_file()
            lost_ok = _lost_set_loads(path=str(src), out_path=str(out_ok), loads=loads)
            decided_ok = await reconciler.decide(lost_ok, read)
            assert decided_ok.outcome == "applied"

            # not_applied: out_path never written
            missing = run_dir / "never_written.ideaCon"
            assert not missing.exists()
            lost_missing = _lost_set_loads(path=str(src), out_path=str(missing), loads=loads)
            decided_missing = await reconciler.decide(lost_missing, read)
            assert decided_missing.outcome == "not_applied"

            # unknown: file exists but read-back does not match the requested loads
            out_bad = run_dir / "out_bad.ideaCon"
            write_bad = await manager.call(
                "idea",
                "main",
                "idea_native_set_loads",
                {
                    "path": str(src),
                    "loads": loads,
                    "connection_id": "CON1",
                    "out_path": str(out_bad),
                    "confirm": True,
                },
                CallEffect.WRITE,
            )
            assert write_bad.is_error is False
            data = json.loads(out_bad.read_text(encoding="utf-8"))
            for conn in data.get("connections", []):
                for effect_row in conn.get("loads", []):
                    segs = effect_row.get("forcesOnSegments") or []
                    if segs:
                        segs[0]["n"] = float(segs[0].get("n", 0.0)) + 1000.0
            out_bad.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            lost_bad = _lost_set_loads(path=str(src), out_path=str(out_bad), loads=loads)
            decided_bad = await reconciler.decide(lost_bad, read)
            assert decided_bad.outcome == "unknown"

    anyio.run(body)


def test_calculate_unknown_no_rerun(tmp_path: Path) -> None:
    """AC18: reconciling idea_calculate always answers unknown; the adapter re-runs nothing."""
    from eng_harness.adapters.idea._reconcile import IdeaReconciler

    control = tmp_path / "control.json"
    # Rest route needed for idea_calculate; reopen config with route rest.
    fake = Path(__file__).resolve().parents[2] / "fakes" / "sasaah_idea" / "server.py"
    wrapper = tmp_path / "sasaah-idea-mcp-rest"
    wrapper.write_text(
        f'#!/bin/sh\nexport SASAAH_IDEA_FAKE_CONTROL="{control}"\nexec "{sys.executable}" "{fake}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    exe = hashlib.sha256(wrapper.read_bytes()).hexdigest()
    allowlist = idea_allowlist()
    rest_config = ServersConfig.model_validate(
        {
            "servers": {
                "idea": {
                    "adapter": "sasaah-idea-mcp",
                    "command": str(wrapper),
                    "args": ["--disable-script"],
                    "route": "rest",
                    "service_url": "http://127.0.0.1:9/",
                    "audit_log": False,
                    "client_grace_s": 2,
                    "shutdown_grace_s": 5,
                    "max_restarts_per_run": 1,
                    "build": {"sasaah_commit": allowlist.sasaah_commit, "exe_sha256": exe},
                    "host_key": "idea",
                    "roles": {"main": {"classes": ["session", "call", "long"], "call_timeout_s": 5}},
                }
            }
        }
    )
    model = make_ideacon(tmp_path / "joint.ideaCon")
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)  # test-only synthetic value; not a cited engineering number
    call_log: list[str] = []

    async def body() -> None:
        async with ServerManager(rest_config, tmp_path / "run") as manager:
            opened = await manager.call("idea", "main", "idea_open_project", {"path": str(model)}, CallEffect.WRITE)
            assert opened.is_error is False

            async def read(tool: str, args: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
                call_log.append(tool)
                result = await manager.call("idea", "main", tool, args, effect)
                if result.is_error:
                    raise AssertionError(f"unexpected host error on {tool}")
                from eng_harness.servers._session import reply_body

                body_json = reply_body(result)
                assert body_json is not None
                return body_json

            lost = _lost_calculate()
            decided = await reconciler.decide(lost, read)
            assert decided.outcome == "unknown"
            assert "idea_calculate" not in call_log
            assert "idea_get_check_results" not in call_log
            assert "idea_native_calculate" not in call_log

    anyio.run(body)
