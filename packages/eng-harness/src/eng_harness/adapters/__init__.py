"""Adapters from the engine's ports to host tools: descriptors and allowlists (spec 0002 section 4.5)."""

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from eng_contract.envelope import Envelope, HostInfo, LiteralInput, RefInput, SuccessEnvelope
from eng_contract.ids import Clock, IdSource, ModelId, Timestamp
from eng_contract.refs import parse_ref
from eng_contract.store import ModelStateStore, ResultStore, Workspace
from pydantic import BaseModel, ConfigDict, JsonValue

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.adapters._allowlist import Allowlist, AllowlistError, load_allowlist
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._hostport import AdapterHostPort
from eng_harness.adapters._identity import IdentityStore
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters.cli import CLI_KINDS, CliToolPort
from eng_harness.adapters.csi import csi_allowlist
from eng_harness.adapters.csi._checks import ReadBack, WrittenItems
from eng_harness.adapters.csi._errors import CsiErrorMapper
from eng_harness.adapters.csi._reconcile import CsiReconciler
from eng_harness.adapters.csi._revisions import Revisions
from eng_harness.adapters.csi._tools import CsiToolPort
from eng_harness.adapters.revit._session_ops import RevitHostPort
from eng_harness.adapters.revit._toolport import _WRITE_RESULT, RevitToolPort
from eng_harness.basis import BasisInvalid, StoreBasisPort
from eng_harness.ctx import Preview, PreviewItem
from eng_harness.errors import JournalIntegrityError
from eng_harness.journal import JournalReader
from eng_harness.ports import HostInstance, HostPort, Reconciliation, ServerCheck, ToolInfo, ToolPort
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


class _RoutedTools:
    """The tool port of a run with `[cli_tools.*]` entries: each tool goes to the adapter that serves it (AC43)."""

    def __init__(self, csi: CsiToolPort, cli: CliToolPort, cli_tools: frozenset[str]) -> None:
        self._csi, self._cli, self._cli_tools = csi, cli, cli_tools

    def _serving(self, tool: str) -> CsiToolPort | CliToolPort:
        return self._cli if tool in self._cli_tools else self._csi

    async def describe(self, tool: str) -> ToolInfo:
        return await self._serving(tool).describe(tool)

    def unreleased_tools(self) -> dict[str, str]:
        return self._csi.unreleased_tools() | self._cli.unreleased_tools()

    async def call(self, tool: str, args: Mapping[str, JsonValue], *, op_id: str, model: str | None) -> Envelope:
        return await self._serving(tool).call(tool, args, op_id=op_id, model=model)

    def supports_reconcile(self, tool: str) -> bool:
        return self._serving(tool).supports_reconcile(tool)

    async def reconcile(self, tool: str, args: Mapping[str, JsonValue], op_id: str) -> Reconciliation:
        return await self._serving(tool).reconcile(tool, args, op_id)

    async def read_back(self, tool: str, args: Mapping[str, JsonValue]) -> Envelope | None:
        return await self._serving(tool).read_back(tool, args)

    async def preview(self, tool: str, args: Mapping[str, JsonValue]) -> Preview:
        """A CSI tool's preview as the CSI port gives it. A command-line tool changes no model of the run (the build
        tool writes only into its attempt folder and its own hidden host, spec 4.7) and its adapter stores no
        canonical arguments: its preview is one item that names the tool, with no reference, model or diff."""
        if tool not in self._cli_tools:
            return await self._csi.preview(tool, args)
        await self._cli.describe(tool)
        return Preview(
            items=(PreviewItem(id=tool, label=f"{tool}: command-line tool", refs=()),), diff_ref=None, models=()
        )


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


class _RevitBinding(BaseModel):
    """Identity of a working document independently of the MCP role processes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document: Path
    model_id: ModelId
    instance: HostInstance


class _RevitBindings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pipe_name: str
    models: dict[str, _RevitBinding]


class _RevitRunHostPort(RevitHostPort):
    """Retain the run's Revit bindings across engine processes (spec 0011 AC22)."""

    @property
    def _binding_path(self) -> Path:
        return self._run_dir / "adapter" / "revit-bindings.json"

    def load_bindings(self) -> None:
        path = self._binding_path
        if not path.is_file():
            return
        bindings = _RevitBindings.model_validate_json(path.read_bytes())
        if bindings.pipe_name != self._pipe_name:
            return
        for key, binding in bindings.models.items():
            if self._files.get(key, binding.document) != binding.document:
                continue
            instance = binding.instance
            self._files[key], self._models[key] = binding.document, binding.model_id
            self._bound[key] = instance.instance_id
            self._instances[instance.instance_id] = instance

    async def working_copy(self, model_key: str, folder: Path) -> str:
        key = await super().working_copy(model_key, folder)
        bindings = _RevitBindings(
            pipe_name=self._pipe_name,
            models={
                name: _RevitBinding(
                    document=self._files[name], model_id=self._models[name], instance=self._instances[i]
                )
                for name, i in self._bound.items()
            },
        )
        path = self._binding_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(bindings.model_dump_json())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        return key


