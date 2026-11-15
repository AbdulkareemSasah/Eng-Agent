"""`ToolPort` over the `[cli_tools.*]` entries: tool jobs, attempt folders, hashed files (plan 0002 T16; spec 4.7).

Purpose: run `dxf-prep/prepare`, `dxf-prep/inspect` and `etabs-model/build` as `[shell, -NoProfile, -NonInteractive,
-File, script, -OutDir, <attempt>, *named arguments]` in a `TOOL` job, bounded by `timeout_s`, and answer a
`harness.cli_run/1` envelope. Units: millimetres in, metres to the tool (a length option); milliseconds out.
Errors, as failure envelopes: `INVALID_ARGUMENT` (bad input, the tool's usage and unreadable-input exits),
`CONFLICT` (the attempt folder exists: an output is never overwritten), `HOST_ERROR` (other exits, `host_code` the exit
code; `BUILD_CHANGED` when a pinned build artifact differs from its pin, before or after the call; `LAUNCH_FAILED`),
`TIMEOUT_NO_EFFECT` (the job is ended; only the discarded attempt folder changed). A tool outside the three raises
`INVALID_ARGUMENT`.

The attempt folder is `run_dir/tools/<op_id>`: the engine's `op_id` is a hash of run, step path and attempt number, so
each attempt of each step has its own fresh folder. `etabs-model/build` is reconciled by the completion record
`complete.json`, which the adapter writes after the process ended with exit 0 and its pins held (spec 4.7).
"""

import contextlib
import hashlib
import json
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import IO, Any, cast

import anyio.to_thread
from eng_contract.envelope import Envelope, FileSource, Provenance, RefInput, make_failure, make_success
from eng_contract.errors import ContractError, ContractWarning, ErrorCode, ErrorDetail, WarningCode
from eng_contract.ids import Clock
from eng_contract.params import ParamModel, ParamSpec, eng_param
from eng_contract.refs import parse_ref
from eng_contract.store import ResultStore
from eng_contract.units import convert
from mcp.client.stdio import get_default_environment
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from eng_harness.adapters._args import validate_call
from eng_harness.errors import ToolFailed
from eng_harness.ports import Reconciliation, ToolInfo
from eng_harness.servers import CliToolConfig, ServersConfig
from eng_harness.servers._launcher import JobPolicy, LaunchError, LaunchSpec, ProcessLauncher
from eng_harness.servers._procinfo import ProcessInspector

__all__ = ["CLI_KINDS", "CliToolPort"]

_Obj = Mapping[str, JsonValue]
_TAIL_BYTES = 2000  # software setting: how much of stdout and stderr is kept
_GRACE_S = 5  # software setting: how long to wait for a job that was just ended
_COMPLETE = "complete.json"
_SHELL_SWITCHES = ("-NoProfile", "-NonInteractive", "-File")
_USAGE_EXITS = {
    "dxf-prep": frozenset({1, 2}),
    "etabs-model": frozenset({2}),
}  # S-12 section 12: usage, unreadable input
_CONFIG_PATHS = ("dxf", "templateE2k")  # relative paths of the build configuration, made absolute (spec 4.7)


def _length() -> Any:
    """A `dxf-prep` length option: a design-basis quantity in millimetres, not negative."""
    return eng_param(
        None, unit="mm", ge=0, ref_capable=True, engineering_quantity=True,
        bounds_source="spec 0002 section 5: a length option of dxf-prep is not negative",
    )  # fmt: skip


class _Output(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)


