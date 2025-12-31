import pytest
from unittest.mock import AsyncMock, MagicMock
from mlit_mcp.tools.fetch_transactions import (
    FetchTransactionsTool,
    FetchTransactionsInput,
)
from mlit_mcp.http_client import FetchResult


@pytest.fixture
def mock_http_client():
    client = MagicMock()
    client.fetch = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_fetch_transactions_run_with_prefecture(mock_http_client):
    # Mock response data for two separate years
    mock_http_client.fetch.side_effect = [
        FetchResult(data={"data": [{"id": 1, "year": 2015}]}, from_cache=False),
        FetchResult(data={"data": [{"id": 2, "year": 2016}]}, from_cache=False),
    ]
    tool = FetchTransactionsTool(mock_http_client)
    input_data = FetchTransactionsInput(
        fromYear=2015,
        toYear=2016,
        area="13",  # Tokyo
    )

    result = await tool.run(input_data)

    # Verify calls
    assert mock_http_client.fetch.call_count == 2

    # Check first call args
    call1_args = mock_http_client.fetch.call_args_list[0]
    assert call1_args[0][0] == "XIT001"
    assert call1_args[1]["params"]["area"] == "13"
    assert call1_args[1]["params"]["year"] == "2015"
    assert "city" not in call1_args[1]["params"]

    # Check result aggregation
    assert len(result.data) == 2
    assert result.data[0]["id"] == 1
    assert result.data[1]["id"] == 2
    assert result.meta.dataset == "XIT001"


@pytest.mark.asyncio
async def test_fetch_transactions_run_with_city(mock_http_client):
    mock_http_client.fetch.return_value = FetchResult(
        data={"data": [{"id": 1}]}, from_cache=False
    )

    tool = FetchTransactionsTool(mock_http_client)
    input_data = FetchTransactionsInput(
        fromYear=2020,
        toYear=2020,
        area="13101",  # Chiyoda-ku
    )

    await tool.run(input_data)

    call_args = mock_http_client.fetch.call_args
    assert call_args[1]["params"]["city"] == "13101"
    assert "area" not in call_args[1]["params"]


@pytest.mark.asyncio
async def test_fetch_transactions_validation_error():
    with pytest.raises(ValueError, match="Area code must be 2 digits"):
        FetchTransactionsInput(
            fromYear=2020,
            toYear=2020,
            area="123",  # Invalid
        )

    with pytest.raises(ValueError, match="toYear .* must be >= fromYear"):
        FetchTransactionsInput(
            fromYear=2020,
            toYear=2019,
            area="13",
        )


@pytest.mark.asyncio
async def test_fetch_transactions_large_response(mock_http_client):
    # Mock a "large" response
    large_data = [{"id": i} for i in range(1000)]
    mock_http_client.fetch.return_value = FetchResult(
        data={"data": large_data}, from_cache=False
    )

    # Mock save_to_cache
    from pathlib import Path

    mock_http_client.save_to_cache.return_value = Path("/tmp/cache/large_file.json")

    tool = FetchTransactionsTool(mock_http_client)

    # Patch threshold to force resource URI
    import mlit_mcp.tools.fetch_transactions as mod

    original_threshold = mod.RESOURCE_THRESHOLD_BYTES
    mod.RESOURCE_THRESHOLD_BYTES = 10  # Very small threshold

    try:
        input_data = FetchTransactionsInput(
            from_year=2020,
            to_year=2020,
            area="13",
        )
        result = await tool.run(input_data)

        # Verify resource URI returned
        assert result.resource_uri == "resource://mlit/transactions/large_file.json"
        assert result.data is None

        # Verify save_to_cache called
        mock_http_client.save_to_cache.assert_called_once()
        args = mock_http_client.save_to_cache.call_args
        assert args[0][0].startswith("transactions:XIT001:13:2020-2020")

    finally:
        mod.RESOURCE_THRESHOLD_BYTES = original_threshold
