"""Google's sign-in certs are kept per process (gateways/signing_keys.py).

google-auth fetched them on every verify and kept none: 100 sign-ins made 100 HTTPS
fetches, one after another or all at once. Here the verify is google-auth's own, on
tokens signed in the test, and Google's endpoint is a fake that counts its fetches.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from google.auth.exceptions import TransportError
from google.auth.transport import requests as g_requests
from google.oauth2 import id_token

from app.core.config import Settings
from app.gateways import google_auth
from app.gateways.signing_keys import REFETCH_INTERVAL_SECONDS, KeyCache, KeySet, max_age_seconds

_CLIENT = "recall.apps.googleusercontent.com"
_SETTINGS = Settings(google_client_id=_CLIENT)
# What Google's cert endpoint sends: public, max-age of about six hours.
_GOOGLE_CACHE_CONTROL = "public, max-age=21600, must-revalidate, no-transform"


@dataclass(frozen=True)
class _Signer:
    """A Google signing key: the tokens it signs, and the cert Google publishes for it."""

    kid: str
    key: rsa.RSAPrivateKey = field(
        default_factory=lambda: rsa.generate_private_key(public_exponent=65537, key_size=2048)
    )

    def token(self, sub: str = "person", *, kid: str | None = None) -> str:
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com",
            "aud": _CLIENT,
            "sub": sub,
            "email": f"{sub}@gmail.com",
            "email_verified": True,
            "iat": now,
            "exp": now + 600,
        }
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": kid or self.kid})

    def cert(self) -> str:
        now = datetime.now(UTC)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, self.kid)])
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(self.key.public_key())
            .serial_number(1)
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=1))
            .sign(self.key, hashes.SHA256())
        )
        return cert.public_bytes(serialization.Encoding.PEM).decode()


@pytest.fixture(scope="module")
def signers() -> tuple[_Signer, _Signer]:
    return _Signer("key-1"), _Signer("key-2")


class _GoogleCerts:
    """Google's cert endpoint (a ``requests.Session``): it counts the fetches it answers."""

    def __init__(self, *published: _Signer, status: int = 200, delay: float = 0.0) -> None:
        self.published = list(published)
        self.status = status
        self.delay = delay
        self.headers = {"Cache-Control": _GOOGLE_CACHE_CONTROL}
        self.fetches = 0

    def close(self) -> None:
        """google-auth's ``Request`` closes its session when it is collected."""

    def request(self, method: str, url: str, **_kwargs: Any) -> Any:
        assert (method, url) == ("GET", google_auth.GOOGLE_CERTS_URL)
        self.fetches += 1
        if self.delay:
            time.sleep(self.delay)
        body = json.dumps({signer.kid: signer.cert() for signer in self.published})
        return SimpleNamespace(
            status_code=self.status, headers=dict(self.headers), content=body.encode()
        )