class _RevitRunToolPort(RevitToolPort):
    """Advance the model revision after a live or reconciled edit (spec 0011 AC22, AC29)."""

    def _record_edit(self, before: HostInfo) -> HostInfo:
        states = self._host.identity_store._states
        current = states.get(before.model_id)
        if current is None:
            return before
        if current.revision == before.model_revision:
            current = states.increment(before.model_id, before.model_revision)
        return before.model_copy(update={"model_revision": current.revision})

    def _store_result(
        self,
        tool: str,
        kind: str,
        payload: dict[str, JsonValue],
        host: HostInfo | None,
        inputs: Mapping[str, RefInput | LiteralInput],
        timing: tuple[Timestamp, int],
        reply: Mapping[str, JsonValue] | None = None,
        summary: dict[str, JsonValue] | None = None,
    ) -> SuccessEnvelope:
        if kind == _WRITE_RESULT and host is not None:
            host = self._record_edit(host)
        return super()._store_result(tool, kind, payload, host, inputs, timing, reply, summary)

    async def reconcile(self, tool: str, args: Mapping[str, JsonValue], op_id: str) -> Reconciliation:
        outcome = await super().reconcile(tool, args, op_id)
        if outcome.outcome == "applied":
            entry = self._revit_ledger.find(op_id)
            if entry is not None and entry.pre_image_ref is not None:
                result_id, _ = parse_ref(entry.pre_image_ref)
                before = self._store.get(result_id).producer.host
                if before is not None:
                    # A crash after advancing the revision can replay the same durable pre-image.
                    self._record_edit(before)
        return outcome


