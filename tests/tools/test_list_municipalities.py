import httpx
import pytest
from pydantic import ValidationError

from mlit_mcp.cache import BinaryFileCache, InMemoryTTLCache
from mlit_mcp.http_client import MLITHttpClient


@pytest.fixture
def http_client(monkeypatch, tmp_path):
    monkeypatch.setenv("MLIT_API_KEY", "dummy-key")

    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(
            status_code=200,
            json={
                "data": [
                    {"id": "13101", "name": "千代田区"},
                    {"MunicipalityCode": "13102", "Municipality": "中央区"},
                ]
            },
        )

    client = MLITHttpClient(
        base_url="https://example.test/",
        json_cache=InMemoryTTLCache(maxsize=4, ttl=60),
        file_cache=BinaryFileCache(tmp_path / "bin"),
        transport=httpx.MockTransport(handler),
    )
    client._call_count = calls  # type: ignore[attr-defined]
    return client


@pytest.mark.anyio
async def test_tool_fetches_and_formats_result(http_client):
    from mlit_mcp.tools.list_municipalities import (
        ListMunicipalitiesInput,
        ListMunicipalitiesTool,
    )

    tool = ListMunicipalitiesTool(http_client=http_client)
    payload = ListMunicipalitiesInput(prefecture_code="13")

    result = await tool.run(payload)
    assert result.prefecture_code == "13"
    assert len(result.municipalities) == 2
    assert result.municipalities[0].code == "13101"
    assert result.meta.cache_hit is False

    cached = await tool.run(payload)
    assert cached.meta.cache_hit is True
    assert http_client._call_count["count"] == 1  # type: ignore[attr-defined]


def test_input_validation_rejects_invalid_prefecture_code():
    from mlit_mcp.tools.list_municipalities import ListMunicipalitiesInput

    with pytest.raises(ValidationError):
        ListMunicipalitiesInput(prefecture_code="1")


@pytest.mark.anyio
async def test_force_refresh_bypasses_cache(http_client):
    from mlit_mcp.tools.list_municipalities import (
        ListMunicipalitiesInput,
        ListMunicipalitiesTool,
    )

    tool = ListMunicipalitiesTool(http_client=http_client)
    payload = ListMunicipalitiesInput(prefecture_code="13")

    # First call - cache miss
    await tool.run(payload)
    assert http_client._call_count["count"] == 1

    # Second call - cache hit
    await tool.run(payload)
    assert http_client._call_count["count"] == 1  # Should still be 1

    # Third call with force_refresh - cache miss (bypass)
    # Note: We need to update Input model to support force_refresh first,
    # but for now we try to pass it to see it fail or if we need to modify input first.
    # Since current Input doesn't have it, we should probably update Input test too.
    # But let's assume we want to support it in Input.

    # If I try to pass force_refresh to Input now, it will raise ValidationError (extra forbidden).
    # So I cannot even write this test without modifying the Input model definition in the test or main code.
    # But TDD says write failing test. The test will fail at Input construction.

    payload_force = ListMunicipalitiesInput(prefecture_code="13", force_refresh=True)
    await tool.run(payload_force)
    assert http_client._call_count["count"] == 2
