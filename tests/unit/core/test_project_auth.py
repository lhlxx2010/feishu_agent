"""Test ProjectAuth authentication header injection logic."""

import pytest
import respx
from httpx import Response, Request
from src.core.project_client import ProjectAuth
from src.core.auth import auth_manager
from src.core.config import settings


@pytest.mark.asyncio
async def test_project_auth_injects_plugin_token(respx_mock, monkeypatch):
    """Test that ProjectAuth injects X-PLUGIN-TOKEN header."""
    monkeypatch.setattr(settings, "FEISHU_PROJECT_USER_TOKEN", "test_token")
    monkeypatch.setattr(settings, "FEISHU_PROJECT_USER_KEY", None)

    auth = ProjectAuth()
    request = Request("GET", "https://test.api/endpoint")

    auth_flow = auth.async_auth_flow(request)
    try:
        result = await auth_flow.__anext__()
    except StopAsyncIteration:
        result = None

    assert result is not None
    assert "X-PLUGIN-TOKEN" in result.headers
    assert result.headers["X-PLUGIN-TOKEN"] == "test_token"


@pytest.mark.asyncio
async def test_project_auth_injects_user_key(respx_mock, monkeypatch):
    """Test that ProjectAuth injects X-USER-KEY header."""
    # 设置静态 token 以避免触发 API 调用
    monkeypatch.setattr(settings, "FEISHU_PROJECT_USER_TOKEN", "test_token")
    monkeypatch.setattr(settings, "FEISHU_PROJECT_USER_KEY", "test_user_key")

    auth = ProjectAuth()
    request = Request("GET", "https://test.api/endpoint")

    auth_flow = auth.async_auth_flow(request)
    try:
        result = await auth_flow.__anext__()
    except StopAsyncIteration:
        result = None

    assert result is not None
    assert "X-USER-KEY" in result.headers
    assert result.headers["X-USER-KEY"] == "test_user_key"


@pytest.mark.asyncio
async def test_project_auth_injects_both_headers(respx_mock, monkeypatch):
    """Test that ProjectAuth injects both X-PLUGIN-TOKEN and X-USER-KEY."""
    monkeypatch.setattr(settings, "FEISHU_PROJECT_USER_TOKEN", "test_token")
    monkeypatch.setattr(settings, "FEISHU_PROJECT_USER_KEY", "test_user_key")

    auth = ProjectAuth()
    request = Request("GET", "https://test.api/endpoint")

    auth_flow = auth.async_auth_flow(request)
    try:
        result = await auth_flow.__anext__()
    except StopAsyncIteration:
        result = None

    assert result is not None
    assert "X-PLUGIN-TOKEN" in result.headers
    assert result.headers["X-PLUGIN-TOKEN"] == "test_token"
    assert "X-USER-KEY" in result.headers
    assert result.headers["X-USER-KEY"] == "test_user_key"


@pytest.mark.asyncio
async def test_project_auth_no_token_from_auth_manager(respx_mock, monkeypatch):
    """Test that ProjectAuth raises TokenError when no token is available."""
    from src.core.project_client import TokenError

    monkeypatch.setattr(settings, "FEISHU_PROJECT_USER_TOKEN", None)
    monkeypatch.setattr(settings, "FEISHU_PROJECT_USER_KEY", None)
    monkeypatch.setattr(settings, "FEISHU_PROJECT_PLUGIN_ID", None)
    monkeypatch.setattr(settings, "FEISHU_PROJECT_PLUGIN_SECRET", None)

    auth = ProjectAuth()
    request = Request("GET", "https://test.api/endpoint")

    auth_flow = auth.async_auth_flow(request)

    # Should raise TokenError when no token is available
    with pytest.raises(TokenError) as exc_info:
        await auth_flow.__anext__()

    assert "Failed to retrieve plugin token" in str(exc_info.value)


@pytest.mark.asyncio
async def test_project_auth_preserves_existing_headers(respx_mock, monkeypatch):
    """Test that ProjectAuth preserves other existing request headers."""
    monkeypatch.setattr(settings, "FEISHU_PROJECT_USER_TOKEN", "test_token")
    monkeypatch.setattr(settings, "FEISHU_PROJECT_USER_KEY", None)

    auth = ProjectAuth()
    request = Request(
        "GET", "https://test.api/endpoint", headers={"Content-Type": "application/json"}
    )

    auth_flow = auth.async_auth_flow(request)
    try:
        result = await auth_flow.__anext__()
    except StopAsyncIteration:
        result = None

    assert result is not None
    assert "Content-Type" in result.headers
    assert result.headers["Content-Type"] == "application/json"
    assert "X-PLUGIN-TOKEN" in result.headers


@pytest.mark.asyncio
async def test_project_auth_multiple_requests(respx_mock, monkeypatch):
    """Test that ProjectAuth can handle multiple sequential requests."""
    monkeypatch.setattr(settings, "FEISHU_PROJECT_USER_TOKEN", "test_token")
    monkeypatch.setattr(settings, "FEISHU_PROJECT_USER_KEY", "test_user_key")

    auth = ProjectAuth()

    # First request
    request1 = Request("GET", "https://test.api/endpoint1")
    auth_flow1 = auth.async_auth_flow(request1)
    try:
        result1 = await auth_flow1.__anext__()
    except StopAsyncIteration:
        result1 = None

    assert result1 is not None
    assert result1.headers["X-PLUGIN-TOKEN"] == "test_token"

    # Second request
    request2 = Request("GET", "https://test.api/endpoint2")
    auth_flow2 = auth.async_auth_flow(request2)
    try:
        result2 = await auth_flow2.__anext__()
    except StopAsyncIteration:
        result2 = None

    assert result2 is not None
    assert result2.headers["X-PLUGIN-TOKEN"] == "test_token"
