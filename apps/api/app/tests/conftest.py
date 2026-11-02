import os
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest
from hypothesis import settings as hypothesis_settings

# Match local `.env.example` — Settings.environment defaults to production
# (fail-closed). Tests that construct Settings() without an env file need this.
os.environ.setdefault("ENVIRONMENT", "development")

# LiteLLM's import runs load_dotenv() in its default DEV mode, copying a developer's
# apps/api/.env into os.environ, where it outranks Settings defaults. Tests then pass
# in CI and fail locally (a lower DAILY_TOKEN_LIMIT, say). Any other mode skips it.
os.environ.setdefault("LITELLM_MODE", "PRODUCTION")

# CI has no provider key, so mock mode (``should_mock_llm``: enabled and no key) is what the
# suite is written against. A developer's apps/api/.env key would turn it off and send those
# tests to the real provider. A key exported in the shell still wins.
os.environ.setdefault("OPENROUTER_API_KEY", "")
# No paid or outside service is reachable from a test, whatever apps/api/.env holds: an empty
# key is "not configured" to every gateway. A test of a gateway passes its own Settings.
for _provider_key in (
    "OPENAI_API_KEY",
    "TAVILY_API_KEY",
    "RESEND_API_KEY",
    "MATHPIX_APP_KEY",
    "REVENUECAT_SECRET_KEY",
):
    os.environ[_provider_key] = ""
os.environ["WEB_SEARCH_FALLBACK_ENABLED"] = "false"

# Under pytest-xdist (CI runs ``-n``) each worker gets its own database and Redis index,
# which CI copies from the migrated one: two runs sharing a database held each other's rows
# and locks, and one hung at 94% with sessions "idle in transaction" (2026-10-31). A ``-n``
# run without them is refused (``pytest_configure``): it would point every worker at one
# shared development database.
_PER_WORKER = os.environ.get("RECALL_TEST_DB_PER_WORKER") == "1"
_XDIST_WORKER = os.environ.get("PYTEST_XDIST_WORKER", "")
if _XDIST_WORKER.startswith("gw") and _PER_WORKER:
    if "DATABASE_URL" in os.environ:  # the sweeps job fakes the database and sets none
        _database, _, _query = os.environ["DATABASE_URL"].partition("?")
        _query = f"?{_query}" if _query else ""
        os.environ["DATABASE_URL"] = f"{_database}_{_XDIST_WORKER}{_query}"
    _redis = os.environ.get("REDIS_URL", "redis://localhost:6379").rstrip("/")
    _redis_base, _, _redis_index = _redis.rpartition("/")
    _redis = _redis_base if _redis_index.isdigit() else _redis
    os.environ["REDIS_URL"] = f"{_redis}/{int(_XDIST_WORKER[2:]) + 1}"

# A maths decline that would hide a programming error (an AttributeError, NameError or our
# own TypeError; see app/modules/math/solve/declines.py) raises under pytest. A value already in
# the environment wins: RECALL_STRICT_DECLINES=0 runs the suite with production's declines.
_STRICT_DECLINES_ASKED = "RECALL_STRICT_DECLINES" in os.environ
os.environ.setdefault("RECALL_STRICT_DECLINES", "1")

# Hypothesis explores new examples on every local run. CI sets HYPOTHESIS_PROFILE=ci:
# the same examples every run, so an unrelated change never turns a property red
# (code-health audit TEST-08); a failure found locally is pinned with @example.
hypothesis_settings.register_profile("ci", derandomize=True, database=None)
hypothesis_settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))

# Helper modules under app/tests (fakes, chat_test_support, the sweeps) get pytest's assert
# messages as test files and conftests do. This works only before any of them is imported:
# a helper a test imports first would otherwise run with plain asserts.
_TESTS = Path(__file__).parent
pytest.register_assert_rewrite(
    *(
        ".".join(path.relative_to(_TESTS.parents[1]).with_suffix("").parts)
        for path in _TESTS.rglob("*.py")
        if not path.name.startswith("test_") and path.name not in {"conftest.py", "__init__.py"}
    )
)

