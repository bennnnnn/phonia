"""Weak ETags on the lists the phone reads again (code-health audit NET-16)."""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.core.etag import body_etag, conditional_json


class _Page(BaseModel):
    items: list[int]


def _request(if_none_match: str | None):
    headers = {} if if_none_match is None else {"if-none-match": if_none_match}
    return SimpleNamespace(headers=headers)


def test_the_etag_follows_the_body():
    assert body_etag(b"a") == body_etag(b"a")
    assert body_etag(b"a") != body_etag(b"b")
    assert body_etag(b"a").startswith('W/"')


def test_a_new_body_is_sent_with_its_etag():
    response = conditional_json(_request(None), _Page(items=[1, 2]))
    assert response.status_code == 200
    assert response.body == b'{"items":[1,2]}'
    assert response.headers["etag"] == body_etag(b'{"items":[1,2]}')
    assert response.headers["cache-control"] == "private, no-cache"


_ONE = body_etag(b'{"items":[1]}')


@pytest.mark.parametrize(
    "header",
    [_ONE, _ONE.removeprefix("W/"), f'W/"other", {_ONE}', "*"],
)
def test_a_body_the_client_holds_is_a_304(header):
    response = conditional_json(_request(header), _Page(items=[1]))
    assert response.status_code == 304
    assert response.body == b""
    assert response.headers["etag"] == _ONE


@pytest.mark.parametrize("header", ['W/"other"', "", " , "])
def test_another_etag_gets_the_body(header):
    assert conditional_json(_request(header), _Page(items=[1])).status_code == 200
