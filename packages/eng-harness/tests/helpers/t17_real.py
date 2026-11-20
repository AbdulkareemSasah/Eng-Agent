"""Real-engine + page wiring for plan 0006 T17 end-to-end re-checks (AC29, AC33, AC34, AC35, AC37).

Test helper only: a `Host` from the engine rig, a `PageApprovalPort` with the production screen builders, and an
`Engine` whose progress sink is the page hub (or a gated wrapper for AC37). Never shipped.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eng_contract.envelope import HostInfo, Provenance, SuccessEnvelope
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.kinds.basis import DesignBasis
from eng_contract.store import LocationClass, ResultStore, Workspace
from fakes.ports import FakeBasisPort, FakeCalcPort
from workflows.rig import BASIS_REF, START_MS, Host

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.block import Registry
from eng_harness.engine import Engine, EnginePorts, EngineSettings, PermissionMode, RunOutcome, RunRequest
from eng_harness.journal import Event, JournalReader
from eng_harness.pages import PageApprovalPort, PageInputPort, PageServer, PageSettings
from eng_harness.pages._answers import bound_sha256
from eng_harness.pages._screens_approval import approval_screens
from eng_harness.pages._security import CSRF_FIELD
from eng_harness.ports import ApprovalPort, ApprovalRequest, LoadedBasis, ProgressSink, RunClass
from helpers.page_client import PageClient

_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="t17-real")


def kill_wait_worker(root: str, ready: Any, die: Any) -> None:
    """Spawn target for AC35: show an approval, signal ready, then `os._exit` when told (no `approval_resolved`).

    Lives in `helpers` so multiprocessing `spawn` can re-import it (a test module under `replay` is not a package).
    """
    from workflows.ctx_flows import flow

    from eng_harness.block import Registry
    from eng_harness.ctx import ModelHandle, Preview, PreviewItem

    def preview(host: Host) -> Any:
        state = host.models["m1"]
        assert state.model_id is not None
        handle = ModelHandle(model_key="m1", model_id=state.model_id, revision=state.revision or 0)
        return Preview(items=(PreviewItem(id="i1", label="Change i1", refs=()),), diff_ref=None, models=(handle,))

    box: list[RealPage] = []

    async def body(ctx: Any) -> list[str]:
        await ctx.approve("Apply the change", preview(box[0].host))
        return []

    workflow = flow(body, name="kill_flow")
    with real_page(Path(root), Registry([workflow])) as page:
        box.append(page)
        page.start("kill_flow")
        request = page.wait_shown()
        Path(root, "request_id.txt").write_text(request.request_id, encoding="utf-8")
        Path(root, "shown_sha256.txt").write_text(request.shown_sha256, encoding="utf-8")
        run_ids = sorted(p.name for p in page.runs.iterdir() if p.is_dir())
        Path(root, "run_id.txt").write_text(run_ids[-1], encoding="utf-8")
        ready.set()
        assert die.wait(30)
        os._exit(77)


def until(condition: Callable[[], bool], seconds: float = 10.0) -> None:
    """Wait for `condition`; fail when it does not hold within `seconds`."""
    end = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < end, "the condition did not hold in time"
        time.sleep(0.01)


class GatedHub:
    """A `ProgressSink` that holds each event until `release` is set, then forwards it to `inner` (AC37)."""

    def __init__(self, inner: ProgressSink) -> None:
        self._inner = inner
        self.release = threading.Event()
        self.release.set()
        self.seen: list[Event] = []

    def emit(self, event: Event) -> None:
        self.seen.append(event)
        self.release.wait()
        self._inner.emit(event)


@dataclass
class RealPage:
    """A real engine, its host, the page ports and a client with an open session."""

    root: Path
    host: Host
    store: ResultStore
    approvals: PageApprovalPort
    engine: Engine
    client: PageClient
    gated: GatedHub | None = None
    shown: list[ApprovalRequest] = field(default_factory=list)
    _server: PageServer | None = field(default=None, repr=False)

    @property
    def runs(self) -> Path:
        return self.root / "ws" / "runs"

    def events(self, run_id: str) -> list[Event]:
        reader = JournalReader(self.runs / run_id)
        try:
            return list(reader.events())
        finally:
            reader.close()

    def form(self, request: ApprovalRequest, **fields: str) -> dict[str, str]:
        token = self.client.token(f"/request/{request.request_id}")
        return {
            CSRF_FIELD: token,
            "shown_sha256": bound_sha256(request),
            "by": "Ada",
            "decision": "approve",
        } | fields

    def answer(self, request: ApprovalRequest, **fields: str) -> int:
        return self.client.post(f"/answer/{request.request_id}", self.form(request, **fields)).status

    def start(self, workflow: str, *, payload: dict[str, Any] | None = None) -> Future[RunOutcome]:
        request = RunRequest(
            workflow=workflow,
            input=payload or {},
            basis_ref=BASIS_REF,
            mode=PermissionMode.WORK_ON_COPY,
            run_class=RunClass.TRIAL,
        )
        return _POOL.submit(asyncio.run, self.engine.start(request))

    def resume(self, run_id: str) -> Future[RunOutcome]:
        return _POOL.submit(asyncio.run, self.engine.resume(run_id))

    def wait_shown(self, seconds: float = 10.0) -> ApprovalRequest:
        until(lambda: bool(self.shown), seconds)
        return self.shown[-1]

    def written(self, model_key: str, revision: int) -> SuccessEnvelope:
        """A write result with host model_revision so the next write under the approval can chain (EC5)."""
        state = self.host.models[model_key]
        assert state.model_id is not None
        host = HostInfo(program="csi", version="1", model_id=state.model_id, model_revision=revision)
        producer = Provenance(
            tool="harness", tool_version="fake", host=host, inputs={}, started_at=self.host._clock.now(), duration_ms=0
        )
        stored = self.store.put("harness.run_output/1", {"value": {"revision": revision}}, producer)
        return SuccessEnvelope(
            contract="eng-contract/1",
            ok=True,
            result_id=stored.result_id,
            kind="harness.run_output/1",
            summary={"revision": revision},
            complete=True,
            provenance=producer,
        )


class _RecordingApprovals:
    """Forwards to the page port, records each request, and waits as the CLI does (engine wait is always false)."""

    def __init__(self, inner: ApprovalPort, shown: list[ApprovalRequest]) -> None:
        self._inner, self._shown = inner, shown

    async def present(self, request: ApprovalRequest) -> None:
        self._shown.append(request)
        await self._inner.present(request)

    async def answer(self, request_id: str, *, wait: bool) -> Any:
        # Spec 0006 4.4.5 step 2: the process wait mode is the command's; the engine's wait is ignored.
        return await self._inner.answer(request_id, wait=True)


@contextmanager
def real_page(
    root: Path,
    registry: Registry,
    *,
    gate_sink: bool = False,
    ack_timeout_s: float = 10,
    bases: dict[str, Any] | None = None,
) -> Iterator[RealPage]:
    """Open a page server and a real engine over a fake host; the page hub is the progress sink."""
    clock = FixedClock(START_MS, 1)
    ids = SeededIdSource(b"t17", clock)
    workspace = Workspace(root=root / "ws", classification=LocationClass.LOCAL)
    runs = workspace.root / "runs"
    runs.mkdir(parents=True, exist_ok=True)  # resume reuses the killed process's workspace (AC35)
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    host = Host(ids, clock, runs)
    shown: list[ApprovalRequest] = []

    def journal() -> JournalReader:
        run_ids = sorted(p.name for p in runs.iterdir() if p.is_dir())
        assert run_ids, "no run folder yet"
        return JournalReader(runs / run_ids[-1])

    page = PageApprovalPort(
        engineer="Ada",
        builders=approval_screens(store, journal),
        ack_timeout_s=ack_timeout_s,
    )
    sink: ProgressSink = page.hub
    gated: GatedHub | None = None
    if gate_sink:
        gated = GatedHub(page.hub)
        sink = gated
    loaded = {BASIS_REF: LoadedBasis(result_id=BASIS_REF, basis=DesignBasis(template=None, fields={}))}
    loaded.update(bases or {})
    ports = EnginePorts(
        tool=host,
        host=host,
        calc=FakeCalcPort(RunClass.TRIAL, ()),
        basis=FakeBasisPort(loaded),
        approvals=_RecordingApprovals(page, shown),
        inputs=PageInputPort(page),
        progress=sink,
    )
    engine = Engine(workspace, registry, ports, store, EngineSettings(), clock, ids)
    settings = PageSettings(max_failed_requests=1000)
    with PageServer(page.hub, settings) as server:
        client = PageClient(server)
        client.open()
        yield RealPage(root, host, store, page, engine, client, gated, shown, server)
