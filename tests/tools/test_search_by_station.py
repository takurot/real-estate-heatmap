"""Tests for search_by_station tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from mlit_mcp.tools.search_by_station import (
    SearchByStationInput,
    SearchByStationResponse,
    SearchByStationTool,
)


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    client = MagicMock()
    client.fetch = AsyncMock()
    return client


@pytest.fixture
def tool(mock_http_client):
    """Create a SearchByStationTool instance."""
    return SearchByStationTool(http_client=mock_http_client)


class TestSearchByStationInput:
    """Tests for input validation."""

    def test_valid_input(self):
        """Test valid input parameters."""
        input_data = SearchByStationInput(
            stationName="東京",
            fromYear=2020,
            toYear=2023,
        )
        assert input_data.station_name == "東京"
        assert input_data.from_year == 2020
        assert input_data.to_year == 2023

    def test_default_years(self):
        """Test default year range."""
        input_data = SearchByStationInput(stationName="渋谷")
        assert input_data.from_year == 2020
        assert input_data.to_year == 2024


class TestSearchByStationTool:
    """Tests for the SearchByStationTool."""

    @pytest.mark.asyncio
    async def test_search_transactions(self, tool, mock_http_client):
        """Test searching transactions by station name."""
        # Mock station search response
        mock_http_client.fetch.side_effect = [
            # First call: station search
            MagicMock(
                data={
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {
                                "S12_001_ja": "東京駅",
                            },
                            "geometry": {
                                "type": "Point",
                                "coordinates": [139.7671, 35.6812],
                            },
                        }
                    ],
                },
                file_path=None,
            ),
            # Second call: transaction search
            MagicMock(
                data={
                    "status": "OK",
                    "data": [
                        {
                            "PriceCategory": "宅地(土地)",
                            "TradePrice": "100000000",
                            "Area": "100",
                            "Prefecture": "東京都",
                            "Municipality": "千代田区",
                        }
                    ],
                },
                file_path=None,
            ),
        ]

        input_data = SearchByStationInput(
            stationName="東京",
            fromYear=2020,
            toYear=2023,
        )
        result = await tool.run(input_data)

        assert isinstance(result, SearchByStationResponse)
        assert result.station_name == "東京"
        assert len(result.transactions) > 0 or result.station_coords is not None

    @pytest.mark.asyncio
    async def test_station_not_found(self, tool, mock_http_client):
        """Test when station is not found."""
        mock_http_client.fetch.return_value = MagicMock(
            data={"type": "FeatureCollection", "features": []},
            file_path=None,
        )

        input_data = SearchByStationInput(stationName="存在しない駅")
        result = await tool.run(input_data)

        assert isinstance(result, SearchByStationResponse)
        assert "not found" in " ".join(result.summary).lower()

    def test_descriptor(self, tool):
        """Test tool descriptor."""
        descriptor = tool.descriptor()
        assert descriptor["name"] == "mlit.search_by_station"
        assert "description" in descriptor
