"""Tests for the shared pooled httpx.AsyncClient helper."""

import pytest

from app.gateways import http_client


@pytest.fixture(autouse=True)
async def _reset_pooled_clients():
    await http_client.aclose_pooled_clients()
    yield
    await http_client.aclose_pooled_clients()


def test_get_pooled_client_reuses_same_instance_for_same_timeout():
    first = http_client.get_pooled_client(12.0)
    second = http_client.get_pooled_client(12.0)
    assert first is second


def test_get_pooled_client_creates_separate_instances_per_timeout():
    short = http_client.get_pooled_client(5.0)
    long = http_client.get_pooled_client(15.0)
    assert short is not long


def test_get_pooled_client_recreates_after_close():
    client = http_client.get_pooled_client(9.0)
    assert http_client.get_pooled_client(9.0) is client


@pytest.mark.asyncio
async def test_aclose_pooled_clients_closes_and_clears():
    client = http_client.get_pooled_client(7.0)
    await http_client.aclose_pooled_clients()
    assert client.is_closed
    # A fresh client is created on next use, not the closed one.
    assert http_client.get_pooled_client(7.0) is not client
