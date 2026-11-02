"""The query-embedding cache's encoding: packed float32, JSON entries still read."""

import json
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.gateways import embedding_gateway
from app.gateways.embedding_gateway import parse_embedding, serialize_embedding


def test_embedding_packed_roundtrip_is_float32_exact():
    vec = [0.1, -0.25, 3.5, 0.0]
    raw = serialize_embedding(vec)
    parsed = parse_embedding(raw)
    assert raw.startswith("f32:")
    assert parsed == pytest.approx(vec, rel=1e-6)


def test_embedding_packed_is_far_smaller_than_json():
    vec = [0.012345678901234567 * (i % 97 - 48) for i in range(1536)]
    packed = serialize_embedding(vec)
    assert len(packed) < 8_300
    assert len(packed) * 3 < len(json.dumps(vec))


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("[0.1, 0.2, 0.3]", [0.1, 0.2, 0.3]),  # written by the release before packing
        ("", None),
        (None, None),
        ("not json", None),
        ('{"a": 1}', None),
        ("f32:!!notbase64!!", None),
        ("f32:AAA=", None),  # two bytes: not a whole float
        ("f32:", None),
    ],
)
def test_parse_embedding_reads_old_json_and_rejects_garbage(raw, expected):
    assert parse_embedding(raw) == expected


async def test_query_embed_cache_writes_packed_with_short_ttl(fake_redis, monkeypatch):
    settings = Settings()
    user_id = uuid4()

    async def embed(_settings: Settings, _text: str) -> list[float]:
        return [0.5] * 1536

    monkeypatch.setattr(embedding_gateway, "embed_text", embed)
    vec = await embedding_gateway.get_or_embed_query(settings, user_id, "What is my plan?")

    key = embedding_gateway._embed_cache_key(user_id, "What is my plan?")
    stored = await fake_redis.get(key)
    assert vec == [0.5] * 1536
    assert stored.startswith("f32:")
    assert 0 < await fake_redis.ttl(key) <= 300


async def test_query_embed_cache_hit_on_a_json_entry_from_before(fake_redis, monkeypatch):
    user_id = uuid4()
    key = embedding_gateway._embed_cache_key(user_id, "old question")
    await fake_redis.set(key, json.dumps([0.25] * 4), ex=60)

    async def must_not_embed(_settings: Settings, _text: str) -> list[float]:
        raise AssertionError("a cached JSON vector is still a hit")

    monkeypatch.setattr(embedding_gateway, "embed_text", must_not_embed)
    vec = await embedding_gateway.get_or_embed_query(Settings(), user_id, "old question")
    assert vec == [0.25] * 4
