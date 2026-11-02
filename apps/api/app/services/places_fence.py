"""Validate model-authored ```places JSON before persist (golden rule 6)."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.services.md_fence_scan import map_closed_fences


class PlaceFenceItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=200)
    url: str = Field(default="", max_length=2000)
    note: str = Field(default="", max_length=500)
    address: str = Field(default="", max_length=400)
    price: str = Field(default="", max_length=40)


def parse_places_payload(raw: object) -> list[PlaceFenceItem]:
    if not isinstance(raw, list):
        return []
    items: list[PlaceFenceItem] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        try:
            items.append(PlaceFenceItem.model_validate(row))
        except ValidationError:
            continue
    return items


def places_payload_dicts(items: list[PlaceFenceItem]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in items:
        row: dict[str, str] = {"name": item.name}
        if item.url.strip():
            row["url"] = item.url.strip()
        if item.note.strip():
            row["note"] = item.note.strip()
        if item.address.strip():
            row["address"] = item.address.strip()
        if item.price.strip():
            row["price"] = item.price.strip()
        rows.append(row)
    return rows


def _rewrite_places_body(body: str) -> str:
    try:
        parsed: object = json.loads(body.strip() or "[]")
    except json.JSONDecodeError:
        return ""
    items = parse_places_payload(parsed)
    if not items:
        return ""
    payload = json.dumps(places_payload_dicts(items), ensure_ascii=False)
    return f"```places\n{payload}\n```\n"


def sanitize_places_fences(text: str) -> str:
    """Drop invalid ```places fences; rewrite valid ones to canonical JSON."""
    if "```places" not in text.lower():
        return text
    return map_closed_fences(text, "places", _rewrite_places_body)
