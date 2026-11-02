"""What production logs and Sentry can see: levels, ids on every line, saturation."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import patch

import pytest

from app.core import saturation
from app.core.log_context import bound_log_ids, current_log_ids, new_turn_id
from app.core.logging import _JsonFormatter, _RequestIdFormatter, setup_logging


@pytest.fixture
def restore_root_level():
    root = logging.getLogger()
    level, handlers = root.level, list(root.handlers)
    yield
    root.setLevel(level)
    root.handlers[:] = handlers


@pytest.mark.parametrize(("configured", "expected"), [("DEBUG", 10), ("warning", 30), ("nope", 20)])
def test_setup_logging_honours_log_level(
    restore_root_level, configured: str, expected: int
) -> None:
    """The root level was fixed at INFO, so 91 DEBUG-only failures could never be seen."""
    setup_logging(level=configured)
    assert logging.getLogger().level == expected


def _record(message: str = "Chat stream failed") -> logging.LogRecord:
    return logging.LogRecord("app.chat", logging.ERROR, __file__, 1, message, (), None)


def test_a_line_inside_a_turn_names_its_chat_and_turn() -> None:
    with bound_log_ids(chat_id="c-1", turn="t-1"), bound_log_ids(user_id="u-1"):
        line = _RequestIdFormatter().format(_record())
        payload = _JsonFormatter().format(_record())
    assert "chat_id=c-1 turn=t-1 user_id=u-1" in line
    assert '"chat_id":"c-1"' in payload and '"turn":"t-1"' in payload
    assert current_log_ids() == {}


def test_turn_ids_are_short_and_distinct() -> None:
    ids = {new_turn_id() for _ in range(100)}
    assert len(ids) == 100 and all(len(i) == 12 for i in ids)


def test_saturation_warns_on_loop_lag(caplog: pytest.LogCaptureFixture) -> None:
    with (
        patch.object(saturation, "snapshot", return_value={"db_checked_out": 1, "db_capacity": 30}),
        patch("app.core.saturation.sentry.report_message") as alert,
        caplog.at_level(logging.INFO, logger="app.core.saturation"),
    ):
        saturation.report(10.0)
        saturation.report(400.0)
    levels = [r.levelname for r in caplog.records]
    assert levels == ["INFO", "WARNING"]
    assert "loop_lag_max_ms=400.0" in caplog.records[-1].getMessage()
    alert.assert_called_once()


def test_saturation_warns_when_the_db_pool_is_full(caplog: pytest.LogCaptureFixture) -> None:
    with (
        patch.object(
            saturation, "snapshot", return_value={"db_checked_out": 30, "db_capacity": 30}
        ),
        patch("app.core.saturation.sentry.report_message"),
        caplog.at_level(logging.INFO, logger="app.core.saturation"),
    ):
        saturation.report(5.0)
    assert caplog.records[-1].levelname == "WARNING"


async def test_saturation_snapshot_reads_the_real_pools() -> None:
    values: dict[str, Any] = saturation.snapshot()
    assert "db_checked_out" in values and "db_capacity" in values
    assert values["db_capacity"] > 0


async def test_a_job_s_lines_name_the_job(
    fake_redis: Any, caplog: pytest.LogCaptureFixture
) -> None:
    from app.core import jobs
    from app.core.config import Settings
    from app.core.jobs import queue, worker

    async def handler(_settings: Settings, _payload: dict[str, Any]) -> None:
        logging.getLogger("app.test.job").warning("job says hi %s", current_log_ids())

    with patch.dict(queue._HANDLERS):
        jobs.register("hello-job", handler)
        await worker._ensure_group(fake_redis)
        fields = {"type": "hello-job", "payload": "{}"}
        entry_id = await fake_redis.xadd(jobs.JOBS_STREAM, fields)
        with caplog.at_level(logging.WARNING, logger="app.test.job"):
            await worker._process_entries(fake_redis, Settings(), [(entry_id, fields)])
    said = [r.getMessage() for r in caplog.records if r.name == "app.test.job"]
    assert said and "'job_type': 'hello-job'" in said[0] and entry_id in said[0]
