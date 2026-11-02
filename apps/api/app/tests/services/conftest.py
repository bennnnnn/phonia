"""Fixtures shared by service tests."""

import pytest

from app.gateways.mcp import registry as mcp_registry
from app.modules.web_search import WebSearchAdapter
from app.tests.services.tool_loop_support import settings


@pytest.fixture
def web_search_registered():
    mcp_registry.clear()
    mcp_registry.register(WebSearchAdapter(settings()))
    yield
    mcp_registry.clear()


@pytest.fixture
def sympy_registered(web_search_registered):
    """web_search and sympy, for tests whose model calls sympy (only offered tools run)."""
    from app.modules.math.tool import SympyAdapter

    mcp_registry.register(SympyAdapter(settings()))
    yield