# Before any test module imports the app (and with it SymPy's names): a reading or a SymPy
# call made on the event loop by production code fails the test (app/tests/loop_guard.py).
from app.core import readings
from app.tests import loop_guard

loop_guard.install()


_REAL_CONNECT: dict[str, object] = {}


def _distributed(config: pytest.Config) -> bool:
    """Any xdist distribution: ``-n``, ``--tx 2*popen`` or a ``--dist`` mode other than "no"."""
    option = config.option
    return bool(
        getattr(option, "numprocesses", None)
        or getattr(option, "tx", None)
        or getattr(option, "dist", "no") not in (None, "no")
    )


def pytest_configure(config: pytest.Config) -> None:
    """A distributed run needs a database per worker (above), or every worker writes to one."""
    if _distributed(config) and not _PER_WORKER:
        pytest.exit(
            "A distributed run (-n, --tx, --dist) needs a database per worker: CI copies "
            "one for each and sets RECALL_TEST_DB_PER_WORKER=1. Locally, run without "
            "xdist (the development database is shared).",
            returncode=4,
        )


@pytest.fixture(autouse=True)
def _nothing_read_on_the_loop():
    """No production coroutine reads a message or runs SymPy on the event loop."""
    loop_guard.found.clear()
    yield
    if loop_guard.found:
        ran = sorted(set(loop_guard.found))
        loop_guard.found.clear()
        pytest.fail(
            "Ran on the event loop; read it in the SymPy pool (app/core/readings.py):\n"
            + "\n".join(ran)
        )


@pytest.fixture(autouse=True)
def _no_turn_left_behind():
    """A sync test that begins a turn leaves none behind: the next test on the worker
    would otherwise run inside it, and the loop guard would fail its own readings."""
    yield
    readings._MEMO.set(None)


@pytest.fixture(autouse=True)
def _hermetic_redis():
    """Every Redis client the app makes talks to one in-memory server per test.

    Isolation used to be opt-in per consumer: 37 modules call ``get_redis_client()``,
    four were faked, and the rest reached the developer's Redis (or a client bound to
    an earlier test's event loop). ``real_redis`` opts a test out.
    """
    from app.core import redis as redis_module

    _REAL_CONNECT.setdefault("connect", redis_module._connect)
    server = fakeredis.FakeServer()

    def connect(_socket_timeout: float) -> fakeredis.aioredis.FakeRedis:
        return fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)

    redis_module.get_redis_client.cache_clear()
    redis_module.get_jobs_redis_client.cache_clear()
    with patch.object(redis_module, "_connect", connect):
        yield server
    redis_module.get_redis_client.cache_clear()
    redis_module.get_jobs_redis_client.cache_clear()


@pytest.fixture(autouse=True)
def _fresh_db_pool():
    """Each test starts with an empty connection pool.

    A pooled asyncpg connection belongs to the event loop that opened it, and each test
    (and each ``TestClient``) runs its own loop. ``core/pool_liveness.py`` replaces one
    opened on another loop at checkout; dropping the pool here also keeps a test from
    inheriting another test's connections at all.
    """
    from app.core.db import engine

    engine.sync_engine.dispose(close=False)
    yield
    engine.sync_engine.dispose(close=False)


@pytest.fixture
def real_redis(_hermetic_redis):
    """The configured Redis, for a test that needs a real server
    (``security/test_quota_carryover_link.py``)."""
    from app.core import redis as redis_module

    redis_module.get_redis_client.cache_clear()
    with patch.object(redis_module, "_connect", _REAL_CONNECT["connect"]):
        yield


