"""Tests for compare_market_to_land_price tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from mlit_mcp.tools.compare_market_to_land_price import (
    CompareMarketToLandPriceInput,
    CompareMarketToLandPriceResponse,
    CompareMarketToLandPriceTool,
)


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    client = MagicMock()
    client.fetch = AsyncMock()
    return client


@pytest.fixture
def tool(mock_http_client):
    """Create a CompareMarketToLandPriceTool instance."""
    return CompareMarketToLandPriceTool(http_client=mock_http_client)


class TestCompareMarketToLandPriceInput:
    """Tests for input validation."""

    def test_valid_input(self):
        """Test valid input parameters."""
        input_data = CompareMarketToLandPriceInput(
            latitude=35.6812,
            longitude=139.7671,
            year=2023,
        )
        assert input_data.latitude == 35.6812
        assert input_data.year == 2023


class TestCompareMarketToLandPriceTool:
    """Tests for the CompareMarketToLandPriceTool."""

    @pytest.mark.asyncio
    async def test_compare_prices(self, tool, mock_http_client):
        """Test comparing market and land prices."""
        mock_http_client.fetch.side_effect = [
            # First call: land price data
            MagicMock(
                data={
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {
                                "u_current_years_price_ja": "500000",
                            },
                        }
                    ],
                },
                file_path=None,
            ),
            # Second call: transaction data
            MagicMock(
                data={
                    "status": "OK",
                    "data": [
                        {"TradePrice": "550000", "UnitPrice": "600000"},
                    ],
                },
                file_path=None,
            ),
        ]

        input_data = CompareMarketToLandPriceInput(
            latitude=35.6812,
            longitude=139.7671,
            year=2023,
        )
        result = await tool.run(input_data)

        assert isinstance(result, CompareMarketToLandPriceResponse)

    def test_descriptor(self, tool):
        """Test tool descriptor."""
        descriptor = tool.descriptor()
        assert descriptor["name"] == "mlit.compare_market_to_land_price"
        assert "description" in descriptor
