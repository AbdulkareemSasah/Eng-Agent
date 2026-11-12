"""Credential-store doubles (spec 0009 section 4.11; lead decision D-5)."""

import keyring.backend
from keyring.compat import properties
from keyring.errors import PasswordDeleteError
from pydantic import SecretStr

SERVICE_NAME = "eng-harness"  # spec 0009 section 4.4


def backend_path(backend: keyring.backend.KeyringBackend) -> str:
    cls = type(backend)
    return f"{cls.__module__}.{cls.__name__}"


class MemoryKeyringBackend(keyring.backend.KeyringBackend):
    """In-memory keyring backend for tests (outside the production allow-list)."""

    def __init__(self) -> None:
        self._passwords: dict[tuple[str, str], str] = {}

    @properties.classproperty
    def priority(cls) -> float:  # noqa: N805
        return 1

    def get_password(self, service: str, username: str) -> str | None:
        return self._passwords.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._passwords[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self._passwords:
            raise PasswordDeleteError(service, username)
        del self._passwords[(service, username)]


class FakeChainerBackend(keyring.backend.KeyringBackend):
    """Chainer double for allow-list tests (avoids constructing the untyped keyring ``ChainerBackend``)."""

    def __init__(self, backends: list[keyring.backend.KeyringBackend]) -> None:
        self._backends = backends

    @properties.classproperty
    def priority(cls) -> float:  # noqa: N805
        return 1

    @property
    def backends(self) -> list[keyring.backend.KeyringBackend]:
        return self._backends

    def get_password(self, service: str, username: str) -> str | None:
        return None

    def set_password(self, service: str, username: str, password: str) -> None:
        return None

    def delete_password(self, service: str, username: str) -> None:
        return None


class DisallowedKeyringBackend(keyring.backend.KeyringBackend):
    """A backend that must stay outside the production allow-list."""

    @properties.classproperty
    def priority(cls) -> float:  # noqa: N805
        return 5

    def get_password(self, service: str, username: str) -> str | None:
        return "disallowed"

    def set_password(self, service: str, username: str, password: str) -> None:
        return None

    def delete_password(self, service: str, username: str) -> None:
        return None


class FakeCredentialStore:
    """Protocol double for the provider key commands."""

    def __init__(self) -> None:
        self._secrets: dict[str, SecretStr] = {}

    def get(self, key_ref: str) -> SecretStr | None:
        return self._secrets.get(key_ref)

    def set(self, key_ref: str, secret: SecretStr) -> None:
        self._secrets[key_ref] = secret

    def delete(self, key_ref: str) -> bool:
        if key_ref not in self._secrets:
            return False
        del self._secrets[key_ref]
        return True
