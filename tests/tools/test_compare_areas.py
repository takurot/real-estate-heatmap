import pytest
from unittest.mock import AsyncMock

from mlit_mcp.tools.compare_areas import (
    CompareAreasInput,
    CompareAreasTool,
)
from mlit_mcp.tools.summarize_transactions import SummarizeTransactionsResponse


@pytest.fixture
def mock_http_client():
    return AsyncMock()


@pytest.fixture
def tool(mock_http_client):
    return CompareAreasTool(mock_http_client)


def create_mock_summary(area: str, avg_price: int, count: int):
    """Helper to create mock summary response."""
    return SummarizeTransactionsResponse(
        recordCount=count,
        averagePrice=avg_price,
        medianPrice=avg_price,
        minPrice=int(avg_price * 0.8),
        maxPrice=int(avg_price * 1.2),
        priceByYear={"2020": avg_price, "2021": int(avg_price * 1.05)},
        countByYear={"2020": count // 2, "2021": count // 2},
        typeDistribution={"中古マンション等": count},
        meta={"cacheHit": False, "dataset": "XIT001", "source": "test"},
    )


@pytest.mark.asyncio
async def test_compare_areas_basic(tool, mock_http_client):
    """Test basic comparison of two areas."""
    # Mock summarize responses for two areas
    mock_summaries = [
        create_mock_summary("13101", 80000000, 100),  # Cheaper area
        create_mock_summary("13103", 120000000, 150),  # More expensive area
    ]

    # Create async mock for summarize tool
    tool._summarize_tool.run = AsyncMock(side_effect=mock_summaries)

    input_data = CompareAreasInput(
        areas=["13101", "13103"],
        fromYear=2020,
        toYear=2021,
    )

    result = await tool.run(input_data)

    assert len(result.area_stats) == 2
    assert result.area_stats[0].area == "13101"
    assert result.area_stats[1].area == "13103"

    # Check ranking (by price, descending)
    assert result.ranking_by_price[0] == "13103"  # Most expensive first
    assert result.ranking_by_price[1] == "13101"

    # Check ranking by transaction count
    assert result.ranking_by_count[0] == "13103"  # Most transactions first


@pytest.mark.asyncio
async def test_compare_areas_single_area(tool, mock_http_client):
    """Test with a single area."""
    mock_summary = create_mock_summary("13101", 80000000, 100)
    tool._summarize_tool.run = AsyncMock(return_value=mock_summary)

    input_data = CompareAreasInput(
        areas=["13101"],
        fromYear=2020,
        toYear=2021,
    )

    result = await tool.run(input_data)

    assert len(result.area_stats) == 1
    assert result.ranking_by_price == ["13101"]


@pytest.mark.asyncio
async def test_compare_areas_three_areas(tool, mock_http_client):
    """Test comparison of three areas."""
    mock_summaries = [
        create_mock_summary("13101", 60000000, 80),
        create_mock_summary("13102", 100000000, 120),
        create_mock_summary("13103", 80000000, 100),
    ]
    tool._summarize_tool.run = AsyncMock(side_effect=mock_summaries)

    input_data = CompareAreasInput(
        areas=["13101", "13102", "13103"],
        fromYear=2020,
        toYear=2021,
    )

    result = await tool.run(input_data)

    assert len(result.area_stats) == 3
    # Price ranking: 13102 (100M) > 13103 (80M) > 13101 (60M)
    assert result.ranking_by_price == ["13102", "13103", "13101"]


@pytest.mark.asyncio
async def test_compare_areas_empty_data(tool, mock_http_client):
    """Test with area that has no data."""
    mock_summaries = [
        create_mock_summary("13101", 80000000, 100),
        SummarizeTransactionsResponse(
            recordCount=0,
            priceByYear={},
            countByYear={},
            typeDistribution={},
            meta={"cacheHit": False, "dataset": "XIT001", "source": "test"},
        ),
    ]
    tool._summarize_tool.run = AsyncMock(side_effect=mock_summaries)

    input_data = CompareAreasInput(
        areas=["13101", "13102"],
        fromYear=2020,
        toYear=2021,
    )

    result = await tool.run(input_data)

    # Should still include both areas
    assert len(result.area_stats) == 2
    # Only valid area in ranking
    assert "13101" in result.ranking_by_price
