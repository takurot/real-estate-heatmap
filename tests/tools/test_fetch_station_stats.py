"""Tests for fetch_station_stats tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from mlit_mcp.tools.fetch_station_stats import (
    FetchStationStatsInput,
    FetchStationStatsResponse,
    FetchStationStatsTool,
)


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    client = MagicMock()
    client.fetch = AsyncMock()
    return client


@pytest.fixture
def tool(mock_http_client):
    """Create a FetchStationStatsTool instance."""
    return FetchStationStatsTool(http_client=mock_http_client)


class TestFetchStationStatsInput:
    """Tests for input validation."""

    def test_valid_input_with_coords(self):
        """Test valid input parameters with coordinates."""
        input_data = FetchStationStatsInput(
            latitude=35.6812,
            longitude=139.7671,
        )
        assert input_data.latitude == 35.6812
        assert input_data.longitude == 139.7671
        assert input_data.station_name is None

    def test_valid_input_with_station_name(self):
        """Test valid input parameters with station name."""
        input_data = FetchStationStatsInput(
            stationName="東京",
        )
        assert input_data.station_name == "東京"
        assert input_data.latitude is None
        assert input_data.longitude is None

    def test_invalid_latitude(self):
        """Test validation for latitude out of range."""
        with pytest.raises(ValueError):
            FetchStationStatsInput(
                latitude=50.0,  # Too high for Japan
                longitude=139.7671,
            )


class TestFetchStationStatsTool:
    """Tests for the FetchStationStatsTool."""

    @pytest.mark.asyncio
    async def test_fetch_by_coordinates(self, tool, mock_http_client):
        """Test fetching station stats by coordinates."""
        mock_http_client.fetch.return_value = MagicMock(
            data={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "S12_001_ja": "東京駅",
                            "S12_002_ja": "JR東日本",
                            "S12_003_ja": "山手線",
                            "S12_009": "150000",  # 乗降客数2011
                            "S12_057": "180000",  # 乗降客数最新
                        },
                        "geometry": {
                            "type": "Point",
                            "coordinates": [139.7671, 35.6812],
                        },
                    }
                ],
            },
            file_path=None,
        )

        input_data = FetchStationStatsInput(
            latitude=35.6812,
            longitude=139.7671,
        )
        result = await tool.run(input_data)

        assert isinstance(result, FetchStationStatsResponse)
        assert len(result.stations) > 0
        assert result.stations[0]["station_name"] == "東京駅"

    @pytest.mark.asyncio
    async def test_fetch_empty_results(self, tool, mock_http_client):
        """Test fetching with no stations found."""
        mock_http_client.fetch.return_value = MagicMock(
            data={"type": "FeatureCollection", "features": []},
            file_path=None,
        )

        input_data = FetchStationStatsInput(
            latitude=35.6812,
            longitude=139.7671,
        )
        result = await tool.run(input_data)

        assert isinstance(result, FetchStationStatsResponse)
        assert len(result.stations) == 0

    @pytest.mark.asyncio
    async def test_api_error_handling(self, tool, mock_http_client):
        """Test handling of API errors."""
        mock_http_client.fetch.side_effect = Exception("API Error")

        input_data = FetchStationStatsInput(
            latitude=35.6812,
            longitude=139.7671,
        )
        result = await tool.run(input_data)

        # Should still return a response with error in summary
        assert isinstance(result, FetchStationStatsResponse)
        assert any("Error" in s or "Failed" in s for s in result.summary)

    def test_descriptor(self, tool):
        """Test tool descriptor."""
        descriptor = tool.descriptor()
        assert descriptor["name"] == "mlit.fetch_station_stats"
        assert "description" in descriptor
        assert "inputSchema" in descriptor
