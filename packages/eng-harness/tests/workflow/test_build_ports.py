"""Production CSI wiring contracts (plan 0002 T19a; AC41, AC43 to AC45)."""

import hashlib
import json
import shutil
import stat
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.envelope import SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode, Precondition, WarningCode
from eng_contract.refs import RefRule, resolve_ref
from fakes.sasaah_csi.wiring import Rig, config, rig

from eng_harness.adapters import AllowlistError, load_allowlist
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters.csi import csi_allowlist
from eng_harness.engine import RunStatus
from eng_harness.journal import _events as ev
from eng_harness.servers import CallEffect, ConfigError, ServersConfig

CLI_FAKES = Path(__file__).resolve().parents[1] / "fakes" / "sasaah_cli"
CLI_OP = "op_0123456789abcdef0123456789abcdef"


async def opened(r: Any, p: Any) -> None:
    result = await p.tool_port.call("csi_open_model", {"model": "m"}, op_id="open", model="m")
    assert isinstance(result, SuccessEnvelope), result


def with_cli_tools(r: Rig, root: Path, **release: Any) -> ServersConfig:
    """The CSI configuration of `r` plus three `[cli_tools.*]` entries over the Python stand-ins of the scripts."""
    tools = root / "cli-tools"
    shutil.copytree(CLI_FAKES, tools)
    shell = root / "pwsh"  # takes the PowerShell switches and runs the script in Python
    shell.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{tools / "pwsh.py"}" "$@"\n')
    shell.chmod(shell.stat().st_mode | stat.S_IXUSR)
    artifact = root / "prep.exe"
    artifact.write_bytes(b"cached-cli-v1")
    pin = {"path": str(artifact), "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}

    def entry(script: str, output: str) -> dict[str, Any]:
        return {
            "shell": str(shell), "script": str(tools / script), "outputs": [output], "timeout_s": 20,
            "build_artifacts": [pin],
        }  # fmt: skip

    entries = {
        "dxf-prep/prepare": entry("run_prepare.py", "prepared.json"),
        "dxf-prep/inspect": entry("run_inspect.py", "inspection.json"),
        "etabs-model/build": entry("run_build.py", "model.json") | release,
    }
    return config(r.control).model_copy(
        update={"cli_tools": ServersConfig.model_validate({"cli_tools": entries}).cli_tools}
    )


def test_allowlist_loaded_for_route(tmp_path: Path) -> None:
    r = rig(tmp_path)
    text = Path(__file__).parents[2].joinpath("src/eng_harness/adapters/csi/_allowlist.toml").read_text()
    routed = 'routes = ["left", "right"]\n' + text.replace("{ name = ", '{ routes = ["left"], name = ')
    calls: list[str | None] = []

    def loader(route: str | None) -> Any:
        calls.append(route)
        return load_allowlist(routed, "synthetic", route=route)

    cfg = config(r.control)
    section = cfg.servers["csi"].model_copy(update={"route": "left"})
    cfg = cfg.model_copy(update={"servers": {"csi": section}})
    p = r.ports(config=cfg, allowlists={"sasaah-csi-mcp": loader})
    assert p.servers is not None
    assert calls == ["left"]
    with pytest.raises(AllowlistError, match="no routes"):
        r.ports(config=cfg)
    with pytest.raises(AllowlistError, match="no routes"):
        csi_allowlist("left")


def test_allowlist_loaded_for_the_servers_product(tmp_path: Path) -> None:
    """Spec 0008 4.1: the build check of a server is made from the allowlist loaded for the server's product."""
    r = rig(tmp_path)
    text = Path(__file__).parents[2].joinpath("src/eng_harness/adapters/csi/_allowlist.toml").read_text()
    status = '{ name = "csi_status"'
    entries = [
        line
        for line in text.splitlines()
        if not line.lstrip().startswith("{ name = ") or line.lstrip().startswith(status)
    ]
    replaced = "\n".join(
        f'fingerprint = {{ SAFE = "{"c" * 64}", ETABS = "{"b" * 64}" }}' if line.startswith("fingerprint = ") else line
        for line in entries
    )
    cfg = config(r.control)
    section = cfg.servers["csi"].model_copy(update={"product": "SAFE"})
    program = cfg.host_programs["etabs"].model_copy(update={"executables": ("SAFE.exe",)})
    cfg = cfg.model_copy(update={"servers": {"csi": section}, "host_programs": {"safe": program}})
    p = r.ports(
        config=cfg, allowlists={"sasaah-csi-mcp": lambda route: load_allowlist(replaced, "synthetic", route=route)}
    )
    want = p.servers._check["csi"]
    assert (want.product, want.tool_fingerprint, want.tool_names) == ("SAFE", "c" * 64, frozenset({"csi_status"}))


def test_cli_tool_routed_through_build_ports(tmp_path: Path) -> None:
    """AC43: a `[cli_tools.*]` entry is served by the command-line adapter, a CSI tool still by the CSI one."""
    r = rig(tmp_path)
    cfg = with_cli_tools(r, tmp_path)
    dxf = tmp_path / "plan.dxf"
    dxf.write_bytes(b"0\nSECTION\n")

    async def body() -> None:
        async with r.ports(config=cfg) as p:
            prepare = await p.tool_port.describe("dxf-prep/prepare")
            assert (prepare.effect, prepare.action, prepare.host_key) == ("read", "plain", "dxf-prep")
            assert prepare.engineering_params == ("SnapTol_mm", "BeamSpacing_mm", "ColumnGrow_mm")
            build = await p.tool_port.describe("etabs-model/build")
            assert (build.effect, build.host_key) == ("write", "etabs-model")
            assert (await p.tool_port.describe("csi_open_model")).host_key == "csi"
            args = {"dxf": str(dxf), "SnapTol_mm": r.value("SnapTol_mm", 5.0)}
            done = await p.tool_port.call("dxf-prep/prepare", args, op_id=CLI_OP, model=None)
            assert isinstance(done, SuccessEnvelope), done
            assert done.kind == "harness.cli_run/1"
            echoed = json.loads((r.run_dir / "tools" / CLI_OP / "prepared.json").read_text())["args"]
            assert echoed == {"OutDir": str(r.run_dir / "tools" / CLI_OP), "Dxf": str(dxf), "SnapTol": "0.005"}
            await opened(r, p)  # the CSI tools are served as before

    anyio.run(body)


def test_binder_from_host_port(tmp_path: Path) -> None:
    r = rig(tmp_path)

    async def body() -> None:
        async with r.ports(visible=True) as p:
            d = p.tool_port._find("csi_assign_frame_section")
            with pytest.raises(ContractError) as missing:
                await p.host_port.binding("csi", "m", d)
            assert (missing.value.detail.code, missing.value.detail.precondition) == (
                ErrorCode.PRECONDITION_FAILED,
                Precondition.model_open,
            )
            with pytest.raises(ContractError):
                await p.host_port.binding("other", "m", d)
            await opened(r, p)
            bound = await p.host_port.binding("csi", "m", d)
            assert bound.owned
            assert bound.target.product == "ETABS"
            assert bound.host.program == "etabs"
            assert bound.host.version == "22.0.0"
            assert p.host_port.last_read("m") is None  # fallback info never becomes an outside-edit baseline
            assert p.host_port.revision(bound.host.model_id) == bound.host.model_revision == 0
            assert p.host_port.revision("mdl_" + "0" * 26) is None
            held = await p.host_port.locate("m")
            state = await p.host_port.model_state("m", held.instance_id)
            assert state.model_id == bound.host.model_id
            read = p.host_port.last_read("m")
            p.host_port._reads["m"] = replace(
                read, status=read.status.model_copy(update={"program_version": "from-state"})
            )
            assert (await p.host_port.binding("csi", "m", d)).host.version == "from-state"
            p.host_port._reads["m"] = read
            assert (await p.host_port.binding("csi", None, d)).host == bound.host
            assert r.calls("csi_launch")[0]["visible"] is True
            lease = await p.host_port.acquire("csi")
            await p.host_port.release(lease)
            assert p.host_port.model_files("m") == (r.original.resolve(),)

    anyio.run(body)


@pytest.mark.parametrize("identity", ["live", "dead", "reused"])
def test_preflight_attaches_only_to_live_cached_identity(tmp_path: Path, identity: str) -> None:
    r = rig(tmp_path)

    async def body() -> None:
        async with r.ports() as p:
            await opened(r, p)
            instance = await p.host_port.locate("m")
            assert instance is not None
            expected = await p.host_port.read_units("m", instance.instance_id)
            await p.host_port.release(await p.host_port.acquire("csi"))

        data = json.loads(r.control.read_text())
        assert data["launched"] == [instance.pid]
        if identity == "dead":
            data["launched"] = []
        elif identity == "reused":
            # The fake inspector derives start order from this list. The same PID now has a different start time.
            data["launched"] = [instance.pid + 1, instance.pid]
        r.control.write_text(json.dumps(data))
        before = len(r.calls("csi_attach"))
        async with r.ports() as resumed:
            checks = await resumed.host_port.preflight({"csi": csi_allowlist().sasaah_commit})
            assert len(checks) == 1
            assert checks[0].ok, checks
            attached = r.calls("csi_attach")[before:]
            assert [call["pid"] for call in attached] == ([instance.pid] if identity == "live" else [])
            assert resumed.host_port.model_files("m") == (r.original.resolve(),)
            assert await resumed.host_port.started_instances("csi") == [instance]
            found = await resumed.host_port.locate("m")
            assert found == (instance if identity == "live" else None)
            units = await resumed.host_port.read_units("m", instance.instance_id)
            assert units.loaded is (identity == "live")
            assert units.expected == expected.expected

    anyio.run(body)


def test_csi_wiring_shares_book_and_pre_image(tmp_path: Path) -> None:
    r = rig(tmp_path)

    async def body() -> None:
        async with r.ports() as p:
            await opened(r, p)
            held = await p.host_port.locate("m")
            await p.host_port.model_state("m", held.instance_id)
            args = {"model": "m", "frame": "F1", "section": "C40"}
            answer = await p.tool_port.call("csi_assign_frame_section", args, op_id="assign", model="m")
            assert isinstance(answer, SuccessEnvelope), answer
            entry = WriteLedger(r.run_dir).find("assign")
            assert entry is not None
            assert entry.pre_image_ref is not None
            observed = resolve_ref(entry.pre_image_ref, RefRule(), r.store, p.host_port.revision).value
            assert isinstance(observed, dict)
            assert observed["section"] == "C30"
            await p.host_port.model_state("m", held.instance_id)
            checked = await p.host_port.check_model("m")
            assert checked.summary["clean"] is True
            assert WarningCode.MODEL_CHANGED_OUTSIDE not in [w.code for w in checked.warnings]
            assert p.host_port._readback.written.items("m") == []
            assert r.calls("csi_assign_frame_section")
            saved = await p.tool_port.call(
                "csi_save_model", {"model": "m", "as_new_revision": True}, op_id="s", model="m"
            )
            assert isinstance(saved, SuccessEnvelope)
            snapshot = r.run_dir / "adapter" / "revisions.json"
            records = json.loads(snapshot.read_text())
            assert records
            saved_file = saved.summary["saved_file"]
            assert isinstance(saved_file, dict)
            restored = await p.tool_port.call(
                "csi_open_revision",
                {"model": "m", "revision": saved_file["name"]},
                op_id="r",
                model="m",
            )
            assert isinstance(restored, SuccessEnvelope), restored
            assert p.host_port.model_files("m")[0].name != r.original.name
            assert await p.host_port.locate("m") is not None

    anyio.run(body)


def test_csi_preview_sends_no_write(tmp_path: Path) -> None:
    r = rig(tmp_path)

    async def body() -> None:
        async with r.ports() as p:
            args = {"model": "m", "frame": "F1", "section": "C40"}
            with pytest.raises(ContractError) as closed:
                await p.tool_port.preview("csi_assign_frame_section", args)
            assert closed.value.detail.precondition is Precondition.model_open
            await opened(r, p)
            preview = await p.tool_port.preview("csi_assign_frame_section", args)
            assert len(preview.items) == len(preview.models) == 1
            assert preview.items[0].id == "csi_assign_frame_section"
            assert "m" in preview.items[0].label
            assert preview.diff_ref is None
            assert len(preview.items[0].refs) == 2
            assert r.store.payload(preview.items[0].refs[0].ref) == {"value": args}
            observed = resolve_ref(preview.items[0].refs[1], RefRule(), r.store, lambda _: None).value
            assert isinstance(observed, dict)
            assert observed["section"] == "C30"
            assert r.calls("csi_assign_frame_section") == []
            assert not (r.run_dir / "adapter" / "ops.jsonl").exists()

    anyio.run(body)


def test_open_preview_without_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    r = rig(tmp_path)

    async def body() -> None:
        async with r.ports() as p:

            async def forbidden(*args: Any) -> Any:
                raise AssertionError("an unbound open preview read the binder")

            monkeypatch.setattr(p.tool_port._binder, "binding", forbidden)
            preview = await p.tool_port.preview("csi_open_model", {"model": "m"})
            assert preview.models == ()
            assert len(preview.items[0].refs) == 1
            assert r.calls("csi_model_info") == r.calls("csi_launch") == r.calls("csi_open_model") == []
            assert await p.host_port.locate("m") is None

    anyio.run(body)


@pytest.mark.parametrize(("tolerance", "clean"), [(0.25, True), (0.0, False), (None, False), ("missing", False)])
def test_readback_tolerance_from_run_basis(tmp_path: Path, tolerance: Any, clean: bool) -> None:
    r = rig(tmp_path, tolerance=tolerance)

    async def body() -> None:
        # The header belongs to this run and freezes this exact value; construction happens before it exists.
        p = r.ports()
        engine = r.engine(p, [], paused=True)
        async with p:
            await engine.start(r.request())
            await opened(r, p)
            args = {
                "model": "m",
                "frame": "F1",
                "pattern": "DEAD",
                "w_kN_m": r.value("w_kN_m", 8.0),
                "direction": "gravity",
            }
            assert isinstance(
                await p.tool_port.call("csi_set_frame_load_distributed", args, op_id="load", model="m"), SuccessEnvelope
            )
            await p.servers.call(
                "csi",
                "main",
                "csi_set_frame_load_distributed",
                {
                    "target": {"product": "ETABS", "pid": 4242},
                    "name": "F1",
                    "load_pattern": "DEAD",
                    "value": 10.0,
                    "direction": "gravity",
                    "units": "kN_m_C",
                    "confirm": True,
                },
                CallEffect.WRITE,
            )
            check = await p.host_port.check_model("m")
            assert check.summary["clean"] is clean
            if not clean:
                issues = r.store.payload(check.result_id)["issues"]
                assert isinstance(issues, list)
                assert all(isinstance(issue, dict) for issue in issues)
                codes = [issue["code"] for issue in issues if isinstance(issue, dict)]
                assert ("READBACK_MISMATCH" if tolerance == 0.0 else "READBACK_UNAVAILABLE") in codes
            reconciliation = await p.tool_port.reconcile("csi_set_frame_load_distributed", args, "load")
            assert reconciliation.outcome == ("applied" if clean else "unknown")
            await p.host_port.release(await p.host_port.acquire("csi"))
        # A new engine resumes using the original header, even though another basis is now selected by the caller.
        r.basis_ref = r.value("different_basis", 0.0)["$ref"].split("#")[0]
        async with r.ports() as resumed:
            await r.engine(resumed, [], paused=True).resume(r.run_id)
            assert isinstance(
                await resumed.tool_port.call("csi_set_frame_load_distributed", args, op_id="again", model="m"),
                SuccessEnvelope,
            )
            answer = await resumed.host_port.check_model("m")
            assert answer.summary["clean"] is (tolerance in (0.25, 0.0))

    anyio.run(body)


@pytest.mark.parametrize("basis", ["missing_header", "invalid_ref", "wrong_kind", True, "not_number", None, 0.0])
def test_frozen_provider_never_defaults(tmp_path: Path, basis: Any) -> None:
    from eng_harness.adapters import _FrozenTolerance

    r = rig(tmp_path, tolerance=basis)
    provider = _FrozenTolerance(r.run_dir, r.store)
    assert provider() is None
    if basis == "missing_header":
        return
    if basis == "invalid_ref":
        r.basis_ref = "res_" + "0" * 26
    if basis == "wrong_kind":
        r.basis_ref = r.value("n", 1.0)["$ref"].split("#")[0]

    async def body() -> None:
        async with r.ports() as p:
            await r.engine(p, []).start(r.request())
            expected = 0.0 if basis == 0.0 and not isinstance(basis, bool) else None
            assert provider() == expected
            assert _FrozenTolerance(r.run_dir, r.store)() == expected

    anyio.run(body)


def test_bound_open_preview_and_hand_wired_pre_image(tmp_path: Path) -> None:
    from eng_contract.envelope import Provenance

    from eng_harness.adapters.csi._tools import CsiToolPort

    r = rig(tmp_path)

    async def body() -> None:
        async with r.ports() as p:
            await opened(r, p)
            preview = await p.tool_port.preview("csi_open_model", {"model": "m"})
            assert len(preview.models) == 1
            assert preview.models[0].model_key == "m"
            assert preview.models[0].revision == 0
            producer = Provenance(
                tool="test/wiring", tool_version="1", inputs={}, started_at=r.clock.now(), duration_ms=0
            )
            old = r.store.put("harness.run_output/1", {"value": {"observed": {"section": "C30"}}}, producer)
            ref = f"{old.result_id}#/value/observed"

            class Binder:
                async def binding(self, host_key: Any, key: Any, descriptor: Any) -> Any:
                    bound = await p.host_port.binding(host_key, key, descriptor)
                    return bound.model_copy(update={"pre_image_ref": ref})

                def revision(self, model_id: str) -> int | None:
                    value = p.host_port.revision(model_id)
                    assert value is None or isinstance(value, int)
                    return value

            hand = CsiToolPort(
                config=config(r.control),
                server="csi",
                caller=p.servers,
                binder=Binder(),
                store=r.store,
                ledger=WriteLedger(r.run_dir),
                clock=r.clock,
                ids=r.ids,
                check=p.tool_port._check,
            )
            args = {"model": "m", "frame": "F1", "section": "C40"}
            before = len(r.calls("csi_list_frames"))
            shown = await hand.preview("csi_assign_frame_section", args)
            assert shown.items[0].refs[1].ref == ref
            answer = await hand.call("csi_assign_frame_section", args, op_id="hand", model="m")
            assert isinstance(answer, SuccessEnvelope)
            entry = WriteLedger(r.run_dir).find("hand")
            assert entry is not None
            assert entry.pre_image_ref == ref
            assert len(r.calls("csi_list_frames")) == before

    anyio.run(body)


def test_binding_does_not_consume_outside_file_edit(tmp_path: Path) -> None:
    r = rig(tmp_path)

    async def body() -> None:
        async with r.ports() as p:
            await opened(r, p)
            held = await p.host_port.locate("m")
            before = await p.host_port.model_state("m", held.instance_id)
            r.original.write_bytes(b"outside edit")
            d = p.tool_port._find("csi_assign_frame_section")
            binding = await p.host_port.binding("csi", "m", d)
            assert binding.host.model_revision == before.revision
            changed = await p.host_port.model_state("m", held.instance_id)
            assert changed.revision > before.revision
            assert p.host_port.take_warnings() == [("m", WarningCode.MODEL_CHANGED_OUTSIDE)]

    anyio.run(body)


def test_platform_defaults_and_host_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from eng_harness import adapters
    from eng_harness.servers import ConfigError, platform_inspector, platform_launcher

    r = rig(tmp_path)
    inspector = platform_inspector()
    launcher = platform_launcher(inspector)
    used: list[Any] = []
    monkeypatch.setattr(adapters, "platform_inspector", lambda: inspector)

    def platform(found: Any) -> Any:
        used.append(found)
        return launcher

    monkeypatch.setattr(adapters, "platform_launcher", platform)
    p: Any = adapters.build_ports(
        config(r.control), r.workspace, r.store, r.run_dir, r.clock, r.ids, lock_dir=r.root / "locks"
    )
    assert used == [inspector]
    assert p.host_port._session._inspector is inspector
    assert p.host_port._session._exe == "ETABS.exe"
    assert p.host_port._program == "etabs"
    assert p.servers._launcher is launcher
    assert p.tool_port._check.ok is False
    assert p.tool_port._check.fingerprint == p.tool_port._check.expected_fingerprint == ""
    assert not r.run_dir.exists()
    cfg = config(r.control).model_copy(update={"host_programs": {}})
    with pytest.raises(ConfigError, match=r"host_programs\.etabs"):
        adapters.build_ports(cfg, r.workspace, r.store, r.run_dir, r.clock, r.ids)


def test_routed_port_methods(tmp_path: Path) -> None:
    """AC43: every `ToolPort` method of a command-line tool reaches the command-line adapter, the rest the CSI one."""
    r = rig(tmp_path)
    record = "docs/gaps/cli-gap.md"
    cfg = with_cli_tools(r, tmp_path, release="unreleased", release_record=record)

    async def body() -> None:
        async with r.ports(config=cfg) as p:
            tools = p.tool_port
            assert tools.unreleased_tools() == {"etabs-model/build": record}
            assert tools.supports_reconcile("etabs-model/build") is True  # reconciled by its completion record
            assert tools.supports_reconcile("dxf-prep/prepare") is False  # it writes nothing
            assert tools.supports_reconcile("csi_assign_frame_section") is True
            args = {"config": str(tmp_path / "build.json")}
            assert (await tools.reconcile("etabs-model/build", args, CLI_OP)).outcome == "not_applied"
            (r.run_dir / "tools" / CLI_OP).mkdir(parents=True)
            (r.run_dir / "tools" / CLI_OP / "complete.json").write_text('{"exit_code": 0}')
            assert (await tools.reconcile("etabs-model/build", args, CLI_OP)).outcome == "applied"
            assert await tools.read_back("etabs-model/build", args) is None
            shown = await tools.preview("etabs-model/build", args)
            assert [(i.id, i.label, i.refs) for i in shown.items] == [
                ("etabs-model/build", "etabs-model/build: command-line tool", ())
            ]
            assert (shown.models, shown.diff_ref) == ((), None)
            await opened(r, p)
            edit = {"model": "m", "frame": "F1", "section": "C40"}
            assert len((await tools.preview("csi_assign_frame_section", edit)).items[0].refs) == 2
            with pytest.raises(ContractError) as unknown:
                await tools.describe("dxf-prep/other")
            assert unknown.value.detail.code is ErrorCode.INVALID_ARGUMENT
            assert r.calls("csi_assign_frame_section") == []  # the preview sent no write

    anyio.run(body)


def test_cli_tool_without_adapter_is_config_error(tmp_path: Path) -> None:
    """A `[cli_tools.*]` entry the adapter has no argument model for is refused, never dropped."""
    r = rig(tmp_path)
    cfg = with_cli_tools(r, tmp_path)
    cfg = cfg.model_copy(update={"cli_tools": {**cfg.cli_tools, "dxf-prep/other": cfg.cli_tools["dxf-prep/inspect"]}})
    with pytest.raises(ConfigError, match="cli_tools: no command-line adapter for dxf-prep/other") as error:
        r.ports(config=cfg)
    assert error.value.key == "cli_tools"
    assert not r.run_dir.exists()
    assert r.calls("csi_launch") == []


def test_no_cli_tools_keeps_csi_port(tmp_path: Path) -> None:
    """Without `[cli_tools.*]` entries the tool port is the CSI port itself."""
    r = rig(tmp_path)
    assert type(r.ports().tool_port).__name__ == "CsiToolPort"
    assert type(r.ports(config=with_cli_tools(r, tmp_path)).tool_port).__name__ == "_RoutedTools"


def test_cli_tools_in_engine_run(tmp_path: Path) -> None:
    """A run's steps on a command-line tool go through the engine to the adapter, journaled as tool steps."""
    r = rig(tmp_path)
    cfg = with_cli_tools(r, tmp_path)
    folder = tmp_path / "inputs"
    folder.mkdir()
    (folder / "plan.dxf").write_bytes(b"dxf")
    (folder / "build.json").write_text(json.dumps({"dxf": "plan.dxf"}))
    steps = [
        ("dxf-prep/inspect", {"dxf": str(folder / "plan.dxf")}),
        ("etabs-model/build", {"config": str(folder / "build.json")}),
    ]

    async def body() -> None:
        async with r.ports(config=cfg) as p:
            result = await r.engine(p, steps).start(r.request())
            assert result.status is RunStatus.COMPLETED, result
            started = [e.payload.name for e in r.events() if isinstance(e.payload, ev.StepStarted)]
            assert [name for name in started if "/" in name] == [name for name, _ in steps]
            run = r.run_dir / "tools"
            assert sorted(f.name for d in run.iterdir() for f in d.iterdir() if f.name.endswith(".json")) == [
                "build.json", "complete.json", "inspection.json", "model.json",
            ]  # fmt: skip
            assert r.calls("csi_launch") == []

    anyio.run(body)