class CliRun(BaseModel):
    """`harness.cli_run/1`: how a command-line tool ended and the declared outputs it left (spec 4.7)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    exit_code: int
    duration_ms: int = Field(ge=0)
    outputs: list[_Output]
    stdout_tail: str
    stderr_tail: str


CLI_KINDS: dict[str, type[BaseModel]] = {"harness.cli_run/1": CliRun}


class PrepareArgs(ParamModel):
    """`dxf-prep/prepare`: the drawing and the three optional options, which are design-basis lengths."""

    dxf: str
    SnapTol_mm: float | None = _length()
    BeamSpacing_mm: float | None = _length()
    ColumnGrow_mm: float | None = _length()


class InspectArgs(ParamModel):
    """`dxf-prep/inspect`: the drawing."""

    dxf: str


class BuildArgs(ParamModel):
    """`etabs-model/build`: the configuration file."""

    config: str


_MODELS: dict[str, type[ParamModel]] = {
    "dxf-prep/prepare": PrepareArgs, "dxf-prep/inspect": InspectArgs, "etabs-model/build": BuildArgs,
}  # fmt: skip
_WRITES = frozenset({"etabs-model/build"})  # creates a model in its own hidden ETABS (S-12 section 12)


def _source(path: Path, field: str) -> FileSource:
    """The base name, SHA-256 and size of an absolute file; `INVALID_ARGUMENT` when it cannot be read."""
    try:
        if not path.is_absolute():
            raise OSError("not an absolute path")
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        return FileSource(name=path.name, sha256=digest, size_bytes=path.stat().st_size)
    except OSError as error:
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT, f"{field}: {path.name} is not a readable file: {error}", field=field
        ) from error


def _tail(data: bytes) -> str:
    return data[-_TAIL_BYTES:].decode("utf-8", errors="replace")


def _drain(stream: IO[bytes], sink: list[bytes]) -> None:
    with contextlib.suppress(
        OSError, ValueError
    ):  # the pipe was closed under the reader: what was read is all there is
        sink.append(stream.read())


class CliToolPort:
    """The `ToolPort` of the command-line tools of `config`, run through `launcher` below `run_dir`."""

    def __init__(
        self,
        *,
        config: ServersConfig,
        store: ResultStore,
        launcher: ProcessLauncher,
        run_dir: Path,
        clock: Clock,
        inspector: ProcessInspector | None = None,
    ) -> None:
        """Wire the port; `ValueError` for a `[cli_tools.*]` entry this adapter has no argument model for.

        With an `inspector`, host-program processes that start during a step and outlive it are reported as a warning.
        """
        unknown = sorted(set(config.cli_tools) - set(_MODELS))
        if unknown:
            raise ValueError(f"no command-line adapter for {', '.join(unknown)}")
        self._config, self._store, self._launcher, self._run_dir = config, store, launcher, run_dir
        self._clock, self._inspector = clock, inspector

    def unreleased_tools(self) -> dict[str, str]:
        """`{name: release_record}` of the unreleased `[cli_tools.*]` entries (AC38)."""
        return self._config.unreleased_tools()

    def _find(self, tool: str) -> CliToolConfig:
        if tool not in self._config.cli_tools:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, f"{tool} is not a configured command-line tool", field="tool"
            )
        return self._config.cli_tools[tool]

    async def describe(self, tool: str) -> ToolInfo:
        """The tool's info; `INVALID_ARGUMENT` for a tool that is not configured."""
        self._find(tool)
        fields = _MODELS[tool].model_fields
        params = tuple(
            n
            for n, i in fields.items()
            if isinstance(i.json_schema_extra, ParamSpec) and i.json_schema_extra.engineering_quantity
        )
        return ToolInfo(
            name=tool, effect="write" if tool in _WRITES else "read", action="plain", host_key=tool.split("/")[0],
            engineering_params=params,
        )  # fmt: skip

    async def call(self, tool: str, args: _Obj, *, op_id: str, model: str | None) -> Envelope:
        """Run `tool` in the attempt folder of `op_id`; every failure but an unconfigured tool is an envelope."""
        config = self._find(tool)
        try:
            return await self._call(tool, config, args, op_id)
        except (ContractError, ToolFailed) as error:
            return make_failure(error.detail)

    def _pinned(self, config: CliToolConfig) -> None:
        for artifact in config.build_artifacts:
            path = Path(artifact.path)
            try:
                with path.open("rb") as handle:
                    found = hashlib.file_digest(handle, "sha256").hexdigest()
            except OSError:
                found = None
            if found != artifact.sha256:
                raise ToolFailed(
                    ErrorDetail(
                        code=ErrorCode.HOST_ERROR,
                        message=f"the pinned build artifact {path.name} differs from its pin",
                        retryable=False,
                        host_code="BUILD_CHANGED",
                    )
                )

    def _inputs(
        self, model: PrepareArgs | InspectArgs | BuildArgs, attempt: Path
    ) -> tuple[list[FileSource], list[str], tuple[Path, str] | None]:
        """Hash the input files, build the named arguments and the build configuration copy (path and text)."""
        if isinstance(model, BuildArgs):
            return self._build_config(Path(model.config), attempt)
        named = ["-Dxf", model.dxf]
        for name, value in model.model_dump(exclude={"dxf"}).items():
            if value is not None:
                named += [f"-{name.removesuffix('_mm')}", f"{convert(value, 'mm', 'm'):.12g}"]
        return [_source(Path(model.dxf), "dxf")], named, None

    def _build_config(self, original: Path, attempt: Path) -> tuple[list[FileSource], list[str], tuple[Path, str]]:
        files = [_source(original, "config")]
        try:
            data = json.loads(original.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, f"config: {original.name} is not a JSON file", field="config"
            ) from error
        if not isinstance(data, dict):
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, "config: the configuration is not a JSON object", field="config"
            )
        for key in _CONFIG_PATHS:
            if key in data:
                if not isinstance(data[key], str):
                    raise ContractError(ErrorCode.INVALID_ARGUMENT, f"config: {key} is not a path", field="config")
                data[key] = str(original.parent / data[key])
                files.append(_source(Path(data[key]), "config"))
        copy = attempt / original.name
        return files, ["-Config", str(copy)], (copy, json.dumps({**data, "outputFolder": str(attempt)}, indent=2))

    async def _call(self, tool: str, config: CliToolConfig, args: _Obj, op_id: str) -> Envelope:
        started, began = self._clock.now(), self._clock.now_ms()
        validated = validate_call(_MODELS[tool], args, source=self._store, current_revision=lambda _id: None)
        self._pinned(config)
        attempt = self._run_dir / "tools" / op_id
        files, named, copy = self._inputs(cast("PrepareArgs | InspectArgs | BuildArgs", validated.model), attempt)
        attempt.parent.mkdir(parents=True, exist_ok=True)
        try:
            attempt.mkdir()
        except FileExistsError as error:
            raise ContractError(
                ErrorCode.CONFLICT, f"the attempt folder of {op_id} exists: outputs are never overwritten"
            ) from error
        if copy is not None:
            copy[0].write_text(copy[1], encoding="utf-8")
        argv = [config.shell, *_SHELL_SWITCHES, config.script, "-OutDir", str(attempt), *named]
        spec = LaunchSpec(
            argv=argv,
            env=get_default_environment(),
            cwd=attempt,
            stderr_path=attempt / "stderr.txt",
            job=JobPolicy.TOOL,
        )
        known = self._host_processes()
        code, stdout = await anyio.to_thread.run_sync(self._run, spec, config.timeout_s)
        if code is None:
            raise ContractError(
                ErrorCode.TIMEOUT_NO_EFFECT, f"{tool} ran past {config.timeout_s} s and its job was ended"
            )
        warnings = self._survivors(known)
        self._pinned(config)
        stderr = (attempt / "stderr.txt").read_bytes()
        if code != 0:
            usage = code in _USAGE_EXITS.get(tool.split("/")[0], frozenset())
            message = f"{tool} exited with {code}"
            if usage:
                raise ContractError(ErrorCode.INVALID_ARGUMENT, message, hint=_tail(stderr) or None)
            raise ContractError(
                ErrorCode.HOST_ERROR, message, retryable=False, host_code=str(code), hint=_tail(stderr) or None
            )
        if tool in _WRITES:
            (attempt / _COMPLETE).write_text(json.dumps({"exit_code": code}), encoding="utf-8")
        outputs = [_Output(**_source(attempt / n, n).model_dump()) for n in config.outputs if (attempt / n).is_file()]
        duration = self._clock.now_ms() - began
        payload = CliRun(
            exit_code=code, duration_ms=duration, outputs=outputs, stdout_tail=_tail(stdout), stderr_tail=_tail(stderr)
        )
        producer = Provenance(
            tool=tool,
            tool_version=_source(Path(config.script), "script").sha256,
            files=files,
            inputs=dict(validated.inputs),
            started_at=started,
            duration_ms=duration,
        )
        parents = [*dict.fromkeys(parse_ref(i.ref)[0] for i in validated.inputs.values() if isinstance(i, RefInput))]
        record = self._store.put("harness.cli_run/1", payload.model_dump(mode="json"), producer, parents=parents)
        return make_success(record, {"exit_code": code, "outputs": [o.name for o in outputs]}, warnings)

    def _run(self, spec: LaunchSpec, timeout_s: int) -> tuple[int | None, bytes]:
        """Run the job to its end or `timeout_s`; the exit code is `None` when the job had to be ended."""
        try:
            process = self._launcher.start(spec)
        except LaunchError as error:
            raise ToolFailed(
                ErrorDetail(code=ErrorCode.HOST_ERROR, message=str(error), retryable=False, host_code="LAUNCH_FAILED")
            ) from error
        chunks: list[bytes] = []
        reader = threading.Thread(target=_drain, args=(process.stdout, chunks), daemon=True)
        reader.start()
        try:
            process.stdin.close()
            code = process.wait(timeout_s)
            if code is None:
                process.terminate_job()
                process.wait(_GRACE_S)
            reader.join(_GRACE_S)
        finally:
            process.close()
        return code, b"".join(chunks)

    def _host_processes(self) -> set[tuple[int, str]]:
        if self._inspector is None:
            return set()
        names = [exe for program in self._config.host_programs.values() for exe in program.executables]
        return {(p.pid, p.started_at) for p in self._inspector.snapshot(names)}

    def _survivors(self, known: set[tuple[int, str]]) -> list[ContractWarning]:
        """A warning for host-program processes that started during the step and still run; they are never killed."""
        new = sorted(self._host_processes() - known)
        if not new:
            return []
        pids = ", ".join(str(pid) for pid, _ in new)
        return [
            ContractWarning(
                code=WarningCode.HOST_WARNING, message=f"host-program processes outlived the tool: pid {pids}"
            )
        ]

    def supports_reconcile(self, tool: str) -> bool:
        """True for `etabs-model/build` when it is configured."""
        return tool in _WRITES and tool in self._config.cli_tools

    async def reconcile(self, tool: str, args: _Obj, op_id: str) -> Reconciliation:
        """`applied` when the attempt folder of `op_id` holds the completion record, else `not_applied` (spec 4.7)."""
        self._find(tool)
        if tool not in _WRITES:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, f"{tool} has no reconciliation: it writes nothing", field="tool"
            )
        done = (self._run_dir / "tools" / op_id / _COMPLETE).is_file()
        return Reconciliation(outcome="applied" if done else "not_applied")

    async def read_back(self, tool: str, args: _Obj) -> Envelope | None:
        """A command-line tool has no read-back."""
        self._find(tool)
        return None