class _Clock:
    """``time.monotonic`` for the cache, moved by the test."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def google(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    clock = _Clock()
    monkeypatch.setattr(google_auth, "cert_cache", KeyCache(clock=clock))

    def serve(endpoint: _GoogleCerts) -> _GoogleCerts:
        request = g_requests.Request(session=endpoint)  # type: ignore[arg-type]
        monkeypatch.setattr(google_auth, "_google_request", request)
        return endpoint

    return SimpleNamespace(clock=clock, serve=serve)


async def _sign_in(token: str) -> str:
    payload = await google_auth.verify_google_id_token(token, _SETTINGS)
    return str(payload["sub"])


async def test_100_google_sign_ins_fetch_the_certs_once(google, signers):
    endpoint = google.serve(_GoogleCerts(signers[0]))
    for n in range(100):
        assert await _sign_in(signers[0].token(f"person-{n}")) == f"person-{n}"
    assert endpoint.fetches == 1  # it was 100


async def test_100_sign_ins_at_once_share_one_fetch(google, signers):
    """On sign-in's two threads: the second waits for the first's fetch, the rest find it."""
    endpoint = google.serve(_GoogleCerts(signers[0], delay=0.05))
    tokens = [signers[0].token(f"person-{n}") for n in range(100)]
    subjects = await asyncio.gather(*(_sign_in(token) for token in tokens))
    assert subjects == [f"person-{n}" for n in range(100)]
    assert endpoint.fetches == 1  # it was 100


async def test_the_certs_are_kept_as_long_as_google_says(google, signers):
    endpoint = google.serve(_GoogleCerts(signers[0]))
    endpoint.headers["Age"] = "600"  # a cached reply, ten minutes old
    await _sign_in(signers[0].token())
    google.clock.now += 21_600 - 600 - 1
    await _sign_in(signers[0].token())
    assert endpoint.fetches == 1
    google.clock.now += 1
    await _sign_in(signers[0].token())
    assert endpoint.fetches == 2


async def test_a_rotated_key_is_fetched_and_made_up_key_ids_wait_out_the_interval(google, signers):
    old, new = signers
    endpoint = google.serve(_GoogleCerts(old))
    await _sign_in(old.token())
    # Google publishes a new key and starts signing with it.
    endpoint.published.append(new)
    google.clock.now += REFETCH_INTERVAL_SECONDS
    assert await _sign_in(new.token("rotated")) == "rotated"
    assert endpoint.fetches == 2
    # Junk tokens naming key ids Google never published: no fetch each.
    for n in range(100):
        with pytest.raises(google_auth.GoogleAuthError):
            await _sign_in(old.token(kid=f"made-up-{n}"))
    assert endpoint.fetches == 2
    google.clock.now += REFETCH_INTERVAL_SECONDS
    for n in range(100):
        with pytest.raises(google_auth.GoogleAuthError):
            await _sign_in(old.token(kid=f"made-up-{n}"))
    assert endpoint.fetches == 3
    # The keys Google does publish still sign in, from the copy kept.
    assert await _sign_in(new.token("still")) == "still"
    assert endpoint.fetches == 3


async def test_a_failed_fetch_answers_unavailable_and_is_not_kept(google, signers):
    endpoint = google.serve(_GoogleCerts(signers[0], status=503))
    with pytest.raises(google_auth.GoogleAuthUnavailableError):
        await _sign_in(signers[0].token())
    endpoint.status = 200
    assert await _sign_in(signers[0].token("back")) == "back"
    assert endpoint.fetches == 2


@pytest.mark.parametrize("body", [b"<html>", b"[]", b'{"keys": [1]}'])
def test_certs_that_cannot_be_read_are_a_failed_fetch(google, body):
    """A body google-auth could not read answered 401 "Invalid Google ID token"."""
    reply = SimpleNamespace(status=200, headers={}, data=body)
    fetch = google_auth._CertsFromCache(lambda *_a, **_k: reply, None, 1.0)
    with pytest.raises(TransportError):
        fetch(google_auth.GOOGLE_CERTS_URL)


def test_the_certs_url_is_the_one_google_auth_reads() -> None:
    assert google_auth.GOOGLE_CERTS_URL == id_token._GOOGLE_OAUTH2_CERTS_URL


@pytest.mark.parametrize(
    "headers, seconds",
    [
        ({"Cache-Control": _GOOGLE_CACHE_CONTROL}, 21_600),
        ({"cache-control": "max-age=300", "age": "100"}, 200),
        ({"Cache-Control": "max-age=300", "Age": "900"}, 0),
        ({"Cache-Control": "public, s-maxage=900"}, 60),
        ({"Cache-Control": "max-age=999999999"}, 86_400),
        ({}, 60),
    ],
)
def test_max_age_reads_cache_control_less_age(headers: dict[str, str], seconds: float) -> None:
    assert max_age_seconds(headers) == seconds


class _Waiting:
    """A clock that reports when a second caller has read it: each ``get`` reads it while
    holding the cache's lock, once it holds keys."""

    def __init__(self) -> None:
        self.reads = 0
        self.second_caller = threading.Event()

    def __call__(self) -> float:
        self.reads += 1
        if self.reads == 2:
            self.second_caller.set()
        return 0.0


def test_callers_during_a_fetch_wait_for_it_and_share_its_failure() -> None:
    clock = _Waiting()
    cache = KeyCache(clock=clock)
    stale = KeySet(b"{}", frozenset({"key-1"}), max_age_seconds=0)
    cache.get(lambda: stale, key_id=None, wait_seconds=1)
    clock.reads = 0
    fetches: list[str] = []

    def failing_fetch() -> KeySet:
        fetches.append("fetch")
        clock.second_caller.wait(timeout=5)  # the second caller is now waiting on this one
        raise TimeoutError("Google did not answer")

    outcomes: list[str] = []

    def sign_in() -> None:
        try:
            cache.get(failing_fetch, key_id="key-1", wait_seconds=5)
        except TimeoutError as exc:
            outcomes.append(str(exc))

    threads = [threading.Thread(target=sign_in) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert fetches == ["fetch"]
    assert outcomes == ["Google did not answer"] * 2
