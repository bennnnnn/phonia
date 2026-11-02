"""The model reader in shadow: only a sampled STEM turn reads, under the spend cap; the turn's
trace line says how its read compares, and a read still running when the line is written
logs its own line when it finishes (docs/MODEL_READER.md)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.gateways import structured_completion
from app.modules.chat.turn_prep.model_read_shadow import start_model_read_shadow
from app.modules.chat.turn_trace import begin_turn_trace, emit_turn_trace, plain_record, turn_record
from app.modules.model_reader.schemas import GivenRead, LawRead, RouteRead
from app.services import quota as quota_service

_SPEED = "A car travels 120 m in 8 s. What is its average speed?"
_ON: dict[str, Any] = {"model_reader_shadow_enabled": True, "model_reader_shadow_rate": 1.0}


def _replies(replies: list[BaseModel]) -> Any:
    async def complete_structured(**_kwargs: Any) -> BaseModel:
        return replies.pop(0)

    return complete_structured


def _speed_reads() -> list[BaseModel]:
    return [
        RouteRead(subject="physics", kind="kinematics"),
        LawRead(
            op="rate_speed",
            givens=[
                GivenRead(name="d", value=120, unit="m", quote="120 m"),
                GivenRead(name="t", value=8, unit="s", quote="8 s"),
            ],
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("settings", "subject"),
    [
        ({}, "physics"),  # off by default
        (_ON, None),  # not a STEM turn: a greeting, a money question
        ({**_ON, "model_reader_shadow_rate": 0.0}, "physics"),  # not sampled
    ],
)
async def test_no_read_and_no_field(
    fake_redis: Any, settings: dict[str, Any], subject: str | None
) -> None:
    trace = begin_turn_trace("new")
    start_model_read_shadow(_SPEED, Settings(**settings), fake_redis, subject=subject)
    assert trace.model_read_task is None
    assert "model_read" not in turn_record(trace, None, outcome=None)


@pytest.mark.asyncio
async def test_a_finished_read_is_compared_in_the_line(
    monkeypatch: pytest.MonkeyPatch, fake_redis: Any, thread_sympy_executor: None
) -> None:
    monkeypatch.setattr(structured_completion, "complete_structured", _replies(_speed_reads()))
    trace = begin_turn_trace("new")
    start_model_read_shadow(_SPEED, Settings(**_ON), fake_redis, subject="physics")
    await trace.model_read_task
    record = turn_record(trace, None, outcome=None)
    shown = record["model_read"]
    assert shown["verdict"] == "model_only"
    assert (shown["subject"], shown["op"], shown["reason"]) == ("physics", "rate_speed", "ok")
    assert plain_record(record)
    # Only identifiers and numbers: the message never reaches the line.
    assert "120 m" not in str(record) and "car" not in str(record)


@pytest.mark.asyncio
async def test_at_the_spend_cap_nothing_is_read(
    monkeypatch: pytest.MonkeyPatch, fake_redis: Any
) -> None:
    calls: list[str] = []

    async def capped(_redis: Any, _settings: Settings) -> bool:
        return True

    async def never(**_kwargs: Any) -> None:
        calls.append("called")

    monkeypatch.setattr(quota_service, "global_spend_exceeded", capped)
    monkeypatch.setattr(structured_completion, "complete_structured", never)
    trace = begin_turn_trace("new")
    start_model_read_shadow(_SPEED, Settings(**_ON), fake_redis, subject="physics")
    await trace.model_read_task
    assert calls == [] and trace.model_read is None


@pytest.mark.asyncio
async def test_a_read_that_outlives_the_turn_logs_its_own_line(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, fake_redis: Any
) -> None:
    release = asyncio.Event()
    reads: list[BaseModel] = [RouteRead(subject="none")]

    async def slow(**_kwargs: Any) -> BaseModel:
        await release.wait()
        return reads.pop(0)

    monkeypatch.setattr(structured_completion, "complete_structured", slow)
    trace = begin_turn_trace("new")
    start_model_read_shadow(_SPEED, Settings(**_ON), fake_redis, subject="physics")
    with caplog.at_level(logging.INFO, logger="app.modules.chat.turn_trace"):
        emit_turn_trace(None, outcome=None)
        assert '"model_read":{"verdict":"pending"}' in caplog.text
        release.set()
        await trace.model_read_task
        await asyncio.sleep(0)
    late = [
        record for record in caplog.records if record.getMessage().startswith("turn_model_read")
    ]
    assert len(late) == 1
    assert '"verdict":"neither"' in late[0].getMessage()
    assert '"reason":"not_subject"' in late[0].getMessage()
