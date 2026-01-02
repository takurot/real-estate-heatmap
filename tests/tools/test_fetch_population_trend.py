"""Tests for fetch_population_trend tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from mlit_mcp.tools.fetch_population_trend import (
    FetchPopulationTrendInput,
    FetchPopulationTrendResponse,
    FetchPopulationTrendTool,
)


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    client = MagicMock()
    client.fetch = AsyncMock()
    return client


@pytest.fixture
def tool(mock_http_client):
    """Create a FetchPopulationTrendTool instance."""
    return FetchPopulationTrendTool(http_client=mock_http_client)


class TestFetchPopulationTrendInput:
    """Tests for input validation."""

    def test_valid_input(self):
        """Test valid input parameters."""
        input_data = FetchPopulationTrendInput(
            latitude=35.6812,
            longitude=139.7671,
        )
        assert input_data.latitude == 35.6812
        assert input_data.longitude == 139.7671

    def test_invalid_latitude(self):
        """Test validation for latitude out of range."""
        with pytest.raises(ValueError):
            FetchPopulationTrendInput(
                latitude=50.0,  # Too high for Japan
                longitude=139.7671,
            )


class TestFetchPopulationTrendTool:
    """Tests for the FetchPopulationTrendTool."""

    @pytest.mark.asyncio
    async def test_fetch_population_data(self, tool, mock_http_client):
        """Test fetching population trend data."""
        mock_http_client.fetch.return_value = MagicMock(
            data={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "MESH_ID": "53393599",
                            "PTN_2020": "1500",
                            "PTN_2025": "1450",
                            "PTN_2030": "1400",
                            "PTN_2040": "1300",
                            "PTN_2050": "1200",
                        },
                        "geometry": {"type": "Polygon", "coordinates": [[]]},
                    }
                ],
            },
            file_path=None,
        )

        input_data = FetchPopulationTrendInput(
            latitude=35.6812,
            longitude=139.7671,
        )
        result = await tool.run(input_data)

        assert isinstance(result, FetchPopulationTrendResponse)
        assert len(result.mesh_data) > 0
        assert result.mesh_data[0]["mesh_id"] == "53393599"

    @pytest.mark.asyncio
    async def test_fetch_empty_results(self, tool, mock_http_client):
        """Test fetching with no data found."""
        mock_http_client.fetch.return_value = MagicMock(
            data={"type": "FeatureCollection", "features": []},
            file_path=None,
        )

        input_data = FetchPopulationTrendInput(
            latitude=35.6812,
            longitude=139.7671,
        )
        result = await tool.run(input_data)

        assert isinstance(result, FetchPopulationTrendResponse)
        assert len(result.mesh_data) == 0

    @pytest.mark.asyncio
    async def test_api_error_handling(self, tool, mock_http_client):
        """Test handling of API errors."""
        mock_http_client.fetch.side_effect = Exception("API Error")

        input_data = FetchPopulationTrendInput(
            latitude=35.6812,
            longitude=139.7671,
        )
        result = await tool.run(input_data)

        assert isinstance(result, FetchPopulationTrendResponse)
        assert any("Error" in s or "Failed" in s for s in result.summary)

    def test_descriptor(self, tool):
        """Test tool descriptor."""
        descriptor = tool.descriptor()
        assert descriptor["name"] == "mlit.fetch_population_trend"
        assert "description" in descriptor
        assert "inputSchema" in descriptor
