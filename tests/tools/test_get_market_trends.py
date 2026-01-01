import pytest
from unittest.mock import AsyncMock, MagicMock

from mlit_mcp.tools.get_market_trends import (
    GetMarketTrendsInput,
    GetMarketTrendsTool,
    MarketTrend,
)
from mlit_mcp.tools.summarize_transactions import SummarizeTransactionsResponse


@pytest.fixture
def mock_http_client():
    return AsyncMock()


@pytest.fixture
def tool(mock_http_client):
    return GetMarketTrendsTool(mock_http_client)


@pytest.mark.asyncio
async def test_get_market_trends_uptrend(tool, mock_http_client):
    # Mock SummarizeTransactionsTool output
    # Price increasing: 10M -> 12M -> 14.4M (20% increase each year)
    mock_summary_response = SummarizeTransactionsResponse(
        recordCount=30,
        priceByYear={
            "2020": 10000000,
            "2021": 12000000,
            "2022": 14400000,
        },
        countByYear={"2020": 10, "2021": 10, "2022": 10},
        typeDistribution={},
        meta={"cacheHit": False, "dataset": "XIT001", "source": "test"},
    )

    # Mock the internal tool run
    tool._summarize_tool.run = AsyncMock(return_value=mock_summary_response)

    input_data = GetMarketTrendsInput(
        fromYear=2020,
        toYear=2022,
        area="13103",  # Minato-ku
    )

    result = await tool.run(input_data)

    assert result.trend == MarketTrend.UPTREND
    assert result.cagr == 0.2000
    assert result.average_yoy == 0.2000
    assert len(result.yearly_data) == 3
    assert result.yearly_data[0].year == 2020
    assert result.yearly_data[0].yoy_change is None
    assert result.yearly_data[1].yoy_change == 0.2000
    assert result.yearly_data[2].yoy_change == 0.2000


@pytest.mark.asyncio
async def test_get_market_trends_downtrend(tool, mock_http_client):
    # Mock SummarizeTransactionsTool output
    # Price decreasing
    mock_summary_response = SummarizeTransactionsResponse(
        recordCount=30,
        priceByYear={
            "2020": 10000000,
            "2021": 9000000,
            "2022": 8100000,
        },
        countByYear={"2020": 10, "2021": 10, "2022": 10},
        typeDistribution={},
        meta={"cacheHit": False, "dataset": "XIT001", "source": "test"},
    )

    tool._summarize_tool.run = AsyncMock(return_value=mock_summary_response)

    input_data = GetMarketTrendsInput(fromYear=2020, toYear=2022, area="13103")
    result = await tool.run(input_data)

    assert result.trend == MarketTrend.DOWNTREND
    assert result.cagr < 0
    assert result.average_yoy < 0


@pytest.mark.asyncio
async def test_get_market_trends_flat(tool, mock_http_client):
    # Mock SummarizeTransactionsTool output
    # Price flat
    mock_summary_response = SummarizeTransactionsResponse(
        recordCount=30,
        priceByYear={
            "2020": 10000000,
            "2021": 10100000,
            "2022": 10050000,
        },
        countByYear={"2020": 10, "2021": 10, "2022": 10},
        typeDistribution={},
        meta={"cacheHit": False, "dataset": "XIT001", "source": "test"},
    )

    tool._summarize_tool.run = AsyncMock(return_value=mock_summary_response)

    input_data = GetMarketTrendsInput(fromYear=2020, toYear=2022, area="13103")
    result = await tool.run(input_data)

    assert result.trend == MarketTrend.FLAT
    # CAGR should be small (less than 3%)
    assert abs(result.cagr) < 0.03


@pytest.mark.asyncio
async def test_get_market_trends_no_data(tool, mock_http_client):
    mock_summary_response = SummarizeTransactionsResponse(
        recordCount=0,
        priceByYear={},
        countByYear={},
        typeDistribution={},
        meta={"cacheHit": False, "dataset": "XIT001", "source": "test"},
    )

    tool._summarize_tool.run = AsyncMock(return_value=mock_summary_response)

    input_data = GetMarketTrendsInput(fromYear=2020, toYear=2022, area="13103")
    result = await tool.run(input_data)

    assert result.trend == MarketTrend.UNKNOWN
    assert result.cagr is None
    assert result.average_yoy is None
    assert len(result.yearly_data) == 0
