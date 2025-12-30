import pytest
from fastapi.testclient import TestClient
from mlit_mcp.http_client import FetchResult


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MLIT_API_KEY", "dummy-key")
    from mlit_mcp.server import app

    with TestClient(app) as test_client:
        yield test_client


def test_full_server_flow(client, monkeypatch):
    # Mocking different endpoints for the flow
    async def fake_fetch(
        self, endpoint, *, params, response_format, force_refresh=False
    ):
        if endpoint == "XIT002":  # Municipalities
            return FetchResult(
                data={"data": [{"cityCode": "13101", "cityName": "千代田区"}]},
                from_cache=False,
            )
        elif endpoint == "XIT001":  # Transactions
            return FetchResult(
                data={"data": [{"price": 100000}]},
                from_cache=False,
            )
        elif endpoint == "XPT001":  # Transaction Points
            return FetchResult(
                # Emulate content stored in cache file later
                data={"type": "FeatureCollection", "features": []},
                from_cache=False,
                resource_uri="resource://mlit/transaction_points/test_resource.geojson",
            )
        else:
            return FetchResult(data={}, from_cache=False)

    monkeypatch.setattr(
        "mlit_mcp.http_client.MLITHttpClient.fetch", fake_fetch, raising=True
    )

    # 1. Get City Code
    resp_mun = client.post(
        "/call_tool",
        json={
            "toolName": "mlit.list_municipalities",
            "arguments": {"prefectureCode": "13"},
        },
    )
    assert resp_mun.status_code == 200
    assert resp_mun.json()["data"]["municipalities"][0]["code"] == "13101"

    # 2. Get Transaction Data
    resp_tx = client.post(
        "/call_tool",
        json={
            "toolName": "mlit.fetch_transactions",
            "arguments": {
                "fromYear": 2020,
                "toYear": 2020,
                "area": "13101",
            },
        },
    )
    assert resp_tx.status_code == 200
    assert resp_tx.json()["data"]["data"][0]["price"] == 100000

    # 3. Get Resource URI from Point Data
    # To test resource URI, we need to return a file_path and ensure it's treated as large.
    # We patch RESOURCE_THRESHOLD_BYTES to 0 so any file is "large".

    # Create a dummy file
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(delete=False, suffix=".geojson") as tmp:
        tmp.write(b'{"type": "FeatureCollection", "features": []}')
        tmp_path = Path(tmp.name)

    # Store original fetch to restore or just rely on monkeypatch context

    async def fake_fetch_with_file(
        self, endpoint, *, params, response_format, force_refresh=False
    ):
        if endpoint == "XPT001":
            return FetchResult(file_path=tmp_path, from_cache=False)
        return await fake_fetch(
            self, endpoint, params=params, response_format=response_format
        )

    monkeypatch.setattr(
        "mlit_mcp.http_client.MLITHttpClient.fetch", fake_fetch_with_file
    )
    monkeypatch.setattr(
        "mlit_mcp.tools.fetch_transaction_points.RESOURCE_THRESHOLD_BYTES", 0
    )

    try:
        resp_pt = client.post(
            "/call_tool",
            json={
                "toolName": "mlit.fetch_transaction_points",
                "arguments": {
                    "z": 13,
                    "x": 7277,
                    "y": 3226,
                    "fromQuarter": "20201",
                    "toQuarter": "20204",
                    "responseFormat": "geojson",
                },
            },
        )
        assert resp_pt.status_code == 200
        uri = resp_pt.json()["data"]["resourceUri"]
        assert "resource://mlit/transaction_points/" in uri
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
