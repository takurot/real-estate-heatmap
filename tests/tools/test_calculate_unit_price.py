import pytest
from unittest.mock import AsyncMock, MagicMock

from mlit_mcp.tools.calculate_unit_price import (
    CalculateUnitPriceInput,
    CalculateUnitPriceTool,
)
from mlit_mcp.http_client import FetchResult


@pytest.fixture
def mock_http_client():
    client = MagicMock()
    client.fetch = AsyncMock()
    return client


@pytest.fixture
def tool(mock_http_client):
    return CalculateUnitPriceTool(mock_http_client)


@pytest.mark.asyncio
async def test_calculate_unit_price_basic(tool, mock_http_client):
    """Test basic unit price calculation."""
    mock_data = [
        {
            "TradePrice": "100000000",  # 1億円
            "Area": "100",  # 100㎡
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "80000000",  # 8000万円
            "Area": "80",  # 80㎡
            "Type": "中古マンション等",
            "Period": "2020年第2四半期",
        },
    ]
    mock_http_client.fetch.return_value = FetchResult(
        data={"data": mock_data}, from_cache=False
    )

    input_data = CalculateUnitPriceInput(
        fromYear=2020,
        toYear=2020,
        area="13103",
    )

    result = await tool.run(input_data)

    assert result.record_count == 2
    # Each record: 100M/100=1M per sqm, 80M/80=1M per sqm -> avg = 1M
    assert result.avg_price_per_sqm == 1000000
    # 坪単価 = ㎡単価 × 3.30578
    assert result.avg_price_per_tsubo == int(1000000 * 3.30578)


@pytest.mark.asyncio
async def test_calculate_unit_price_by_type(tool, mock_http_client):
    """Test unit price calculation by property type."""
    mock_data = [
        {
            "TradePrice": "100000000",
            "Area": "100",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "50000000",
            "Area": "200",
            "Type": "宅地(土地)",  # 250,000/sqm
            "Period": "2020年第1四半期",
        },
    ]
    mock_http_client.fetch.return_value = FetchResult(
        data={"data": mock_data}, from_cache=False
    )

    input_data = CalculateUnitPriceInput(
        fromYear=2020,
        toYear=2020,
        area="13103",
    )

    result = await tool.run(input_data)

    assert "中古マンション等" in result.by_type
    assert "宅地(土地)" in result.by_type
    assert result.by_type["中古マンション等"]["avgPricePerSqm"] == 1000000
    assert result.by_type["宅地(土地)"]["avgPricePerSqm"] == 250000


@pytest.mark.asyncio
async def test_calculate_unit_price_no_area(tool, mock_http_client):
    """Test handling of records without area data."""
    mock_data = [
        {
            "TradePrice": "100000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },  # No Area field
        {
            "TradePrice": "80000000",
            "Area": "80",
            "Type": "中古マンション等",
            "Period": "2020年第2四半期",
        },
    ]
    mock_http_client.fetch.return_value = FetchResult(
        data={"data": mock_data}, from_cache=False
    )

    input_data = CalculateUnitPriceInput(
        fromYear=2020,
        toYear=2020,
        area="13103",
    )

    result = await tool.run(input_data)

    # Should only calculate for records with area
    assert result.record_count == 1
    assert result.avg_price_per_sqm == 1000000


@pytest.mark.asyncio
async def test_calculate_unit_price_empty(tool, mock_http_client):
    """Test handling of empty dataset."""
    mock_http_client.fetch.return_value = FetchResult(
        data={"data": []}, from_cache=False
    )

    input_data = CalculateUnitPriceInput(
        fromYear=2020,
        toYear=2020,
        area="13103",
    )

    result = await tool.run(input_data)

    assert result.record_count == 0
    assert result.avg_price_per_sqm is None
    assert result.avg_price_per_tsubo is None
