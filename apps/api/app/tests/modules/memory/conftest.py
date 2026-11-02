from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _no_memory_areas(request: pytest.FixtureRequest):
    """Unit tests drive the workflow with mock sessions; real-DB tests keep the query."""
    if "db_session" in request.fixturenames:
        yield
        return
    with patch("app.modules.memory.repository.list_areas", AsyncMock(return_value=[])):
        yield
