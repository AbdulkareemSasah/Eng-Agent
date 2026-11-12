"""Operating-system credential store (spec 0009 section 4.4; ADR-0002)."""

from __future__ import annotations

import re
from typing import Protocol, cast, runtime_checkable

import keyring
from keyring.errors import PasswordDeleteError
from pydantic import SecretStr

from eng_harness.decisions.interfaces import ProviderError, ProviderErrorCode
from eng_harness.providers._config import ProvidersConfig

# spec 0009 section 4.4; names confirmed against keyring 25.7.0 (ADR-0002).
DEFAULT_ALLOWED_BACKENDS = frozenset(
    {
        "keyring.backends.Windows.WinVaultKeyring",
        "keyring.backends.macOS.Keyring",
        "keyring.backends.SecretService.Keyring",
        "keyring.backends.kwallet.DBusKeyring",
    }
)
SERVICE_NAME = "eng-harness"  # spec 0009 section 4.4
_KEY_REF = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_CHAINED_BACKENDS = frozenset({"keyring.backends.chainer.ChainerBackend"})


class ChainedKeyringBackend(Protocol):
    @property
    def backends(self) -> list[keyring.backend.KeyringBackend]: ...


@runtime_checkable
class CredentialStore(Protocol):
    """Read and write provider keys under ``key_ref``; keys never come from the environment."""

    def get(self, key_ref: str) -> SecretStr | None: ...

    def set(self, key_ref: str, secret: SecretStr) -> None: ...

    def delete(self, key_ref: str) -> bool: ...


def _backend_path(backend: keyring.backend.KeyringBackend) -> str:
    cls = type(backend)
    return f"{cls.__module__}.{cls.__name__}"


def _resolve_backend(allowed: frozenset[str]) -> keyring.backend.KeyringBackend:
    backend = keyring.get_keyring()
    if _backend_path(backend) in _CHAINED_BACKENDS:
        for candidate in cast(ChainedKeyringBackend, backend).backends:
            if _backend_path(candidate) in allowed:
                return candidate
        raise ProviderError(ProviderErrorCode.CREDENTIAL_STORE)
    if _backend_path(backend) not in allowed:
        raise ProviderError(ProviderErrorCode.CREDENTIAL_STORE)
    return backend


def _validate_key_ref(key_ref: str) -> None:
    if not _KEY_REF.fullmatch(key_ref):
        raise ValueError(f"key_ref: {key_ref!r} must match {_KEY_REF.pattern}")


class KeyringCredentialStore:
    """``keyring`` store with a backend allow-list; calls one concrete backend, not the chainer."""

    def __init__(self, *, allowed_backends: frozenset[str] | None = None) -> None:
        self._allowed = allowed_backends or DEFAULT_ALLOWED_BACKENDS

    def get(self, key_ref: str) -> SecretStr | None:
        _validate_key_ref(key_ref)
        try:
            backend = _resolve_backend(self._allowed)
            password = backend.get_password(SERVICE_NAME, key_ref)
        except ProviderError:
            raise
        except Exception:
            raise ProviderError(ProviderErrorCode.CREDENTIAL_STORE) from None
        if password is None:
            return None
        return SecretStr(password)

    def set(self, key_ref: str, secret: SecretStr) -> None:
        _validate_key_ref(key_ref)
        value = secret.get_secret_value()
        if not value:
            raise ValueError("key must not be empty")
        try:
            backend = _resolve_backend(self._allowed)
            backend.set_password(SERVICE_NAME, key_ref, value)
        except ProviderError:
            raise
        except Exception:
            raise ProviderError(ProviderErrorCode.CREDENTIAL_STORE) from None

    def delete(self, key_ref: str) -> bool:
        _validate_key_ref(key_ref)
        try:
            backend = _resolve_backend(self._allowed)
            backend.delete_password(SERVICE_NAME, key_ref)
        except ProviderError:
            raise
        except PasswordDeleteError:
            return False
        except Exception:
            raise ProviderError(ProviderErrorCode.CREDENTIAL_STORE) from None
        return True


def key_status(store: CredentialStore, key_ref: str) -> str:
    """Return ``key present``, ``key absent`` or ``credential store unavailable`` (spec AC8)."""
    try:
        return "key present" if store.get(key_ref) is not None else "key absent"
    except ProviderError as error:
        if error.code is ProviderErrorCode.CREDENTIAL_STORE:
            return "credential store unavailable"
        raise


def status_lines(config: ProvidersConfig, store: CredentialStore) -> list[str]:
    """One status line per configured provider ``key_ref``."""
    rows: list[str] = []
    for provider in (config.decision, config.llm):
        if provider is None or provider.key_ref is None:
            continue
        rows.append(f"{provider.key_ref}: {key_status(store, provider.key_ref)}")
    return rows
