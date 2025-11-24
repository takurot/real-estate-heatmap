import pytest
from fastapi.testclient import TestClient

from mlit_mcp.http_client import FetchResult


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MLIT_API_KEY", "dummy-key")
    from mlit_mcp.server import app

    with TestClient(app) as test_client:
        yield test_client


def test_list_tools_endpoint_returns_registered_tool(client):
    response = client.post("/list_tools", json={})
    assert response.status_code == 200
    tools = response.json()["tools"]
    assert any(tool["name"] == "mlit.list_municipalities" for tool in tools)


def test_call_tool_endpoint_requires_name(client):
    response = client.post("/call_tool", json={"arguments": {}})
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "toolName is required"


def test_call_tool_executes_list_municipalities(client, monkeypatch):
    async def fake_fetch(self, endpoint, *, params, response_format, force_refresh=False):
        assert endpoint == "XIT002"
        assert params["area"] == "13"
        assert response_format == "json"
        return FetchResult(
            data={"data": [{"cityCode": "13101", "cityName": "千代田区"}]},
            from_cache=False,
        )

    monkeypatch.setattr("mlit_mcp.http_client.MLITHttpClient.fetch", fake_fetch, raising=True)

    response = client.post(
        "/call_tool",
        json={"toolName": "mlit.list_municipalities", "arguments": {"prefectureCode": "13"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["prefectureCode"] == "13"
    assert payload["data"]["municipalities"][0]["code"] == "13101"