_LOCAL_HOSTS = frozenset({"testserver", "test", "localhost", "127.0.0.1"})


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """No test reaches the internet: an outside request fails as a refused connection.

    Mock transports and the in-process app are allowed. DuckDuckGo's client is not httpx,
    so it is refused by name.
    """
    import httpx

    real_send = httpx.AsyncClient.send

    async def guarded_send(self, request, *args, **kwargs):
        transport = getattr(self, "_transport", None)
        if request.url.host in _LOCAL_HOSTS or isinstance(
            transport, httpx.MockTransport | httpx.ASGITransport
        ):
            return await real_send(self, request, *args, **kwargs)
        raise httpx.ConnectError(f"no network in tests ({request.url.host})", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", guarded_send)

    class _NoDuckDuckGo:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("no network in tests (DuckDuckGo)")

    monkeypatch.setattr("ddgs.DDGS", _NoDuckDuckGo)


@pytest.fixture(name="fake_session")
def fake_session_fixture():
    """An ``AsyncSession`` over empty tables, specced so ``add`` stays synchronous
    (``app.tests.fakes.fake_session``; code-health audit TEST-07)."""
    from app.tests import fakes  # after loop_guard.install(): fakes imports the app

    return fakes.fake_session()


@pytest.fixture
async def fake_redis(_hermetic_redis):
    """A client on the test's in-memory server: what the app's own clients see."""
    client = fakeredis.aioredis.FakeRedis(server=_hermetic_redis, decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def production_declines(monkeypatch):
    """Maths declines as production has them (silent), unless the run set RECALL_STRICT_DECLINES."""
    if not _STRICT_DECLINES_ASKED:
        monkeypatch.setenv("RECALL_STRICT_DECLINES", "0")


@pytest.fixture(autouse=True)
def _no_sign_in_keys_kept(monkeypatch):
    """Each test starts with no provider keys kept (gateways/signing_keys.py): keys one test
    fetched, or the refetch it just made, would answer another test's sign-in."""
    from app.gateways import apple_auth, google_auth
    from app.gateways.signing_keys import KeyCache

    monkeypatch.setattr(google_auth, "cert_cache", KeyCache())
    monkeypatch.setattr(apple_auth, "_jwks_cache", None)
    monkeypatch.setattr(apple_auth, "_jwks_fetched_at", 0.0)


@pytest.fixture(autouse=True)
def _tool_registry_restored():
    """A test that fills or clears the model's tool registry leaves it as it found it,
    so the suite passes in any order (code-health audit TEST-10)."""
    from app.gateways.mcp import registry

    before = registry.list_adapters()
    yield
    registry.clear()
    for adapter in before:
        registry.register(adapter)


@pytest.fixture
def quota_clock():
    """The UTC day the daily counters see, 2026-10-16 until a test sets ``.day``.

    A provider fake that sets ``quota_clock.day = quota_clock.next_day`` makes
    its request run past UTC midnight.
    """
    from app.services.quota import counters

    clock = SimpleNamespace(day=date(2026, 10, 16), next_day=date(2026, 10, 17))
    with patch.object(counters, "clock", lambda: clock.day):
        yield clock


@pytest.fixture(autouse=True)
def _isolate_rest_rate_limiter():
    """Give the global REST rate-limit middleware a fresh in-memory Redis per
    test so counters don't accumulate across the suite against the real Redis
    (which produced spurious 429s and order-dependent failures locally).

    Tests that exercise the limiter directly patch `allow_request`/`get_redis_client`
    inside their own `with patch(...)` blocks, which override this for their
    duration. The middleware otherwise hits the fake client, whose counts start
    at zero every test.
    """
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch("app.core.rest_rate_limit.get_redis_client", return_value=client):
        yield


@pytest.fixture(autouse=True)
def _ai_data_consent_given():
    """Test users have agreed to what goes to outside AI services.

    The consent gate (``app/core/consent.py``) refuses a chat turn,
    speech and a scan read for an account that has not; most tests build users
    without that column. A test that checks the refusal takes ``consent_enforced``.
    """
    given = patch("app.core.consent.has_ai_data_consent", return_value=True)
    given.start()
    yield given
    given.stop()


@pytest.fixture
def consent_enforced(_ai_data_consent_given):
    """The real consent check, for tests of the refusal."""
    _ai_data_consent_given.stop()


@pytest.fixture(autouse=True)
def model_spend_redis():
    """The gateway spend meter's Redis: a fresh fake per test, never the real one.

    A test whose provider fake reports token usage would otherwise add to the
    real ``spend_musd`` counter. Tests read this fixture to see what was metered.
    """
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch("app.gateways.llm_spend.get_redis_client", return_value=client):
        yield client


@pytest.fixture(autouse=True)
def user_generation_redis():
    """Where user-row writes publish their generation (core/user_cache): a fresh fake per test.

    In production that is the app's one Redis, where every token check reads the
    generation. A test that drives the app through a fake Redis makes it this same
    client (the round-trip guard), or points the user cache at its own (security
    ``use_fake_redis``), so a write's generation is where the next request reads it.
    """
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch("app.core.user_cache.get_redis_client", return_value=client):
        yield client


@pytest.fixture(autouse=True)
def structured_invalid_redis():
    """The invalid-structured-output counter's Redis: a fresh fake per test."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch("app.gateways.structured_completion.get_redis_client", return_value=client):
        yield client


@pytest.fixture(autouse=True)
def _no_real_embedding_provider():
    """The embedding provider is never called from a test.

    ``embed_many`` sends batches before it falls back to ``embed_text``, so a
    test that patches only ``embed_text`` would otherwise send its first batch
    to the real provider. A failed batch takes the fallback; tests of the
    request itself patch ``aembedding`` over this.
    """
    refused = AsyncMock(side_effect=RuntimeError("no embedding provider in tests"))
    with patch("app.gateways.embedding_gateway.aembedding", refused):
        yield


@pytest.fixture(autouse=True)
def ocr_allowance_redis():
    """The OCR allowance and kept OCR text: a fresh fake per test, never the real one.

    Every index job reads it, so a test that indexes a file would otherwise reach
    the real Redis (and a client bound to an earlier test's event loop).
    """
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch("app.modules.attachments.ocr_allowance.get_redis_client", return_value=client):
        yield client


@pytest.fixture(autouse=True)
def _reset_sympy_executor():
    """Use a fresh in-process math worker for ordinary unit tests.

    Production hard-kill behavior has dedicated ProcessPoolSympyExecutor
    tests. Spawning a new subprocess pool in every unrelated async test is
    both unnecessary and capable of exhausting macOS's semaphore table over
    a full suite. The thread worker also correctly observes monkeypatches;
    the production ``spawn`` context intentionally does not inherit them.
    """
    from app.core.sympy_executor import set_sympy_executor
    from app.tests.sympy_support import ThreadSympyExecutor

    set_sympy_executor(ThreadSympyExecutor(max_workers=1))
    yield
    set_sympy_executor(None)


@pytest.fixture(autouse=True)
def _thread_document_executor():
    """Documents parse on an in-process thread in tests, as maths does above."""
    from app.core.document_executor import set_document_executor
    from app.tests.sympy_support import ThreadSympyExecutor

    set_document_executor(ThreadSympyExecutor(max_workers=2))
    yield
    set_document_executor(None)


@pytest.fixture
def thread_sympy_executor():
    """Swap the production ProcessPoolSympyExecutor for an in-process
    thread-based one. Needed for tests that monkeypatch module-level SymPy
    functions with local closures (closures aren't picklable across a
    subprocess boundary) or that spy on in-process state (a subprocess can't
    write back to the test's memory). The production executor's hard-kill
    behavior is exercised in test_sympy_executor.py."""
    from app.core.sympy_executor import set_sympy_executor
    from app.tests.sympy_support import ThreadSympyExecutor

    set_sympy_executor(ThreadSympyExecutor(max_workers=1))
    yield
    set_sympy_executor(None)


@pytest.fixture
async def db_session():
    """Real Postgres session isolated by an outer transaction and savepoints.

    Product-module and repository tests share this fixture. A commit issued by
    code under test only releases a savepoint; the outer rollback always
    discards the test's data.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.db import engine

    # Connections are bound to the event loop that opened them. Forget any
    # pooled connection left by a TestClient/anyio loop before and after use.
    await engine.dispose(close=False)
    async with engine.connect() as connection:
        await connection.begin()
        session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await connection.rollback()
    await engine.dispose(close=False)
