"""`[providers.*]` of `harness.toml` (spec 0009 section 4.2; AC1 to AC4).

Software settings only; there is no key for a secret. Timeouts are in milliseconds. Every refusal is a
`ContractError` `INVALID_ARGUMENT` naming the key; a value is never part of a message.
"""

import ipaddress
import re
from collections.abc import Mapping
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from eng_contract.errors import ContractError, ErrorCode
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from eng_harness.decisions.types import DecisionPolicy

_SECRET_KEYS = frozenset({"key", "api_key", "token", "secret", "password", "authorization"})
_NAME = r"^[a-z][a-z0-9_-]{0,31}$"
_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TABLES = ("decision", "llm")
PositiveInt = Annotated[int, Field(strict=True, ge=1)]  # unit set on each field


def _loopback(host: str | None) -> bool:
    if host is None:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class _Provider(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=_NAME)
    base_url: str
    model: str = Field(min_length=1, max_length=100)
    model_version: str = Field(min_length=1, max_length=40)
    key_ref: str | None = Field(default=None, pattern=_NAME)
    local: bool = Field(default=False, strict=True)
    request_timeout_ms: PositiveInt  # unit: ms

    @model_validator(mode="after")
    def _endpoint(self) -> _Provider:
        parts = urlsplit(self.base_url)
        loopback = _loopback(parts.hostname)
        if (
            parts.scheme not in ("https", "http")
            or not parts.hostname
            or "@" in parts.netloc
            or "?" in self.base_url
            or "#" in self.base_url
            or (parts.scheme == "http" and not loopback)
            or (self.local and not loopback)
        ):
            raise ValueError("base_url: must be https, or http on a loopback host, without user, query or fragment")
        if self.key_ref is None and not self.local:
            raise ValueError("key_ref: is required unless local is true")
        return self


class DecisionProviderConfig(_Provider):
    """`[providers.decision]`: the Jev decision-model tier."""

    backend: Literal["openrouter", "typesafe"] = "openrouter"


class LLMProviderConfig(_Provider):
    """`[providers.llm]`: the language-model tier."""

    max_output_tokens: PositiveInt  # unit: tokens


class ConfigWarning(BaseModel):
    """A non-fatal finding of the configuration; `table` is `providers.decision` or `providers.llm`."""

    model_config = ConfigDict(frozen=True)

    code: Literal["request_timeout_below_policy"]
    table: str


class ProvidersConfig(BaseModel):
    """Both tables are optional; with neither the harness has no providers (spec 0005 AC17)."""

    model_config = ConfigDict(frozen=True)

    decision: DecisionProviderConfig | None = None
    llm: LLMProviderConfig | None = None
    warnings: tuple[ConfigWarning, ...] = ()


def _refuse(path: str, message: str, hint: str | None = None) -> ContractError:
    field = path if _PATH.fullmatch(path.rsplit(".", 1)[-1]) else None
    return ContractError(ErrorCode.INVALID_ARGUMENT, message, field=field, hint=hint)


def _check_table(path: str, table: object, defaults: Mapping[str, str]) -> dict[str, Any]:
    if not isinstance(table, Mapping):
        raise _refuse(path, f"{path} must be a table")
    for key in table:
        if str(key).lower() in _SECRET_KEYS:
            raise _refuse(
                f"{path}.{key}",
                f"{path}.{key}: a secret is never configured here; keep it in the credential store",
                hint="name the credential-store entry with key_ref",
            )
    return {**defaults, **table}


def load_providers_config(providers: Mapping[str, Any] | None) -> ProvidersConfig:
    """Validate the `[providers]` table of `harness.toml`.

    Args:
        providers: The parsed table, or None when the section is absent.

    Raises:
        ContractError: `INVALID_ARGUMENT` for an unknown, missing, secret-named or out-of-bounds key.
    """
    providers = providers or {}
    for key in providers:
        if key not in _TABLES:
            raise _refuse(f"providers.{key}", f"providers.{key}: unknown table")
    built: dict[str, Any] = {}
    warnings: list[ConfigWarning] = []
    # 12 section 3 ceilings, the DecisionPolicy defaults (spec 0009 AC4; decision_policy_defaults.json).
    policy = DecisionPolicy()
    for table, model, ceiling in (
        ("decision", DecisionProviderConfig, policy.timeout_ms_model),
        ("llm", LLMProviderConfig, policy.timeout_ms_llm),
    ):
        if table not in providers:
            continue
        path = f"providers.{table}"
        raw = _check_table(path, providers[table], {})
        if "name" not in raw:
            raw["name"] = (
                str(raw["backend"])
                if table == "decision" and raw.get("backend") in ("openrouter", "typesafe")
                else ("openrouter" if table == "decision" else "llm")
            )
        try:
            built[table] = model.model_validate(raw)
        except ValidationError as exc:
            first = exc.errors(include_input=False, include_url=False)[0]
            loc = ".".join(str(part) for part in first["loc"])
            if not loc:  # a model-level rule names its key at the start of the message
                loc = first["msg"].removeprefix("Value error, ").split(":", 1)[0]
            key = f"{path}.{loc}" if loc else path
            raise _refuse(key, f"{key}: {first['msg']}") from None
        if built[table].request_timeout_ms < ceiling:
            warnings.append(ConfigWarning(code="request_timeout_below_policy", table=path))
    return ProvidersConfig(warnings=tuple(warnings), **built)
