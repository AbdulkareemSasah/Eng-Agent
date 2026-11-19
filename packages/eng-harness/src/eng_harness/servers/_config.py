"""Server, command-line tool and host-program sections of `harness.toml` (spec 0002 section 4.2).

Spec 0006 owns where the file is found and its `[engine]` section; this module reads only `[servers.*]`,
`[cli_tools.*]` and `[host_programs.*]`. All timeouts are whole seconds and have no default (process 11 section 9).
"""

import ipaddress
import tomllib
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator, model_validator

_FORBIDDEN_ARGS = ("--enable-script", "--enable-generic-invoke", "--allow-attached-writes", "--read-only")
_ADAPTER_ONLY_ARGS = ("--call-timeout-sec", "--audit-log")
_ADAPTER_ONLY_ENV = "SASAAH_CSI_CALL_TIMEOUT_SEC"
_CSI_ADAPTER = "sasaah-csi-mcp"
_IDEA_ADAPTER = "sasaah-idea-mcp"  # spec 0014 section 4.2
_IDEA_ROUTES = ("native", "rest")
_IDEA_ARG = "--disable-script"  # the one argument the section may carry; the adapter adds the rest from the keys
# The three aliases of each server option (E/IdeaModels.cs:441-452): the adapter sets options by argument only.
_IDEA_ENV_PREFIXES = ("SASAAH_IDEA_", "SASAH_IDEA_", "IDEA_")
_REVIT_ADAPTER = "sasaah-revit-mcp"  # spec 0011 section 4.2
_REVIT_FORBIDDEN_ARGS = (
    "--enable-send-code",
    "--enable-adaptive-bake",
    "--cache-send-code-bodies",
    "--toolsets",
    "--pipe-name",
    "--bridge-timeout-ms",
    "--disable-send-code",
    "--disable-adaptive-bake",
    "--no-cache-send-code-bodies",
)
# The CSI products a server section can name (spec 0008 4.1); the adapter's profile registry holds the same names.
KNOWN_PRODUCTS = ("ETABS", "SAFE")
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


def _loopback_url(value: str) -> str:
    """Return `value` when it is a plain http(s) URL without credentials whose host is loopback (spec 0014 AC1)."""
    try:
        parts = urlsplit(value)
        host = parts.hostname
        _ = parts.port  # reading it validates the port: a ValueError is the refusal
    except ValueError as error:
        raise ValueError(f"service_url is not a valid URL: {error}") from error
    if (
        parts.scheme not in ("http", "https")
        or host is None
        or parts.username is not None
        or parts.password is not None
    ):
        raise ValueError("service_url must be an http or https URL with a host and no credentials")
    if host != "localhost":
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            raise ValueError("service_url must point at a loopback host (127.0.0.1, ::1 or localhost)")
    return value


Seconds = Annotated[int, Field(strict=True, ge=1)]  # unit: s


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReleaseMarked(_Model):
    """Release mark of an allowlist or `[cli_tools.*]` entry (spec 0002 section 4.5.1, AC38).

    `unreleased` is a project-lane tool not yet through the release lane (ADR-0026); it needs `release_record`, the
    repository-relative path of its gap report or session record, which a `released` entry must not carry.
    """

    release: Literal["released", "unreleased"] = "released"
    release_record: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _release_consistent(self) -> Self:
        if (self.release == "unreleased") != (self.release_record is not None):
            raise ValueError("release_record is required exactly when release is unreleased")
        path = PureWindowsPath(self.release_record or "")  # also splits on "/"
        if path.anchor or ".." in path.parts:
            raise ValueError("release_record must be a repository-relative path")
        return self


