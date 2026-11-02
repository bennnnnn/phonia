"""A GET that returns rows returns a ``Page`` (code-health audit CLAR-12).

Five list endpoints used three list keys, three continuation signals and three cursor
kinds. ``GET /chats`` never showed the 201st chat, and offset paging repeated or skipped
attachments and search hits when the list changed while the phone paged it. A GET whose
response holds rows now answers ``{items, next_cursor}`` (``models/schemas/page.py``,
paged by ``repositories/keyset.py``), or is listed here with the reason it is not.

The check reads the OpenAPI document: FastAPI 0.14x wraps each included router, so
``app.routes`` no longer lists the endpoints.
"""

from __future__ import annotations

from typing import Any

from app.main import app

# GET path -> why its rows are not a Page.
_NOT_PAGED = {
    "/admin/dlq": "an operator's look at failed jobs, newest first up to `count`",
    "/auth/sessions": "the user's signed-in devices",
    "/billing/plans": "the plan catalog",
    "/chats": "the drawer's groups by recency; `next_cursor` pages the dated chats",
    "/chats/{chat_id}/messages": "a window around one message, read older and newer by id",
    "/memories": "the user's facts on one screen; at most 150 are active",
    "/memories/documents": "one entry per memory document",
    "/models": "the model catalog",
}


def _schemas() -> tuple[dict[str, Any], dict[str, Any]]:
    """GET path -> its 200 JSON schema, and the components they refer to."""
    document = app.openapi()
    found = {
        path: operations["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        for path, operations in document["paths"].items()
        if "application/json"
        in operations.get("get", {}).get("responses", {}).get("200", {}).get("content", {})
    }
    return found, document.get("components", {}).get("schemas", {})


def _resolve(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        schema = components[schema["$ref"].rsplit("/", 1)[-1]]
    return schema


def _holds_rows(schema: dict[str, Any], components: dict[str, Any]) -> bool:
    """A list of objects, or an object with one among its fields."""

    def is_rows(part: dict[str, Any]) -> bool:
        part = _resolve(part, components)
        return any(
            branch.get("type") == "array" and "$ref" in branch.get("items", {})
            for branch in part.get("anyOf", [part])
        )

    schema = _resolve(schema, components)
    return is_rows(schema) or any(is_rows(field) for field in schema.get("properties", {}).values())


def _is_page(schema: dict[str, Any], components: dict[str, Any]) -> bool:
    return {"items", "next_cursor"} <= set(_resolve(schema, components).get("properties", {}))


def test_every_get_that_returns_rows_is_a_page() -> None:
    schemas, components = _schemas()
    unpaged = sorted(
        path
        for path, schema in schemas.items()
        if _holds_rows(schema, components)
        and not _is_page(schema, components)
        and path not in _NOT_PAGED
    )
    assert unpaged == [], "answer Page[...] and page by keyset (repositories/keyset.py)"


def test_every_exemption_still_returns_rows_unpaged() -> None:
    schemas, components = _schemas()
    stale = sorted(
        path
        for path in _NOT_PAGED
        if path not in schemas
        or not _holds_rows(schemas[path], components)
        or _is_page(schemas[path], components)
    )
    assert stale == [], "drop the exemption"


def test_the_pages_the_audit_named_are_pages() -> None:
    schemas, components = _schemas()
    for path in ("/attachments", "/search", "/todos/page"):
        assert _is_page(schemas[path], components), path
