import pytest
import respx
from httpx import Response
from src.core.auth import AuthManager
from src.core.config import settings


@pytest.mark.asyncio
async def test_auth_manager_static_token(monkeypatch):
    """Test using static token from settings."""
    monkeypatch.setattr(settings, "FEISHU_PROJECT_USER_TOKEN", "static_token")
    manager = AuthManager()
    token = await manager.get_plugin_token()
    assert token == "static_token"


@pytest.mark.asyncio
async def test_auth_manager_fetch_token(respx_mock, monkeypatch):
    """Test fetching token from API."""
    monkeypatch.setattr(settings, "FEISHU_PROJECT_USER_TOKEN", None)
    monkeypatch.setattr(settings, "FEISHU_PROJECT_PLUGIN_ID", "pid")
    monkeypatch.setattr(settings, "FEISHU_PROJECT_PLUGIN_SECRET", "psec")

    mock_resp = {"code": 0, "data": {"plugin_token": "fetched_token", "expire": 7200}}
    respx_mock.post("https://project.feishu.cn/open_api/authen/plugin_token").mock(
        return_value=Response(200, json=mock_resp)
    )

    manager = AuthManager()
    token = await manager.get_plugin_token()
    assert token == "fetched_token"
    assert manager._plugin_token == "fetched_token"


@pytest.mark.asyncio
async def test_auth_manager_caching(respx_mock, monkeypatch):
    """Test token caching."""
    monkeypatch.setattr(settings, "FEISHU_PROJECT_USER_TOKEN", None)
    monkeypatch.setattr(settings, "FEISHU_PROJECT_PLUGIN_ID", "pid")
    monkeypatch.setattr(settings, "FEISHU_PROJECT_PLUGIN_SECRET", "psec")

    route = respx_mock.post(
        "https://project.feishu.cn/open_api/authen/plugin_token"
    ).mock(
        return_value=Response(
            200, json={"code": 0, "data": {"plugin_token": "t1", "expire": 3600}}
        )
    )

    manager = AuthManager()
    await manager.get_plugin_token()
    await manager.get_plugin_token()

    # Should only call API once
    assert route.call_count == 1
