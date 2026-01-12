import pytest
import respx
from httpx import Response
from src.core.project_client import ProjectClient
from src.core.config import settings


@pytest.mark.asyncio
async def test_project_client_default_base_url(monkeypatch):
    """Test that ProjectClient uses the default base URL from settings."""
    monkeypatch.setattr(settings, "FEISHU_PROJECT_BASE_URL", "https://default.api")
    client = ProjectClient()
    assert str(client.client.base_url).rstrip("/") == "https://default.api"


@pytest.mark.asyncio
async def test_project_client_auth_injection(respx_mock, monkeypatch):
    """Test that ProjectClient injects auth headers via Auth flow."""
    # Patch settings
    monkeypatch.setattr(settings, "FEISHU_PROJECT_USER_TOKEN", "mock_token")
    monkeypatch.setattr(settings, "FEISHU_PROJECT_USER_KEY", "mock_user")

    client = ProjectClient(base_url="https://mock.api")

    # Mock endpoint
    route = respx_mock.get("https://mock.api/test").mock(
        return_value=Response(200, json={})
    )

    await client.get("/test")

    assert route.called
    headers = route.calls.last.request.headers
    assert headers["X-PLUGIN-TOKEN"] == "mock_token"
    assert headers["X-USER-KEY"] == "mock_user"


@pytest.mark.asyncio
async def test_project_client_post(respx_mock):
    """Test ProjectClient.post method wrapper."""
    client = ProjectClient(base_url="https://mock.api")

    # Mock endpoint
    route = respx_mock.post("https://mock.api/test/create").mock(
        return_value=Response(200, json={"data": "success"})
    )

    response = await client.post("/test/create", json={"foo": "bar"})

    assert response.status_code == 200
    assert response.json() == {"data": "success"}
    assert route.called

    # Verify request payload
    last_req = route.calls.last.request
    import json

    assert json.loads(last_req.content) == {"foo": "bar"}


@pytest.mark.asyncio
async def test_project_client_get(respx_mock):
    """Test ProjectClient.get method wrapper."""
    client = ProjectClient(base_url="https://mock.api")

    route = respx_mock.get("https://mock.api/test/query").mock(
        return_value=Response(200, json={"items": []})
    )

    response = await client.get("/test/query", params={"page": 1})

    assert response.status_code == 200
    assert route.called
    # httpx merges params into URL
    assert "page=1" in str(route.calls.last.request.url)
