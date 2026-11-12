"""Credential store (spec 0009 section 3.2, AC6 and AC7): store only, backend allow-list."""

import os

import keyring
import pytest
from fakes.credential_stores import FakeChainerBackend, MemoryKeyringBackend, backend_path
from keyring.core import load_keyring
from pydantic import SecretStr

import eng_harness.providers._credentials as credentials_mod
from eng_harness.decisions.interfaces import ProviderError, ProviderErrorCode
from eng_harness.providers._credentials import (
    DEFAULT_ALLOWED_BACKENDS,
    SERVICE_NAME,
    KeyringCredentialStore,
)

_ENV_KEYS = ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "TYPESAFE_API_KEY", "ANTHROPIC_API_KEY")
_STORE_VALUE = "-".join(("sk", "stored", "only"))
_STORE_SECRET = SecretStr(_STORE_VALUE)
_FAKE_CHAINER_PATH = f"{FakeChainerBackend.__module__}.{FakeChainerBackend.__name__}"


def _allowed_with(*paths: str) -> frozenset[str]:
    return frozenset({*DEFAULT_ALLOWED_BACKENDS, *paths})


def _with_fake_chainer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        credentials_mod,
        "_CHAINED_BACKENDS",
        credentials_mod._CHAINED_BACKENDS | {_FAKE_CHAINER_PATH},
    )


def test_store_only_no_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    memory = MemoryKeyringBackend()
    keyring.set_keyring(memory)
    store = KeyringCredentialStore(allowed_backends=_allowed_with(backend_path(memory)))
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
    _with_fake_chainer(monkeypatch)

    for name in ("keyring.backends.fail.Keyring", "keyring.backends.null.Keyring"):
        keyring.set_keyring(load_keyring(name))
        for operation in (
            lambda: store.get("jev"),
            lambda: store.set("jev", _STORE_SECRET),
            lambda: store.delete("jev"),
        ):
            with pytest.raises(ProviderError) as info:
                operation()
            assert info.value.code is ProviderErrorCode.CREDENTIAL_STORE

    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyring.backends.fail.Keyring")
    keyring.set_keyring(load_keyring("keyring.backends.fail.Keyring"))
    with pytest.raises(ProviderError) as info:
        store.get("jev")
    assert info.value.code is ProviderErrorCode.CREDENTIAL_STORE

    disallowed = load_keyring("keyring.backends.fail.Keyring")
    keyring.set_keyring(FakeChainerBackend([disallowed]))
    with pytest.raises(ProviderError) as info:
        store.get("jev")
    assert info.value.code is ProviderErrorCode.CREDENTIAL_STORE

    primary = MemoryKeyringBackend()
    secondary = MemoryKeyringBackend()
    keyring.set_keyring(FakeChainerBackend([primary, secondary]))
    direct = KeyringCredentialStore(allowed_backends=_allowed_with(backend_path(primary), backend_path(secondary)))
    direct.set("jev", _STORE_SECRET)
    assert primary.get_password(SERVICE_NAME, "jev") == _STORE_VALUE
    assert secondary.get_password(SERVICE_NAME, "jev") is None
