import pytest
import respx
from httpx import Response
from src.core.project_client import ProjectClient, RetryableHTTPError
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


@pytest.mark.asyncio
async def test_project_client_put(respx_mock):
    """Test ProjectClient.put method wrapper."""
    client = ProjectClient(base_url="https://mock.api")

    route = respx_mock.put("https://mock.api/test/update").mock(
        return_value=Response(200, json={"updated": True})
    )

    response = await client.put("/test/update", json={"name": "new"})

    assert response.status_code == 200
    assert response.json() == {"updated": True}
    assert route.called


@pytest.mark.asyncio
async def test_project_client_delete(respx_mock):
    """Test ProjectClient.delete method wrapper."""
    client = ProjectClient(base_url="https://mock.api")

    route = respx_mock.delete("https://mock.api/test/123").mock(
        return_value=Response(204)
    )

    response = await client.delete("/test/123")

    assert response.status_code == 204
    assert route.called


class TestProjectClientRetry:
    """ProjectClient Retry 机制测试"""

    @pytest.mark.asyncio
    async def test_retry_on_500_error(self, respx_mock):
        """测试 5xx 错误触发重试"""
        client = ProjectClient(base_url="https://mock.api")

        # 第一次返回 500，第二次返回 200
        route = respx_mock.post("https://mock.api/test").mock(
            side_effect=[
                Response(500, json={"error": "Internal Server Error"}),
                Response(200, json={"success": True}),
            ]
        )

        response = await client.post("/test", json={})

        # 最终应该成功
        assert response.status_code == 200
        assert response.json() == {"success": True}

        # 应该调用了 2 次
        assert route.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises_error(self, respx_mock):
        """测试重试耗尽后抛出错误"""
        client = ProjectClient(base_url="https://mock.api")

        # 始终返回 500
        route = respx_mock.post("https://mock.api/test").mock(
            return_value=Response(500, json={"error": "Server Error"})
        )

        with pytest.raises(RetryableHTTPError):
            await client.post("/test", json={})

        # 应该重试了 3 次（MAX_RETRIES）
        assert route.call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_4xx_error(self, respx_mock):
        """测试 4xx 错误不触发重试"""
        client = ProjectClient(base_url="https://mock.api")

        route = respx_mock.post("https://mock.api/test").mock(
            return_value=Response(400, json={"error": "Bad Request"})
        )

        response = await client.post("/test", json={})

        # 4xx 不重试，直接返回
        assert response.status_code == 400
        assert route.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_503_service_unavailable(self, respx_mock):
        """测试 503 服务不可用触发重试"""
        client = ProjectClient(base_url="https://mock.api")

        route = respx_mock.get("https://mock.api/test").mock(
            side_effect=[
                Response(503, json={"error": "Service Unavailable"}),
                Response(503, json={"error": "Service Unavailable"}),
                Response(200, json={"ok": True}),
            ]
        )

        response = await client.get("/test")

        assert response.status_code == 200
        assert route.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_preserves_request_body(self, respx_mock):
        """测试重试时请求体被保留"""
        import json

        client = ProjectClient(base_url="https://mock.api")

        route = respx_mock.post("https://mock.api/test").mock(
            side_effect=[
                Response(500),
                Response(200, json={"success": True}),
            ]
        )

        await client.post("/test", json={"important": "data"})

        # 检查两次请求的 body 都是一样的
        assert route.call_count == 2
        for call in route.calls:
            body = json.loads(call.request.content)
            assert body == {"important": "data"}