def _cli_port(
    config: ServersConfig,
    workspace: Workspace,
    run_dir: Path,
    clock: Clock,
    ids: IdSource,
    launcher: ProcessLauncher,
    inspector: ProcessInspector,
) -> CliToolPort | None:
    """The port of the `[cli_tools.*]` entries, `None` without any; `ConfigError` for an entry it cannot serve.

    Its `harness.cli_run/1` results go through a store over the run's workspace whose registry holds that kind, which
    `HARNESS_KINDS` does not register (spec 0002 A1 lists it, `_kinds.py` is outside plan task T19b; see the CHANGELOG).
    """
    if not config.cli_tools:
        return None
    store = ResultStore(workspace, HARNESS_KINDS.extend(CLI_KINDS), ids, clock)
    try:
        return CliToolPort(
            config=config, store=store, launcher=launcher, run_dir=run_dir, clock=clock, inspector=inspector
        )
    except ValueError as error:
        raise ConfigError("cli_tools", str(error)) from error


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
    """Wire CSI ports for the server product and command-line tools (spec 0002 4.1, AC41, AC43 to AC45; spec 0008 4.1).

    Enter the result around Engine.start/resume. No process starts here. Each `[cli_tools.*]` entry is served by the
    command-line tool adapter beside the CSI tools (AC43); unsupported server adapters/configurations and a
    command-line tool the adapter has no argument model for raise ConfigError rather than silently losing a capability.
    """
    from dataclasses import replace as _replace

    from eng_harness.adapters.idea import idea_allowlist
    from eng_harness.adapters.idea._toolport import IdeaRunHostPort, IdeaToolPort
    from eng_harness.adapters.revit import revit_allowlist
    from eng_harness.kinds.idea import IDEA_KINDS

    idea_adapter = "sasaah-idea-mcp"
    loaders: dict[str, Callable[[str | None], Allowlist]] = {
        "sasaah-csi-mcp": csi_allowlist,
        idea_adapter: idea_allowlist,
        **(allowlists or {}),
        "sasaah-revit-mcp": lambda _route: revit_allowlist(),
    }
    loaded: dict[str, Allowlist] = {}
    for name, section in config.servers.items():
        if section.adapter not in loaders:
            raise ConfigError(f"servers.{name}.adapter", "this adapter is not implemented")
        allowlist = loaders[section.adapter](section.route)
        loaded[name] = allowlist if section.adapter == "sasaah-revit-mcp" else allowlist.for_product(section.product)
    if len(config.servers) != 1:
        raise ConfigError("servers", "CSI port wiring requires one server section")
    name, section = next(iter(config.servers.items()))
    if section.adapter not in ("sasaah-csi-mcp", "sasaah-revit-mcp", idea_adapter):
        raise ConfigError(f"servers.{name}.adapter", "this adapter is not implemented")
    is_revit = section.adapter == "sasaah-revit-mcp"
    product = section.product  # the server's product profile (spec 0002 4.6, spec 0008 4.1)
    program = None if is_revit or section.adapter == idea_adapter else config.host_program(product)
    inspector = inspector if inspector is not None else platform_inspector()
    launcher = launcher if launcher is not None else platform_launcher(inspector)
    cli = _cli_port(config, workspace, run_dir, clock, ids, launcher, inspector)
    if is_revit and cli is not None:
        raise ConfigError("cli_tools", "Revit port wiring does not serve command-line tools")
    engine = inspector.identity(os.getpid())
    if engine is None:
        raise ConfigError("servers", "the engine process identity cannot be read")
    locks = HostLocks(
        lock_dir if lock_dir is not None else default_lock_dir(os.environ, home=Path.home(), windows=os.name == "nt"),
        run_id=run_dir.name,
        engine=engine,
        clock=clock,
    )
    guard = ProcessGuard(inspector, run_dir, host_exes=() if program is None else program.executables)
    if is_revit:
        _destructive = frozenset(
            {
                "revit_set_type_parameter_values",
                "revit_set_element_parameter_values",
                "revit_set_parameter_value_by_guid",
                "revit_change_element_type",
            }
        )
        _revit_check = {}
        for _role in ("read", "write"):
            _base = revit_allowlist(role=_role).build_expectation()
            _revit_check[f"{name}/{_role}"] = _replace(
                _base,
                status_tool="revit_connection_status",
                destructive_tools=_destructive if _role == "write" else frozenset(),
            )
        servers = ServerManager(config, run_dir, launcher=launcher, helpers=guard, check=_revit_check)
    else:
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
    states = ModelStateStore(workspace, clock)
    if section.adapter == idea_adapter:
        if cli is not None:
            raise ConfigError("cli_tools", "IDEA port wiring does not serve command-line tools")
        if section.route is None:
            raise ConfigError(f"servers.{name}.route", "IDEA port wiring requires a route")
        idea_store = ResultStore(workspace, HARNESS_KINDS.extend(IDEA_KINDS), ids, clock)
        idea_host = IdeaRunHostPort(
            identity=IdentityStore(workspace=workspace, states=states, ids=ids),
            sessions=servers,
            locks=locks,
            clock=clock,
            ids=ids,
            run_dir=run_dir,
            files=files or {},
            store=idea_store,
            server=name,
            host_key=section.host_key,
            route=section.route,
            service_url=section.service_url,
        )
        tool_port = IdeaToolPort(
            config=config,
            allowlist=loaded[name],
            server=name,
            caller=servers,
            host=idea_host,
            states=states,
            store=idea_store,
            run_dir=run_dir,
            clock=clock,
            ids=ids,
            check=check,
        )
        return AdapterPorts(tool_port, idea_host, servers)
    if is_revit:
        # Revit dispatch, after the IDEA dispatch (amendment B-611); B-617 references and Q10/Q11 evidence.
        if section.pipe_name is None:
            raise ConfigError(f"servers.{name}.pipe_name", "pipe_name is required for Revit")
        from eng_harness.adapters.revit._checks import WrittenItems as _RevitWritten

        revit_written, revit_tolerance = _RevitWritten(), _FrozenTolerance(run_dir, store)
        revit_host = _RevitRunHostPort(
            identity=IdentityStore(workspace=workspace, states=states, ids=ids),
            sessions=servers,
            locks=locks,
            clock=clock,
            ids=ids,
            run_dir=run_dir,
            files=files or {},
            pipe_name=section.pipe_name,
            server=name,
            host_key=section.host_key,
            store=store,
            check=check,
            written=revit_written,
            tolerance=revit_tolerance,
        )
        revit_host.load_bindings()
        revit_tool = _RevitRunToolPort(
            config=config,
            allowlist=loaded[name],
            server=name,
            caller=servers,
            host=revit_host,
            store=store,
            run_dir=run_dir,
            clock=clock,
            ids=ids,
            check=check,
            written=revit_written,
            tolerance=revit_tolerance,
        )
        return AdapterPorts(revit_tool, revit_host, servers)
    if program is None:
        raise ConfigError("host_programs", "CSI port wiring requires a host program")
    written, tolerance = WrittenItems(), _FrozenTolerance(run_dir, store)
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
        saved=host.tool_saved,
        opener=host.open_original,
        record_pre_image=True,
        open_model_bound=host.open_model_bound,
    )
    return AdapterPorts(tool if cli is None else _RoutedTools(tool, cli, frozenset(config.cli_tools)), host, servers)


__all__ = ["AdapterPorts", "Allowlist", "AllowlistError", "ToolDescriptor", "build_ports", "load_allowlist"]