class BuildPin(_Model):
    """Pinned server build (spec section 4.3.4)."""

    sasaah_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    exe_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    server_info_version: str | None = None
    addin_sha256: tuple[Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")], ...] = ()
    addin_paths: tuple[str, ...] = Field(default=(), validate_default=True)

    @field_validator("addin_paths")
    @classmethod
    def _addin_paths_check(cls, value: tuple[str, ...], info: ValidationInfo) -> tuple[str, ...]:
        for path in value:
            _absolute(path)
        sha = info.data.get("addin_sha256", ())
        if len(sha) != len(value):
            raise ValueError("addin_paths and addin_sha256 must have equal lengths")
        return value


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
    pipe_name: str | None = Field(default=None, validate_default=True)
    # The host product (spec 0008 4.1): required for CSI; defaults to IDEA or Revit for their adapters.
    product: str = Field(default="", validate_default=True)
    mcp_mode: str = "legacy"  # spec section 11 Q3
    # spec 0002 section 4.2 rule 5; a non-boolean is a ConfigError; validated when absent too (the IDEA rule below)
    audit_log: bool = Field(default=True, strict=True, validate_default=True)
    route: str | None = None  # spec 0002 section 4.2 rule 5; the allowlist load checks it (AC41), IDEA's values here
    roles: Mapping[str, RoleConfig] = Field(min_length=1)
    service_url: str | None = None  # spec 0014 section 4.2: IDEA only, loopback, passed as --service-url
    idea_dir: str | None = None  # spec 0014 section 4.2: IDEA only, absolute, passed as --idea-dir

    @model_validator(mode="before")
    @classmethod
    def _revit_product(cls, data: object) -> object:
        if isinstance(data, dict) and data.get("adapter") == _REVIT_ADAPTER and "product" not in data:
            return {**data, "product": "Revit"}
        return data

    @field_validator("command")
    @classmethod
    def _command_absolute(cls, value: str) -> str:
        return _absolute(value)

    @field_validator("pipe_name")
    @classmethod
    def _pipe_name_revit(cls, value: str | None, info: ValidationInfo) -> str | None:
        if info.data.get("adapter") == _REVIT_ADAPTER and (not value or not value.strip()):
            raise ValueError("pipe_name is required for Revit")
        return value

    @field_validator("product")
    @classmethod
    def _product_known(cls, value: str, info: ValidationInfo) -> str:
        adapter = info.data.get("adapter")
        if adapter == _IDEA_ADAPTER:
            if value and value != "IDEA":
                raise ValueError(f"unknown product {value!r} for {_IDEA_ADAPTER}; omit product or use 'IDEA'")
            return "IDEA"
        if adapter == _REVIT_ADAPTER:
            if value != "Revit":
                raise ValueError(f"product must be 'Revit', not {value!r}")
            return "Revit"
        if not value:
            raise ValueError("product is required")
        if value not in KNOWN_PRODUCTS:
            raise ValueError(f"unknown product {value!r}; one of {', '.join(KNOWN_PRODUCTS)}")
        return value

    @field_validator("build")
    @classmethod
    def _build_revit(cls, value: BuildPin, info: ValidationInfo) -> BuildPin:
        if info.data.get("adapter") == _REVIT_ADAPTER and (not value.addin_paths or not value.addin_sha256):
            raise ValueError("build.addin_paths and build.addin_sha256 are required for Revit")
        return value

    @field_validator("args")
    @classmethod
    def _args_allowed(cls, value: tuple[str, ...], info: ValidationInfo) -> tuple[str, ...]:
        adapter = info.data.get("adapter")
        for arg in value:
            name = arg.split("=", 1)[0]
            if name in _FORBIDDEN_ARGS or name in _ADAPTER_ONLY_ARGS:
                raise ValueError(f"argument {name} is forbidden (set by the adapter only or enables an escape hatch)")
            # The IDEA server ignores unknown arguments with only a warning, so a typo would pass silently (4.2 rule 4).
            if adapter == _IDEA_ADAPTER and arg != _IDEA_ARG:
                raise ValueError(
                    f"argument {arg} is not permitted for {_IDEA_ADAPTER}: only {_IDEA_ARG}; "
                    "the folder and the service URL come from the idea_dir and service_url keys"
                )
            if adapter == _REVIT_ADAPTER and name in _REVIT_FORBIDDEN_ARGS:
                raise ValueError(f"argument {name} is forbidden (adapter-only or enables an escape hatch)")
        return value

    @field_validator("env")
    @classmethod
    def _env_allowed(cls, value: Mapping[str, str], info: ValidationInfo) -> Mapping[str, str]:
        names = {key.upper(): item for key, item in value.items()}  # Windows env names are case-insensitive
        if len(names) != len(value):
            raise ValueError("env names that differ only in case collide on Windows (SASAAH_CSI_DISABLE_SCRIPT check)")
        if "SASAAH_CSI_ENABLE_SCRIPT" in names:
            raise ValueError("SASAAH_CSI_ENABLE_SCRIPT is forbidden")
        if names.get("SASAAH_CSI_DISABLE_SCRIPT", "true").lower() != "true":
            raise ValueError("SASAAH_CSI_DISABLE_SCRIPT must be true")
        if _ADAPTER_ONLY_ENV in names:
            raise ValueError(f"{_ADAPTER_ONLY_ENV} is set by the adapter only")
        adapter = info.data.get("adapter")
        if adapter == _IDEA_ADAPTER:
            for name in names:
                if name.startswith(_IDEA_ENV_PREFIXES):
                    raise ValueError(f"{name} is forbidden for {_IDEA_ADAPTER} (an alias of a server option)")
        if adapter == _REVIT_ADAPTER:
            for name in names:
                if name.startswith("SASAAH_MCP_"):
                    raise ValueError(f"{name} is forbidden for {_REVIT_ADAPTER} (adapter-only)")
        return value

    @field_validator("toolsets")
    @classmethod
    def _toolsets_allowed(cls, value: tuple[str, ...], info: ValidationInfo) -> tuple[str, ...]:
        for name in value:
            if any(marker in name.lower() for marker in _ESCAPE_MARKERS):
                raise ValueError(f"toolset {name} includes an escape hatch")
        if info.data.get("adapter") == _REVIT_ADAPTER and value:
            raise ValueError("toolsets is forbidden for Revit (the allowlist is the filter)")
        return value

    @field_validator("audit_log")
    @classmethod
    def _idea_has_no_audit_log(cls, value: bool, info: ValidationInfo) -> bool:
        if value and info.data.get("adapter") == _IDEA_ADAPTER:
            raise ValueError(f"audit_log must be false for {_IDEA_ADAPTER}: the server has no --audit-log option")
        return value

    @field_validator("route")
    @classmethod
    def _idea_route(cls, value: str | None, info: ValidationInfo) -> str | None:
        if info.data.get("adapter") == _IDEA_ADAPTER and value not in _IDEA_ROUTES:
            raise ValueError(f"route must be one of {', '.join(_IDEA_ROUTES)} for {_IDEA_ADAPTER}")
        return value

    @field_validator("roles")
    @classmethod
    def _roles_check(cls, value: Mapping[str, RoleConfig], info: ValidationInfo) -> Mapping[str, RoleConfig]:
        adapter = info.data.get("adapter")
        if adapter == _IDEA_ADAPTER and tuple(value) != ("main",):
            raise ValueError(f"{_IDEA_ADAPTER} needs the single topology: exactly one role, named main")
        if adapter == _REVIT_ADAPTER:
            if set(value) != {"read", "write"}:
                raise ValueError("Revit requires read and write roles")
            if set(value["read"].classes) != {"session", "call"} or value["write"].classes != ("attended",):
                raise ValueError("invalid Revit role classes")
            classes = [item for role in value.values() for item in role.classes]
            if len(classes) != len(set(classes)):
                raise ValueError("a timeout class cannot be served twice")
        return value

    @field_validator("service_url")
    @classmethod
    def _service_url_loopback(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        if info.data.get("adapter") != _IDEA_ADAPTER:
            raise ValueError(f"service_url is only for {_IDEA_ADAPTER}")
        return _loopback_url(value)

    @field_validator("idea_dir")
    @classmethod
    def _idea_dir_absolute(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        if info.data.get("adapter") != _IDEA_ADAPTER:
            raise ValueError(f"idea_dir is only for {_IDEA_ADAPTER}")
        return _absolute(value)

    @model_validator(mode="after")
    def _idea_section(self) -> Self:
        if self.adapter != _IDEA_ADAPTER:
            return self
        if self.route is None:
            raise ValueError(f"route is required for {_IDEA_ADAPTER}: one of {', '.join(_IDEA_ROUTES)}")
        if self.route == "rest" and self.service_url is None:
            raise ValueError("service_url is required for route rest")
        if _IDEA_ARG not in self.args:
            raise ValueError(f"args must contain {_IDEA_ARG}")
        return self

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


class CliToolConfig(ReleaseMarked):
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

    @model_validator(mode="after")
    def _servers_consistent(self) -> Self:
        """One host key per server, one build pin per executable (spec 0008 AC1); `ConfigError` names the later key."""
        host_keys: dict[str, str] = {}
        pins: dict[PureWindowsPath, tuple[str, BuildPin]] = {}  # Windows paths compare without case and separator
        for name, server in self.servers.items():
            other = host_keys.setdefault(server.host_key, name)
            if other != name:
                raise ConfigError(
                    f"servers.{name}.host_key", f"host key {server.host_key!r} is also used by servers.{other}"
                )
            first, pin = pins.setdefault(PureWindowsPath(server.command), (name, server.build))
            if pin != server.build:
                raise ConfigError(
                    f"servers.{name}.build", f"the build pin differs from servers.{first}, the same executable"
                )
        return self

    def unreleased_tools(self) -> dict[str, str]:
        """`{name: release_record}` of the unreleased `[cli_tools.*]` entries (AC38); empty when there are none."""
        return {
            n: t.release_record for n, t in self.cli_tools.items() if t.release_record and t.release == "unreleased"
        }

    def host_program(self, product: str) -> HostProgramConfig:
        """The `[host_programs.<product in lower case>]` entry; `ConfigError` (`key` names it) when there is none."""
        name = product.lower()
        if name not in self.host_programs:
            raise ConfigError(f"host_programs.{name}", "no host program entry for this product")
        return self.host_programs[name]


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
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(path.name, f"cannot read harness.toml: {error}") from error
    return servers_config(data)


def servers_config(data: Mapping[str, Any]) -> ServersConfig:
    """`load_servers_config` over tables already parsed; a `ConfigError` names the dotted key."""
    try:
        return ServersConfig.model_validate({k: data[k] for k in ServersConfig.model_fields if k in data})
    except ValidationError as error:
        first = error.errors()[0]
        key = ".".join(str(part) for part in first["loc"])
        raise ConfigError(key, first["msg"].removeprefix("Value error, ")) from error
