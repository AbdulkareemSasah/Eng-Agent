"""Credential store (spec 0009 section 3.2, AC6 and AC7): store only, backend allow-list."""

import os
from unittest.mock import PropertyMock

import keyring
import pytest
from keyring.backends import fail, null
from keyring.backends.chainer import ChainerBackend
from pydantic import SecretStr

from eng_harness.decisions.interfaces import ProviderError, ProviderErrorCode
from eng_harness.providers._credentials import (
    DEFAULT_ALLOWED_BACKENDS,
    SERVICE_NAME,
    KeyringCredentialStore,
)
from tests.fakes.credential_stores import DisallowedKeyringBackend, MemoryKeyringBackend

_ENV_KEYS = ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "TYPESAFE_API_KEY", "ANTHROPIC_API_KEY")
_STORE_VALUE = "-".join(("sk", "stored", "only"))
_STORE_SECRET = SecretStr(_STORE_VALUE)


def _allowed_with(*paths: str) -> frozenset[str]:
    return frozenset({*DEFAULT_ALLOWED_BACKENDS, *paths})


def test_store_only_no_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    memory = MemoryKeyringBackend()
    keyring.set_keyring(memory)
    store = KeyringCredentialStore(allowed_backends=_allowed_with(memory.path))
    memory.set_password(SERVICE_NAME, "jev", _STORE_VALUE)
    for name in _ENV_KEYS:
        monkeypatch.setenv(name, _STORE_VALUE)

    def getenv_raises(name: str, default: str | None = None) -> str | None:
        if name in _ENV_KEYS:
            raise AssertionError(f"read environment variable {name}")
        return os.environ.get(name, default)

    monkeypatch.setattr(os, "getenv", getenv_raises)
    got = store.get("jev")
    assert got is not None
    assert got.get_secret_value() == _STORE_VALUE


def test_backend_allow_list(monkeypatch: pytest.MonkeyPatch) -> None:
    store = KeyringCredentialStore()

    for backend in (fail.Keyring(), null.Keyring()):
        keyring.set_keyring(backend)
        for operation in (
            lambda: store.get("jev"),
            lambda: store.set("jev", _STORE_SECRET),
            lambda: store.delete("jev"),
        ):
            with pytest.raises(ProviderError) as info:
                operation()
            assert info.value.code is ProviderErrorCode.CREDENTIAL_STORE

    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyring.backends.fail.Keyring")
    keyring.set_keyring(keyring.load_keyring("keyring.backends.fail.Keyring"))
    with pytest.raises(ProviderError) as info:
        store.get("jev")
    assert info.value.code is ProviderErrorCode.CREDENTIAL_STORE

    memory = MemoryKeyringBackend()
    disallowed = DisallowedKeyringBackend()
    monkeypatch.setattr(ChainerBackend, "backends", PropertyMock(return_value=[disallowed, memory]))
    keyring.set_keyring(ChainerBackend())
    allowed_store = KeyringCredentialStore(allowed_backends=_allowed_with(memory.path))
    with pytest.raises(ProviderError) as info:
        allowed_store.get("jev")
    assert info.value.code is ProviderErrorCode.CREDENTIAL_STORE

    primary = MemoryKeyringBackend()
    secondary = MemoryKeyringBackend()
    monkeypatch.setattr(ChainerBackend, "backends", PropertyMock(return_value=[primary, secondary]))
    keyring.set_keyring(ChainerBackend())
    direct = KeyringCredentialStore(allowed_backends=_allowed_with(primary.path, secondary.path))
    direct.set("jev", _STORE_SECRET)
    assert primary.get_password(SERVICE_NAME, "jev") == _STORE_VALUE
    assert secondary.get_password(SERVICE_NAME, "jev") is None
