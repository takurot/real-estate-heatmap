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
    assert call1_args[1]["params"]["year"] == 2015
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
