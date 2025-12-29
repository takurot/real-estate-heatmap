from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from mlit_mcp.cache import BinaryFileCache, InMemoryTTLCache
from mlit_mcp.http_client import MLITHttpClient


@pytest.mark.anyio
async def test_fetch_json_retries_on_retryable_status_and_caches(
    monkeypatch, tmp_path, httpx_mock: HTTPXMock
):
    monkeypatch.setenv("MLIT_API_KEY", "dummy")

    # Mocking: First 429, then 200
    httpx_mock.add_response(status_code=429, json={"detail": "rate"})
    httpx_mock.add_response(status_code=200, json={"items": [1, 2]})

    client = MLITHttpClient(
        base_url="https://example.test/",
        json_cache=InMemoryTTLCache(maxsize=4, ttl=60),
        file_cache=BinaryFileCache(tmp_path / "bin"),
    )

    # First fetch: should retry once
    result = await client.fetch("XIT001", params={"pref": "13"}, response_format="json")
    assert result.data == {"items": [1, 2]}
    assert result.from_cache is False

    # Verify requests sent
    requests = httpx_mock.get_requests()
    assert len(requests) == 2

    # Second fetch: should hit cache, no new request
    cached = await client.fetch("XIT001", params={"pref": "13"}, response_format="json")
    assert cached.from_cache is True

    # Verify no additional requests sent
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.anyio
async def test_force_refresh_issues_new_request(
    monkeypatch, tmp_path, httpx_mock: HTTPXMock
):
    monkeypatch.setenv("MLIT_API_KEY", "dummy")

    # Mocking: Two separate successful responses
    httpx_mock.add_response(status_code=200, json={"value": 1})
    httpx_mock.add_response(status_code=200, json={"value": 2})

    client = MLITHttpClient(
        base_url="https://example.test/",
        json_cache=InMemoryTTLCache(maxsize=4, ttl=60),
        file_cache=BinaryFileCache(tmp_path / "bin"),
    )

    first = await client.fetch("XIT002", params={"pref": "27"}, response_format="json")
    assert first.data == {"value": 1}
    assert first.from_cache is False

    # Second fetch with force_refresh=True
    second = await client.fetch(
        "XIT002",
        params={"pref": "27"},
        response_format="json",
        force_refresh=True,
    )
    assert second.data == {"value": 2}
    # Even if we just fetched, force_refresh makes it look like a fresh fetch
    assert second.from_cache is False

    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.anyio
async def test_fetch_geojson_uses_file_cache(
    monkeypatch, tmp_path, httpx_mock: HTTPXMock
):
    monkeypatch.setenv("MLIT_API_KEY", "dummy")

    httpx_mock.add_response(
        status_code=200, content=b'{"type":"FeatureCollection","features":[]}'
    )

    client = MLITHttpClient(
        base_url="https://example.test/",
        json_cache=InMemoryTTLCache(maxsize=4, ttl=60),
        file_cache=BinaryFileCache(tmp_path / "bin"),
    )

    result = await client.fetch(
        "XKT001", params={"pref": "01"}, response_format="geojson"
    )
    assert result.file_path is not None
    assert result.file_path.exists()
    assert result.from_cache is False

    # Second fetch: cache hit
    cached = await client.fetch(
        "XKT001", params={"pref": "01"}, response_format="geojson"
    )
    assert cached.file_path == result.file_path
    assert cached.from_cache is True

    # Only 1 request actually sent
    assert len(httpx_mock.get_requests()) == 1
