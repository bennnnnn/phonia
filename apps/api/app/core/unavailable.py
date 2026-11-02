"""Map "a dependency is down or slow" to 503 + Retry-After instead of a bare 500.

Covers the database (pool exhaustion after ``db_pool_timeout_seconds``, a
statement or connect timeout, a dropped or refused connection) and Redis (our
``RedisUnavailableError``, raised where auth, quota or locks fail closed, and the
client's own connection and timeout errors that reach a route uncaught). Clients retry
a 503 with backoff; a 500 reads as a bug. The exception is still logged with
its traceback; the response body never carries it.

The body names the code ``unavailable`` (``{"detail": {"code", "message"}}``, as every
coded refusal: ``docs/fixtures/error_codes.json``), the code the chat socket's error
frame already sends for the same outage. It was the English alone, so the phone could
tell an outage from another 503 ("not configured") only by its words.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis import exceptions as redis_exc
from sqlalchemy import exc as sa_exc

from app.exceptions import RedisUnavailableError

logger = logging.getLogger(__name__)

UNAVAILABLE_CODE = "unavailable"
UNAVAILABLE_DETAIL = "Service temporarily unavailable. Please retry shortly."
RETRY_AFTER_SECONDS = "5"

# TimeoutError covers asyncpg's connect and command timeouts (raised as-is,
# not wrapped by SQLAlchemy). ConnectionError covers refused/reset sockets.
# redis-py's errors do not subclass the builtins, so they are listed too.
UNAVAILABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    sa_exc.TimeoutError,
    sa_exc.OperationalError,
    sa_exc.InterfaceError,
    TimeoutError,
    ConnectionError,
    redis_exc.ConnectionError,
    redis_exc.TimeoutError,
)


def unavailable_detail(message: str = UNAVAILABLE_DETAIL) -> dict[str, str]:
    """A 503's ``detail``: the code a client switches on, and the English."""
    return {"code": UNAVAILABLE_CODE, "message": message}


def unavailable_response(message: str = UNAVAILABLE_DETAIL) -> JSONResponse:
    """503 + Retry-After: a dependency is down, retry shortly."""
    return JSONResponse(
        status_code=503,
        content={"detail": unavailable_detail(message)},
        headers={"Retry-After": RETRY_AFTER_SECONDS},
    )


async def _unavailable(request: Request, exc: Exception) -> JSONResponse:
    logger.warning(
        "Dependency unavailable on %s %s: %s",
        request.method,
        request.url.path,
        type(exc).__name__,
        exc_info=exc,
    )
    return unavailable_response()


async def _redis_unavailable(request: Request, exc: Exception) -> JSONResponse:
    # Same body as the routes' own redis_unavailable_http_exception (core/deps.py).
    logger.warning("Redis unavailable on %s %s", request.method, request.url.path, exc_info=exc)
    message = exc.message if isinstance(exc, RedisUnavailableError) else UNAVAILABLE_DETAIL
    return unavailable_response(message)


def register_unavailable_handlers(app: FastAPI) -> None:
    for exc_type in UNAVAILABLE_EXCEPTIONS:
        app.add_exception_handler(exc_type, _unavailable)
    app.add_exception_handler(RedisUnavailableError, _redis_unavailable)
