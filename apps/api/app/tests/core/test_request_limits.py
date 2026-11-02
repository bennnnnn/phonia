import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.request_limits import reject_oversized


def _request(content_length: str | None) -> Request:
    headers = [] if content_length is None else [(b"content-length", content_length.encode())]
    return Request({"type": "http", "headers": headers})


@pytest.mark.parametrize(
    ("content_length", "body", "refused"),
    [
        (None, b"", False),
        ("10", b"", False),
        ("11", b"", True),
        ("not a number", b"", False),
        (None, b"x" * 10, False),
        (None, b"x" * 11, True),
        ("10", b"x" * 11, True),
    ],
)
def test_reject_oversized_refuses_a_declared_or_read_body_over_the_cap(
    content_length: str | None, body: bytes, refused: bool
) -> None:
    request = _request(content_length)
    if not refused:
        reject_oversized(request, body, 10, "Too big")
        return
    with pytest.raises(HTTPException) as exc:
        reject_oversized(request, body, 10, "Too big")
    assert (exc.value.status_code, exc.value.detail) == (413, "Too big")
