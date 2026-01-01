import pytest
from unittest.mock import AsyncMock, MagicMock

from mlit_mcp.tools.get_price_distribution import (
    GetPriceDistributionInput,
    GetPriceDistributionTool,
)
from mlit_mcp.http_client import FetchResult


@pytest.fixture
def mock_http_client():
    client = MagicMock()
    client.fetch = AsyncMock()
    return client


@pytest.fixture
def tool(mock_http_client):
    return GetPriceDistributionTool(mock_http_client)


@pytest.mark.asyncio
async def test_get_price_distribution_basic(tool, mock_http_client):
    """Test basic price distribution generation."""
    # Create test data with known distribution
    # 5 items: 10M, 20M, 30M, 40M, 50M
    mock_data = [
        {"TradePrice": "10000000"},
        {"TradePrice": "20000000"},
        {"TradePrice": "30000000"},
        {"TradePrice": "40000000"},
        {"TradePrice": "50000000"},
    ]
    mock_http_client.fetch.return_value = FetchResult(
        data={"data": mock_data}, from_cache=False
    )

    input_data = GetPriceDistributionInput(
        fromYear=2020,
        toYear=2020,
        area="13103",
        numBins=5,
    )

    result = await tool.run(input_data)

    assert result.total_count == 5
    assert result.min_price == 10000000
    assert result.max_price == 50000000
    assert len(result.bins) == 5

    # Each bin should have exactly 1 item
    for bin_item in result.bins:
        assert bin_item.count == 1

    assert result.bins[-1].cumulative_percent == 100.0


@pytest.mark.asyncio
async def test_get_price_distribution_percentiles(tool, mock_http_client):
    """Test that percentiles are correctly calculated."""
    # 100 items from 1M to 100M to check percentiles
    mock_data = [{"TradePrice": str(i * 1000000)} for i in range(1, 101)]
    mock_http_client.fetch.return_value = FetchResult(
        data={"data": mock_data}, from_cache=False
    )

    input_data = GetPriceDistributionInput(
        fromYear=2020,
        toYear=2020,
        area="13103",
        numBins=10,
    )

    result = await tool.run(input_data)

    # 25th percentile of 1..100 is ~25
    # median is ~50
    # 75th is ~75
    assert 24000000 <= result.percentile_25 <= 26000000
    assert 49000000 <= result.percentile_50 <= 51000000
    assert 74000000 <= result.percentile_75 <= 76000000


@pytest.mark.asyncio
async def test_get_price_distribution_skewed(tool, mock_http_client):
    """Test skewed distribution."""
    # 4 items at 10M, 1 item at 100M
    mock_data = [
        {"TradePrice": "10000000"},
        {"TradePrice": "10000000"},
        {"TradePrice": "10000000"},
        {"TradePrice": "10000000"},
        {"TradePrice": "100000000"},
    ]
    mock_http_client.fetch.return_value = FetchResult(
        data={"data": mock_data}, from_cache=False
    )

    input_data = GetPriceDistributionInput(
        fromYear=2020,
        toYear=2020,
        area="13103",
        numBins=2,
    )

    result = await tool.run(input_data)

    # Range 10M-100M. Range=90M. Bin size=45M.
    # Bin 1: 10M-55M. Should have 4 items.
    # Bin 2: 55M-100M. Should have 1 item.
    assert result.bins[0].count == 4
    assert result.bins[1].count == 1


@pytest.mark.asyncio
async def test_get_price_distribution_empty(tool, mock_http_client):
    """Test handling of empty dataset."""
    mock_http_client.fetch.return_value = FetchResult(
        data={"data": []}, from_cache=False
    )

    input_data = GetPriceDistributionInput(
        fromYear=2020,
        toYear=2020,
        area="13103",
    )

    result = await tool.run(input_data)

    assert result.total_count == 0
    assert len(result.bins) == 0
