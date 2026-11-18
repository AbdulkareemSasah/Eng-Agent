"""Adapters from the engine's ports to host tools: descriptors and allowlists (spec 0002 section 4.5)."""

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from eng_contract.ids import Clock, IdSource
from eng_contract.store import ModelStateStore, ResultStore, Workspace

from eng_harness.adapters._allowlist import Allowlist, AllowlistError, load_allowlist
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._hostport import AdapterHostPort
from eng_harness.adapters._identity import IdentityStore
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters.csi import csi_allowlist
from eng_harness.adapters.csi._checks import ReadBack, WrittenItems
from eng_harness.adapters.csi._errors import CsiErrorMapper
from eng_harness.adapters.csi._reconcile import CsiReconciler
from eng_harness.adapters.csi._revisions import Revisions
from eng_harness.adapters.csi._tools import CsiToolPort
from eng_harness.basis import BasisInvalid, StoreBasisPort
from eng_harness.errors import JournalIntegrityError, NotImplementedGap
from eng_harness.journal import JournalReader
from eng_harness.ports import HostPort, ServerCheck, ToolPort
from eng_harness.servers import ConfigError, ServerManager, ServersConfig, platform_inspector, platform_launcher
from eng_harness.servers._guard import ProcessGuard
from eng_harness.servers._hostlock import HostLocks, default_lock_dir
from eng_harness.servers._launcher import ProcessLauncher
from eng_harness.servers._procinfo import ProcessInspector


@dataclass(frozen=True)
class AdapterPorts:
    """The ports of a run; `async with` enters and leaves its `ServerManager` (spec 0002 AC48)."""

    tool_port: ToolPort
    host_port: HostPort
    servers: ServerManager

    async def __aenter__(self) -> Self:
        await self.servers.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.servers.__aexit__(*exc)


class _RunRevisions(Revisions):
    """Create the copies folder only at its first snapshot; construction precedes Engine.start's run-id check."""

    def target(self, working: Path) -> Path:
        target = super().target(working)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target


class _FrozenTolerance:
    """Read the run's frozen basis, including at resume; missing evidence supplies no engineering value (AC44)."""

    def __init__(self, run_dir: Path, store: ResultStore) -> None:
        self._run_dir, self._basis = run_dir, StoreBasisPort(store)
        self._value: float | None = None

    def __call__(self) -> float | None:
        if self._value is not None:
            return self._value
        try:
            reader = JournalReader(self._run_dir)
            try:
                basis_ref = reader.header().basis_ref
            finally:
                reader.close()
            basis = self._basis.load(basis_ref).basis
        except JournalIntegrityError, BasisInvalid:
            return None
        field = basis.fields.get("checks.readback_relative_tolerance_ratio")
        if field is not None and isinstance(field.value, int | float) and not isinstance(field.value, bool):
            self._value = float(field.value)
        return self._value


def build_ports(
    config: ServersConfig,
    workspace: Workspace,
    store: ResultStore,
    run_dir: Path,
    clock: Clock,
    ids: IdSource,
    *,
    inspector: ProcessInspector | None = None,
    launcher: ProcessLauncher | None = None,
    lock_dir: Path | None = None,
    files: Mapping[str, Path] | None = None,
    checks: Mapping[str, ServerCheck] | None = None,
    allowlists: Mapping[str, Callable[[str | None], Allowlist]] | None = None,
    visible: bool = False,
) -> AdapterPorts:
    """Wire the CSI ETABS ports of one run (spec 0002 4.1, AC41, AC43 to AC45).

    Enter the result around Engine.start/resume. No process starts here. CLI tools are the explicit H-G8 gap;
    unsupported server adapters/configurations raise ConfigError rather than silently losing a capability.
    """
    if config.cli_tools:
        raise NotImplementedGap("H-G8: CLI tools are not wired: " + ", ".join(sorted(config.cli_tools)))
    loaders = {"sasaah-csi-mcp": csi_allowlist, **(allowlists or {})}
    loaded: dict[str, Allowlist] = {}
    for name, section in config.servers.items():
        if section.adapter not in loaders:
            raise ConfigError(f"servers.{name}.adapter", "this adapter is not implemented")
        loaded[name] = loaders[section.adapter](section.route)
    if len(config.servers) != 1:
        raise ConfigError("servers", "CSI port wiring requires one server section")
    name, section = next(iter(config.servers.items()))
    if section.adapter != "sasaah-csi-mcp":
        raise ConfigError(f"servers.{name}.adapter", "this adapter is not implemented")
    product = "ETABS"  # spec 0002 4.6: the phase-1 CSI product profile
    program = config.host_program(product)
    inspector = inspector if inspector is not None else platform_inspector()
    launcher = launcher if launcher is not None else platform_launcher(inspector)
    engine = inspector.identity(os.getpid())
    if engine is None:
        raise ConfigError("servers", "the engine process identity cannot be read")
    locks = HostLocks(
        lock_dir if lock_dir is not None else default_lock_dir(os.environ, home=Path.home(), windows=os.name == "nt"),
        run_id=run_dir.name,
        engine=engine,
        clock=clock,
    )
    guard = ProcessGuard(inspector, run_dir, host_exes=program.executables)
    servers = ServerManager(
        config,
        run_dir,
        launcher=launcher,
        helpers=guard,
        check={key: allowlist.build_expectation() for key, allowlist in loaded.items()},
    )
    pin = section.build
    check = (checks or {}).get(name) or ServerCheck(
        server=name,
        build=f"{pin.sasaah_commit[:12]}+{pin.exe_sha256[:12]}",
        min_build="",
        fingerprint="",
        expected_fingerprint="",
        ok=False,
        reason="unchecked",
    )
    written, tolerance = WrittenItems(), _FrozenTolerance(run_dir, store)
    states = ModelStateStore(workspace, clock)
    host = AdapterHostPort(
        identity=IdentityStore(workspace=workspace, states=states, ids=ids),
        states=states,
        sessions=servers,
        guard=guard,
        inspector=inspector,
        locks=locks,
        clock=clock,
        ids=ids,
        run_dir=run_dir,
        product=product,
        program=product.lower(),
        exe_name=program.executables[0],
        server=name,
        host_key=section.host_key,
        files=files or {},
        readback=ReadBack(written, store, check),
        tolerance=tolerance,
        visible=visible,
    )
    tool = CsiToolPort(
        config=config,
        server=name,
        caller=servers,
        binder=host,
        store=store,
        ledger=WriteLedger(run_dir),
        clock=clock,
        ids=ids,
        check=check,
        errors=CsiErrorMapper(ids),
        reconciler=CsiReconciler(product=product, tolerance_ratio=None, tolerance=tolerance),
        written=written,
        wrote=host.wrote,
        revisions=_RunRevisions(run_dir / "copies", run_dir / "adapter/revisions.json"),
        reopened=host.reopened,
        opener=host.open_original,
        record_pre_image=True,
        open_model_bound=host.open_model_bound,
    )
    return AdapterPorts(tool, host, servers)


__all__ = ["AdapterPorts", "Allowlist", "AllowlistError", "ToolDescriptor", "build_ports", "load_allowlist"]
