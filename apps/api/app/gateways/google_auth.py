import asyncio
import json
import logging
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

import jwt
from google.auth import exceptions as google_exceptions
from google.auth.transport import requests
from google.oauth2 import id_token

from app.core.blocking import run_blocking
from app.core.config import Settings
from app.core.validation import claim_is_true
from app.exceptions import AuthenticationError
from app.gateways.signing_keys import KeyCache, KeySet, max_age_seconds

logger = logging.getLogger(__name__)

# Where google-auth reads the certs ``verify_oauth2_token`` checks a token against.
GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v1/certs"
# This process's copy of them (gateways/signing_keys.py): google-auth keeps none.
cert_cache = KeyCache()

# Reuse one Request (and its underlying Session) so Google cert fetches get
# HTTP keep-alive instead of a cold TLS handshake on every sign-in.
_google_request: requests.Request | None = None

# Extra wait past the HTTP timeout before giving up on the worker thread
# (DNS resolution is not covered by the requests timeout).
_THREAD_GRACE_SECONDS = 2.0


def _shared_google_request() -> requests.Request:
    global _google_request
    if _google_request is None:
        _google_request = requests.Request()
    return _google_request


class GoogleAuthError(AuthenticationError):
    """A Google ID token the server does not accept."""


class GoogleAuthUnavailableError(Exception):
    """Google's signing certs could not be fetched in time; the token is not judged.

    Not a ``GoogleAuthError``: callers answer 503 (retry) rather than 401,
    which the app treats as "signed out".
    """

    code = "google_unavailable"


class _BoundedRequest:
    """Google transport callable that never waits longer than ``timeout``.

    ``id_token.verify_oauth2_token`` calls the transport without a timeout,
    so google-auth's 120s default applied to every cert fetch.
    """

    def __init__(self, inner: requests.Request, timeout: float) -> None:
        self._inner = inner
        self._timeout = timeout

    def __call__(
        self,
        url: str,
        method: str = "GET",
        body: Any = None,
        headers: Any = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        bounded = self._timeout if timeout is None else min(timeout, self._timeout)
        return self._inner(
            url, method=method, body=body, headers=headers, timeout=bounded, **kwargs
        )


def _cert_key_ids(certs: object) -> frozenset[str]:
    """The key ids Google's certs hold: ``{kid: pem}``, or a JWK set's ``keys``."""
    if not isinstance(certs, dict):
        raise TypeError("Google's certs are not an object")
    if "keys" in certs:
        return frozenset(str(key["kid"]) for key in certs["keys"] if "kid" in key)
    return frozenset(str(kid) for kid in certs)


def _cert_fetch_failed(reason: str) -> Exception:
    """What google-auth raises for a failed cert fetch: answered as unavailable (503)."""
    # google-auth ships no type hints for its exceptions.
    return google_exceptions.TransportError(reason)  # type: ignore[no-untyped-call]


@dataclass(frozen=True)
class _KeptCerts:
    """Google's certs as a google-auth transport response."""

    data: bytes
    status: int = HTTPStatus.OK
    headers: dict[str, str] = field(default_factory=dict)


class _CertsFromCache:
    """The transport ``verify_oauth2_token`` uses: the certs come from ``cert_cache``.

    ``key_id`` is the one the token's header names, so a key Google rotated in since the
    certs were kept fetches them again (at most once per refetch interval).
    """

    def __init__(self, inner: _BoundedRequest, key_id: str | None, wait_seconds: float) -> None:
        self._inner = inner
        self._key_id = key_id
        self._wait_seconds = wait_seconds

    def __call__(self, url: str, method: str = "GET", **kwargs: Any) -> Any:
        if url != GOOGLE_CERTS_URL or method != "GET":
            return self._inner(url, method=method, **kwargs)
        try:
            keys = cert_cache.get(self._fetch, key_id=self._key_id, wait_seconds=self._wait_seconds)
        except TimeoutError as exc:
            raise _cert_fetch_failed("Timed out waiting for Google's certs") from exc
        return _KeptCerts(keys.body)

    def _fetch(self) -> KeySet:
        response = self._inner(GOOGLE_CERTS_URL, method="GET")
        if response.status != HTTPStatus.OK:
            raise _cert_fetch_failed(f"Could not fetch {GOOGLE_CERTS_URL}")
        try:
            key_ids = _cert_key_ids(json.loads(response.data.decode("utf-8")))
        except (ValueError, TypeError, KeyError) as exc:
            raise _cert_fetch_failed("Google's certs could not be read") from exc
        return KeySet(response.data, key_ids, max_age_seconds(response.headers))


def _key_id(id_token_str: str) -> str | None:
    """The key id the token's header names, read unverified; None when it names none."""
    try:
        kid = jwt.get_unverified_header(id_token_str).get("kid")
    except jwt.PyJWTError:
        return None
    return kid if isinstance(kid, str) else None


def _verify_google_id_token_sync(id_token_str: str, settings: Settings) -> dict[str, Any]:
    timeout = settings.google_auth_timeout_seconds
    request = _CertsFromCache(
        _BoundedRequest(_shared_google_request(), timeout), _key_id(id_token_str), timeout
    )
    try:
        # google-auth ships no type hints for id_token.
        payload: dict[str, Any] = id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
            id_token_str,
            request,
            settings.google_client_id,
        )
    except google_exceptions.TransportError as exc:
        logger.warning("Google cert fetch failed: %s", exc)
        raise GoogleAuthUnavailableError("Google sign-in is unavailable right now") from exc
    except (ValueError, google_exceptions.GoogleAuthError) as exc:
        # GoogleAuthError covers a wrong issuer, which used to surface as a 500.
        logger.warning("Google ID token verification failed: %s", exc)
        raise GoogleAuthError("Invalid Google ID token", code="google_token_invalid") from exc

    if not claim_is_true(payload.get("email_verified")):
        raise GoogleAuthError(
            "Google email address is not verified", code="google_email_unverified"
        )

    return payload


async def verify_google_id_token(id_token_str: str, settings: Settings) -> dict[str, Any]:
    """Verify a Google ID token off the event loop, on sign-in's own threads.

    Its own pool (``core/blocking.py``): queued behind R2 calls and PDF parses on the
    shared one, sign-in ran past its budget and answered 503.
    """
    deadline = settings.google_auth_timeout_seconds + _THREAD_GRACE_SECONDS
    try:
        return await asyncio.wait_for(
            run_blocking("sign_in", _verify_google_id_token_sync, id_token_str, settings),
            timeout=deadline,
        )
    except TimeoutError as exc:
        logger.warning("Google ID token verification timed out after %.1fs", deadline)
        raise GoogleAuthUnavailableError("Google sign-in is unavailable right now") from exc
