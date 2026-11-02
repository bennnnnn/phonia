"""The database URL as asyncpg takes it: SSL, Neon's pooler host, connection recycling."""

from app.core.database_url import (
    pool_recycle_seconds_for_url,
    prefer_neon_pooler_hostname,
    prepare_asyncpg_url,
)

# ── database_url ───────────────────────────────────────────────────────────────


def test_prepare_asyncpg_url_strips_sslmode():
    url = "postgresql+asyncpg://user:pass@host/db?sslmode=require"
    clean, args = prepare_asyncpg_url(url)
    assert "sslmode" not in clean
    assert args == {"ssl": "require"}


def test_prepare_asyncpg_url_neon_host_sets_ssl():
    url = "postgresql+asyncpg://user:pass@ep-foo.c-4.us-east-1.aws.neon.tech/db"
    _, args = prepare_asyncpg_url(url)
    assert args == {"ssl": "require"}


def test_prepare_asyncpg_url_plain_host_no_ssl():
    url = "postgresql+asyncpg://user:pass@localhost/db"
    clean, args = prepare_asyncpg_url(url)
    assert args == {}
    assert "localhost" in clean


def test_prepare_asyncpg_url_preserves_other_params():
    url = "postgresql+asyncpg://user:pass@host/db?sslmode=require&application_name=app"
    clean, _args = prepare_asyncpg_url(url)
    assert "application_name=app" in clean
    assert "sslmode" not in clean


def test_prefer_neon_pooler_hostname():
    host = "ep-cool-name-123456.us-east-2.aws.neon.tech"
    assert prefer_neon_pooler_hostname(host) == "ep-cool-name-123456-pooler.us-east-2.aws.neon.tech"
    assert prefer_neon_pooler_hostname("localhost") == "localhost"


def test_prepare_asyncpg_url_neon_pooler_rewrite():
    url = "postgresql+asyncpg://user:pass@ep-foo.us-east-1.aws.neon.tech/db"
    clean, args = prepare_asyncpg_url(url, prefer_neon_pooler=True)
    assert "-pooler." in clean
    assert args == {"ssl": "require"}


def test_pool_recycle_seconds_for_url():
    assert pool_recycle_seconds_for_url("postgresql://ep-x-pooler.neon.tech/db") == 1800
    assert pool_recycle_seconds_for_url("postgresql://localhost/db") == 300
