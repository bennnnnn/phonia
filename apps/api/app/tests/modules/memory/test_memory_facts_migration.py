"""Pure helpers from alembic revision 0087 — no database."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from app.modules.memory.facts import pack_memories


def _migration():
    path = Path(__file__).resolve().parents[4] / "alembic/versions/0087_memory_facts.py"
    spec = importlib.util.spec_from_file_location("memory_facts_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_keep_source_embedding_only_when_row_does_not_split():
    migration = _migration()
    assert migration._keep_source_embedding(["Lives in Boston"]) is True
    assert migration._keep_source_embedding(["Lives in Boston", "Has a dog"]) is False


def test_collapse_prefers_active_keeper_and_merges_inactive_text():
    migration = _migration()
    active = SimpleNamespace(
        id=1,
        status="active",
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
        text="Likes tea",
    )
    muted = SimpleNamespace(
        id=2,
        status="muted",
        updated_at=datetime(2026, 1, 3, tzinfo=UTC),
        text="Old tea note",
    )
    keeper, merged = migration._keeper_and_merged([muted, active])
    assert keeper.id == 1
    assert "Likes tea" in merged
    assert "Old tea note" in merged


def test_pack_memories_skips_oversized_first_fact():
    long_pref = SimpleNamespace(type="preference", text="x" * 2000)
    other = SimpleNamespace(type="focus", text="Ship the quiz this week")
    packed = pack_memories([long_pref, other], max_chars=200)
    assert packed == [other]
