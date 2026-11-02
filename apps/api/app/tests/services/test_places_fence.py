from app.services.places_fence import sanitize_places_fences


def test_sanitize_places_rewrites_valid_payload() -> None:
    raw = 'Here\n```places\n[{"name":"Cafe","url":"https://maps.example/c","extra":1}]\n```\n'
    out = sanitize_places_fences(raw)
    assert "```places" in out
    assert "Cafe" in out
    assert "extra" not in out
    assert "https://maps.example/c" in out


def test_sanitize_places_drops_invalid_json() -> None:
    raw = "Before\n```places\n{not-json\n```\nAfter"
    out = sanitize_places_fences(raw)
    assert "```places" not in out
    assert "Before" in out
    assert "After" in out


def test_sanitize_places_drops_rows_without_name() -> None:
    raw = '```places\n[{"url":"https://example.com"},{"name":"OK"}]\n```\n'
    out = sanitize_places_fences(raw)
    assert "OK" in out
    assert "example.com" not in out
