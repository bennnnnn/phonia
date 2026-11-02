import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app


@pytest.mark.asyncio
async def test_dev_auth_disabled(monkeypatch: pytest.MonkeyPatch):
    # The cached settings are the process's; monkeypatch puts the flag back even when
    # the request raises.
    monkeypatch.setattr(get_settings(), "dev_auth_enabled", False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/auth/dev", json={"email": "x@y.z", "name": "X"})
    assert response.status_code == 403
