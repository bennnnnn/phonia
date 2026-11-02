"""Every refusal answers with one body (code-health audit DUP-10).

A ``DomainError`` reaching a route is answered with its status and
``{"detail": {"code", "message", ...}}``; the routes no longer copy each module's
error into an ``HTTPException`` by hand. An ``HTTPException`` a route, a dependency or
the router itself raises (an unknown path, a missing token) and a request that fails
validation answer the same shape, so a client reads ``code`` from every refusal: they
sent ``{"detail": "..."}`` and FastAPI's error list, which named no code. A failed
validation keeps FastAPI's list as ``errors``.
"""

from __future__ import annotations

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.utils import is_body_allowed_for_status_code
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.unavailable import UNAVAILABLE_CODE
from app.exceptions import DomainError, status_code_name

_INVALID_REQUEST = "The request is not valid."
# A plain HTTPException's gateway failure names no code of its own: the phone read a
# codeless 502, 503 or 504 as Phonia being unavailable (``isServiceUnavailable``), and
# naming it ``unavailable`` keeps that reading. A DomainError names its own (an image
# provider's 502 is ``upstream_failed``, no outage).
_GATEWAY_STATUSES = frozenset({502, 503, 504})


def _plain_code(status_code: int) -> str:
    return UNAVAILABLE_CODE if status_code in _GATEWAY_STATUSES else status_code_name(status_code)


def domain_error_response(exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.body()}, headers=exc.headers
    )


async def _domain_error(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):  # registered for DomainError only
        raise exc
    return domain_error_response(exc)


def _status_phrase(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Request refused"


def http_error_detail(status_code: int, detail: object) -> dict[str, object]:
    """An ``HTTPException``'s detail as the refusal body: a string becomes its message, a
    body that names a code keeps it, and the status names the code otherwise."""
    if isinstance(detail, dict):
        body = {str(key): value for key, value in detail.items()}
        code = body.get("code")
        message = body.get("message")
        body["code"] = code if isinstance(code, str) else _plain_code(status_code)
        body["message"] = message if isinstance(message, str) else _status_phrase(status_code)
        return body
    message = detail.strip() if isinstance(detail, str) else ""
    return {"code": _plain_code(status_code), "message": message or _status_phrase(status_code)}


async def _http_error(_request: Request, exc: Exception) -> Response:
    if not isinstance(exc, StarletteHTTPException):  # registered for HTTPException only
        raise exc
    headers = dict(exc.headers) if exc.headers else None
    if not is_body_allowed_for_status_code(exc.status_code):
        return Response(status_code=exc.status_code, headers=headers)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": http_error_detail(exc.status_code, exc.detail)},
        headers=headers,
    )


def _validation_message(errors: list[dict[str, object]]) -> str:
    messages = [str(error.get("msg") or "") for error in errors]
    return ", ".join(message for message in messages if message) or _INVALID_REQUEST


async def _validation_error(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # registered for it only
        raise exc
    errors = jsonable_encoder(exc.errors())
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "code": status_code_name(422),
                "message": _validation_message(errors),
                "errors": errors,
            }
        },
    )


def register_domain_error_handler(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
