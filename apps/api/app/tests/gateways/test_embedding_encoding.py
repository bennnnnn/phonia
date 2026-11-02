"""The query-embedding cache's encoding."""

from app.gateways.embedding_gateway import parse_embedding, serialize_embedding


def test_embedding_json_roundtrip():
    vec = [0.1, 0.2, 0.3]
    raw = serialize_embedding(vec)
    parsed = parse_embedding(raw)
    assert parsed == vec
