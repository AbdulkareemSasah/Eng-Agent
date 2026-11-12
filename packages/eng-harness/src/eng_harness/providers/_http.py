"""The one shared HTTP client of the provider layer (spec 0009 section 4.5; AC9 to AC11, AC14, AC15).

Redirects off, no retry, ``trust_env=False``, one request per call, and the key only in the ``Authorization`` header
set at send time. An error is classified inside the ``except`` block to a code (a small value) and raised after the
block, by a function that receives only the code, so the raised error holds no original exception, key or body.
"""

import asyncio
import json
import logging
from collections.abc import Generator, Mapping, Sequence
from typing import NoReturn

import httpx2
from pydantic import JsonValue, SecretStr

from eng_harness.decisions.interfaces import OutgoingPlace, ProviderError, ProviderErrorCode
from eng_harness.providers._config import DecisionProviderConfig, LLMProviderConfig
from eng_harness.providers._credentials import CredentialStore
from eng_harness.providers._outgoing import find_body_place

__all__ = ["ProviderClient", "build_http_client"]

_NOISY_LOGGERS = ("openai", "httpx2", "httpcore2", "pydantic_ai")  # spec 0009 section 4.5
_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}

type ProviderConfig = DecisionProviderConfig | LLMProviderConfig
type _Outcome = tuple[ProviderErrorCode | None, dict[str, JsonValue] | None]


def _raise(code: ProviderErrorCode) -> NoReturn:
    raise ProviderError(code)


def _apply_key(request: httpx2.Request, store: CredentialStore, key_ref: str | None) -> None:
    """Set the bearer header; the key lives in this frame only, which ends before the request is sent."""
    secret = store.get(key_ref) if key_ref is not None else None
    if secret is not None:
        request.headers["Authorization"] = f"Bearer {secret.get_secret_value()}"


class _BearerAuth(httpx2.Auth):
    """Reads the key at send time (spec 0009 section 4.5); the client never holds it."""

    def __init__(self, store: CredentialStore, key_ref: str | None) -> None:
        self._store = store
        self._key_ref = key_ref

    def auth_flow(self, request: httpx2.Request) -> Generator[httpx2.Request, httpx2.Response]:
        _apply_key(request, self._store, self._key_ref)
        yield request


def _quiet_loggers() -> None:
    for name in _NOISY_LOGGERS:
        logger = logging.getLogger(name)
        if logger.level < logging.WARNING:  # NOTSET (0) counts as lower
            logger.setLevel(logging.WARNING)


def build_http_client(
    config: ProviderConfig, store: CredentialStore, *, transport: httpx2.AsyncBaseTransport | None = None
) -> httpx2.AsyncClient:
    """The only place an HTTP client is built: redirects off, ``trust_env=False``, bearer hook, ceiling timeout.

    Also raises the third-party logger levels to ``WARNING`` (AC14), so no adapter can skip it.
    """
    _quiet_loggers()
    return httpx2.AsyncClient(
        base_url=config.base_url,
        auth=_BearerAuth(store, config.key_ref),
        follow_redirects=False,
        trust_env=False,
        timeout=httpx2.Timeout(config.request_timeout_ms / 1000),  # unit: s
        transport=transport,
    )


def _classify(response: httpx2.Response) -> _Outcome:
    status = response.status_code
    if status in (401, 403):
        return ProviderErrorCode.AUTH, None
    if status == 429:
        return ProviderErrorCode.RATE_LIMITED, None
    if not response.is_success:  # any other non-2xx, and every 3xx (redirects are not followed)
        return ProviderErrorCode.HTTP_STATUS, None
    try:
        data = json.loads(response.content)
    except ValueError:
        return ProviderErrorCode.BAD_RESPONSE, None
    if not isinstance(data, dict):
        return ProviderErrorCode.BAD_RESPONSE, None
    return None, data


class ProviderClient:
    """One provider's client: ``post_json`` makes exactly one request and raises only ``ProviderError``."""

    def __init__(
        self, config: ProviderConfig, store: CredentialStore, *, transport: httpx2.AsyncBaseTransport | None = None
    ) -> None:
        self._config = config
        self._store = store
        self._timeout_s = config.request_timeout_ms / 1000  # unit: s
        self.http = build_http_client(config, store, transport=transport)

    def _secret(self) -> SecretStr | None:
        key_ref = self._config.key_ref
        if key_ref is None:
            if self._config.local:
                return None
            _raise(ProviderErrorCode.NO_KEY)
        secret = self._store.get(key_ref)  # CREDENTIAL_STORE propagates
        if secret is None:
            _raise(ProviderErrorCode.NO_KEY)
        return secret

    def _prepare(
        self, body: Mapping[str, JsonValue], sensitive_values: Sequence[str]
    ) -> tuple[bytes, OutgoingPlace | None]:
        """Check the key and scan the body; the key is bound here only, so no raised error's traceback holds it.

        A body that cannot be serialized to strict JSON is not scannable and counts as ``STATE_VALUE``.
        """
        secret = self._secret()
        try:
            payload = json.dumps(body, allow_nan=False).encode("utf-8")
        except ValueError, TypeError:
            return b"", OutgoingPlace.STATE_VALUE
        return payload, find_body_place(payload, sensitive_values, secret)

    async def _exchange(self, path: str, payload: bytes) -> _Outcome:
        code: ProviderErrorCode | None = None
        data: dict[str, JsonValue] | None = None
        try:
            async with asyncio.timeout(self._timeout_s):
                response = await self.http.post(path, content=payload, headers=_HEADERS)
        except TimeoutError, httpx2.TimeoutException:
            code = ProviderErrorCode.TIMEOUT
        except httpx2.HTTPError, OSError:
            code = ProviderErrorCode.NETWORK
        else:
            code, data = _classify(response)
        return code, data

    async def post_json(
        self, path: str, body: Mapping[str, JsonValue], *, sensitive_values: Sequence[str] = ()
    ) -> dict[str, JsonValue]:
        """POST ``body`` as JSON to ``path`` under the base URL and return the JSON object answered.

        ``sensitive_values`` are the ``DecisionSettings.sensitive_values`` entries the final body is scanned for.

        Raises:
            ProviderError: ``NO_KEY``, ``CREDENTIAL_STORE``, ``REDACTION_BLOCKED`` (also for a body that is not
                strict JSON), all before any request; ``NETWORK``, ``TIMEOUT``, ``AUTH``, ``RATE_LIMITED``,
                ``HTTP_STATUS`` or ``BAD_RESPONSE``; the message is the code.
        """
        payload, place = self._prepare(body, sensitive_values)
        if place is not None:
            raise ProviderError(ProviderErrorCode.REDACTION_BLOCKED, where=place)
        code, data = await self._exchange(path, payload)
        if code is not None or data is None:
            _raise(code or ProviderErrorCode.BAD_RESPONSE)
        return data

    async def aclose(self) -> None:
        await self.http.aclose()
