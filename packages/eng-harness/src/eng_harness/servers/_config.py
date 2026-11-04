"""Server, command-line tool and host-program sections of `harness.toml` (spec 0002 section 4.2).

Spec 0006 owns where the file is found and its `[engine]` section; this module reads only `[servers.*]`,
`[cli_tools.*]` and `[host_programs.*]`. All timeouts are whole seconds and have no default (process 11 section 9).
"""

import tomllib
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

_FORBIDDEN_ARGS = ("--enable-script", "--enable-generic-invoke", "--allow-attached-writes", "--read-only")
_ADAPTER_ONLY_ARGS = ("--call-timeout-sec", "--audit-log")
_ADAPTER_ONLY_ENV = "SASAAH_CSI_CALL_TIMEOUT_SEC"
_CSI_ADAPTER = "sasaah-csi-mcp"
# Substrings that mark an escape-hatch tool name (script, generic invoke, table write); the full deny list is the
# allowlist's (spec 0002 section 4.5.1).
_ESCAPE_MARKERS = ("script", "invoke", "tables_apply")


class ConfigError(Exception):
    """A configuration key is missing, invalid or forbidden; raised before any run.

    Attributes:
        key: Dotted path of the offending key, or the file name when the file itself is unusable.
    """

    def __init__(self, key: str, message: str) -> None:
        super().__init__(f"{key}: {message}")
        self.key = key


def _absolute(value: str) -> str:
    if not (PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()):
        raise ValueError("path must be absolute")
    return value


Seconds = Annotated[int, Field(strict=True, ge=1)]  # unit: s


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BuildPin(_Model):
    """Pinned server build (spec section 4.3.4)."""

    sasaah_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    exe_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    server_info_version: str | None = None


class RoleConfig(_Model):
    """One server process: the timeout classes it serves and its server-wide call timeout (s)."""

    classes: tuple[str, ...] = Field(min_length=1)
    call_timeout_s: Seconds


class ServerConfig(_Model):
    """One `[servers.<name>]` section."""

    adapter: str
    command: str
    args: tuple[str, ...] = ()
    env: Mapping[str, str] = Field(default_factory=dict)
    toolsets: tuple[str, ...] = ()
    client_grace_s: Seconds
    max_restarts_per_run: int = Field(default=1, ge=0)  # software setting
    shutdown_grace_s: Seconds = 10  # software setting, s
    build: BuildPin
    host_key: str
    mcp_mode: str = "legacy"  # spec section 11 Q3
    audit_log: bool = True
    route: str | None = None
    roles: Mapping[str, RoleConfig] = Field(min_length=1)

    @field_validator("command")
    @classmethod
    def _command_absolute(cls, value: str) -> str:
        return _absolute(value)

    @field_validator("args")
    @classmethod
    def _args_allowed(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for arg in value:
            name = arg.split("=", 1)[0]
            if name in _FORBIDDEN_ARGS or name in _ADAPTER_ONLY_ARGS:
                raise ValueError(f"argument {name} is forbidden (set by the adapter only or enables an escape hatch)")
        return value

    @field_validator("env")
    @classmethod
    def _env_allowed(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        names = {key.upper(): item for key, item in value.items()}  # Windows env names are case-insensitive
        if "SASAAH_CSI_ENABLE_SCRIPT" in names:
            raise ValueError("SASAAH_CSI_ENABLE_SCRIPT is forbidden")
        if names.get("SASAAH_CSI_DISABLE_SCRIPT", "true").lower() != "true":
            raise ValueError("SASAAH_CSI_DISABLE_SCRIPT must be true")
        if _ADAPTER_ONLY_ENV in names:
            raise ValueError(f"{_ADAPTER_ONLY_ENV} is set by the adapter only")
        return value

    @field_validator("toolsets")
    @classmethod
    def _toolsets_allowed(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for name in value:
            if any(marker in name.lower() for marker in _ESCAPE_MARKERS):
                raise ValueError(f"toolset {name} includes an escape hatch")
        return value

    @model_validator(mode="after")
    def _csi_disables_scripts(self) -> Self:
        if self.adapter == _CSI_ADAPTER and "--disable-script" not in self.args:
            raise ValueError("args must contain --disable-script")
        return self


class BuildArtifact(_Model):
    """A cached command-line executable pinned by SHA-256."""

    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def _path_absolute(cls, value: str) -> str:
        return _absolute(value)


class CliToolConfig(_Model):
    """One `[cli_tools.<name>]` section; `timeout_s` is required."""

    shell: str
    script: str
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    timeout_s: Seconds
    build_artifacts: tuple[BuildArtifact, ...] = ()

    @field_validator("shell", "script")
    @classmethod
    def _path_absolute(cls, value: str) -> str:
        return _absolute(value)


class HostProgramConfig(_Model):
    """One `[host_programs.<name>]` section: executables that identify host instances."""

    executables: tuple[str, ...] = Field(min_length=1)
    install_dirs: tuple[str, ...] = ()

    @field_validator("install_dirs")
    @classmethod
    def _dirs_absolute(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            _absolute(item)
        return value


class ServersConfig(_Model):
    """The server, tool and host-program sections of `harness.toml`."""

    servers: Mapping[str, ServerConfig] = Field(default_factory=dict)
    cli_tools: Mapping[str, CliToolConfig] = Field(default_factory=dict)
    host_programs: Mapping[str, HostProgramConfig] = Field(default_factory=dict)


def load_servers_config(path: Path) -> ServersConfig:
    """Load and validate the server sections of a `harness.toml`.

    Args:
        path: The file; other top-level sections (such as `[engine]`) are ignored.

    Returns:
        The immutable configuration.

    Raises:
        ConfigError: The file cannot be read or parsed, or a key is missing, invalid or forbidden; `key` names it.
    """
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(path.name, f"cannot read harness.toml: {error}") from error
    try:
        return ServersConfig.model_validate({k: data[k] for k in ServersConfig.model_fields if k in data})
    except ValidationError as error:
        first = error.errors()[0]
        key = ".".join(str(part) for part in first["loc"])
        raise ConfigError(key, first["msg"].removeprefix("Value error, ")) from error
