"""Every refusal a service raises answers with one body (code-health audit DUP-10).

A ``DomainError`` reaching a route is answered with its status and
``{"detail": {"code", "message", ...}}``; the routes no longer copy each module's
error into an ``HTTPException`` by hand.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.exceptions import DomainError


def domain_error_response(exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.body()}, headers=exc.headers
    )


async def _domain_error(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):  # registered for DomainError only
        raise exc
    return domain_error_response(exc)


def register_domain_error_handler(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
