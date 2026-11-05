"""`harness.toml` discovery and the sections owned by spec 0006 (section 4.2.4, AC4)."""

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from eng_harness.servers import ConfigError

PosInt = Annotated[int, Field(strict=True, ge=1)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EngineSection(_Model):
    """`[engine]`: permission mode, proposed engineer name and the `EngineSettings` limits (engine spec 4.10)."""

    default_mode: Literal["work_on_copy", "approve_each_write", "autonomous_logged"] = "work_on_copy"
    engineer: str | None = Field(default=None, min_length=1, max_length=100)
    max_parallel_children: PosInt = 8
    max_concurrent_hosts: PosInt = 1
    max_concurrent_decisions: PosInt = 4
    max_attempts_cap: PosInt = 10
    step_retry_limit: PosInt = 2


class ProgressSection(_Model):
    """`[progress]`: heartbeat and expected-time settings."""

    heartbeat_s: PosInt = 10  # unit: s
    stale_after_heartbeats: Annotated[int, Field(strict=True, ge=2)] = 3
    history_runs: PosInt = 20
    min_samples: PosInt = 3
    queue_lines: PosInt = 1000


class PageSection(_Model):
    """`[page]`: approval page settings."""

    open_browser: bool = True
    max_body_bytes: PosInt = 32768  # unit: byte
    max_failed_requests: PosInt = 20
    ack_timeout_s: PosInt = 10  # unit: s
    display_max_chars: PosInt = 500


class ProjectLaneTool(_Model):
    """`[project_lane.<tool>]`: a tool not yet released (ADR-0026 section 3)."""

    record: str = Field(min_length=1)


class HarnessConfig(_Model):
    """The sections of `harness.toml`; the sections of other specs are kept as they are."""

    engine: EngineSection = EngineSection()
    progress: ProgressSection = ProgressSection()
    page: PageSection = PageSection()
    project_lane: Mapping[str, ProjectLaneTool] = Field(default_factory=dict)
    # servers, cli_tools, host_programs and providers belong to specs 0002 and 0009, which validate them.
    servers: Mapping[str, Any] = Field(default_factory=dict)
    cli_tools: Mapping[str, Any] = Field(default_factory=dict)
    host_programs: Mapping[str, Any] = Field(default_factory=dict)
    providers: Mapping[str, Any] = Field(default_factory=dict)


def resolve_config_path(explicit: Path | None, environ: Mapping[str, str], workspace: Path | None) -> Path | None:
    """Find `harness.toml`: `--config`, then `ENG_HARNESS_CONFIG`, then `<workspace>/harness.toml`.

    Raises:
        ConfigError: a file named by `--config` or the variable does not exist.
    """
    named = explicit or (Path(environ["ENG_HARNESS_CONFIG"]) if environ.get("ENG_HARNESS_CONFIG") else None)
    if named is not None:
        if not named.is_file():
            raise ConfigError(named.name, "configuration file not found")
        return named
    default = workspace / "harness.toml" if workspace else None
    return default if default is not None and default.is_file() else None


def load_config(path: Path | None) -> HarnessConfig:
    """Load and validate `path` (defaults when None).

    Raises:
        ConfigError: unreadable file, unknown key, wrong type or out-of-bounds value; `key` is the dotted key.
    """
    if path is None:
        return HarnessConfig()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(path.name, f"cannot read harness.toml: {error}") from error
    unknown = sorted(set(data) - set(HarnessConfig.model_fields))
    if unknown:
        raise ConfigError(unknown[0], "unknown section")
    try:
        return HarnessConfig.model_validate(data)
    except ValidationError as error:
        first = error.errors()[0]
        raise ConfigError(".".join(str(part) for part in first["loc"]), first["msg"]) from error
