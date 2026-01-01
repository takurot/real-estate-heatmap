import pytest
from unittest.mock import AsyncMock, MagicMock

from mlit_mcp.tools.detect_outliers import (
    DetectOutliersInput,
    DetectOutliersTool,
    OutlierMethod,
)
from mlit_mcp.http_client import FetchResult


@pytest.fixture
def mock_http_client():
    client = MagicMock()
    client.fetch = AsyncMock()
    return client


@pytest.fixture
def tool(mock_http_client):
    return DetectOutliersTool(mock_http_client)


@pytest.mark.asyncio
async def test_detect_outliers_iqr_basic(tool, mock_http_client):
    """Test IQR-based outlier detection."""
    # Need enough data points for proper IQR calculation
    # Normal prices around 100M, one extreme outlier at 1B
    mock_data = [
        {
            "TradePrice": "80000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "85000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "90000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "95000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "100000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "105000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "110000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "115000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "120000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "1000000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
    ]
    mock_http_client.fetch.return_value = FetchResult(
        data={"data": mock_data}, from_cache=False
    )

    input_data = DetectOutliersInput(
        fromYear=2020,
        toYear=2020,
        area="13103",
        method=OutlierMethod.IQR,
    )

    result = await tool.run(input_data)

    assert result.total_count == 10
    assert result.outlier_count >= 1  # At least the 1B should be detected
    assert len(result.outliers) >= 1
    # Check one of the outliers is the 1B
    outlier_prices = [o.price for o in result.outliers]
    assert 1000000000 in outlier_prices


@pytest.mark.asyncio
async def test_detect_outliers_zscore(tool, mock_http_client):
    """Test Z-score based outlier detection."""
    # Normal prices around 100M, extreme outlier
    mock_data = [
        {
            "TradePrice": "100000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "102000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "98000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "101000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "99000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "1000000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
    ]
    mock_http_client.fetch.return_value = FetchResult(
        data={"data": mock_data}, from_cache=False
    )

    input_data = DetectOutliersInput(
        fromYear=2020,
        toYear=2020,
        area="13103",
        method=OutlierMethod.ZSCORE,
        threshold=2.0,
    )

    result = await tool.run(input_data)

    assert result.total_count == 6
    assert result.outlier_count >= 1


@pytest.mark.asyncio
async def test_detect_outliers_no_outliers(tool, mock_http_client):
    """Test with data that has no outliers."""
    mock_data = [
        {
            "TradePrice": "100000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "102000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "98000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "101000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
    ]
    mock_http_client.fetch.return_value = FetchResult(
        data={"data": mock_data}, from_cache=False
    )

    input_data = DetectOutliersInput(
        fromYear=2020,
        toYear=2020,
        area="13103",
        method=OutlierMethod.IQR,
    )

    result = await tool.run(input_data)

    assert result.total_count == 4
    assert result.outlier_count == 0


@pytest.mark.asyncio
async def test_detect_outliers_empty(tool, mock_http_client):
    """Test handling of empty dataset."""
    mock_http_client.fetch.return_value = FetchResult(
        data={"data": []}, from_cache=False
    )

    input_data = DetectOutliersInput(
        fromYear=2020,
        toYear=2020,
        area="13103",
    )

    result = await tool.run(input_data)

    assert result.total_count == 0
    assert result.outlier_count == 0


@pytest.mark.asyncio
async def test_detect_outliers_stats_after_exclusion(tool, mock_http_client):
    """Test that stats after exclusion are correctly calculated."""
    # Need enough data for proper IQR calculation (at least 4 points)
    mock_data = [
        {
            "TradePrice": "100000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "102000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "98000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "101000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "99000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "103000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "97000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "104000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
        {
            "TradePrice": "1000000000",
            "Type": "中古マンション等",
            "Period": "2020年第1四半期",
        },
    ]
    mock_http_client.fetch.return_value = FetchResult(
        data={"data": mock_data}, from_cache=False
    )

    input_data = DetectOutliersInput(
        fromYear=2020,
        toYear=2020,
        area="13103",
        method=OutlierMethod.IQR,
    )

    result = await tool.run(input_data)

    # Should detect the 1B as outlier
    assert result.outlier_count >= 1
    # After excluding outliers, average should be around 100M
    if result.avg_after_exclusion:
        assert result.avg_after_exclusion < 200000000
