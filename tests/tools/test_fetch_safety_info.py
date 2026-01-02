"""Tests for fetch_safety_info tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from mlit_mcp.tools.fetch_safety_info import (
    FetchSafetyInfoInput,
    FetchSafetyInfoResponse,
    FetchSafetyInfoTool,
    SafetyInfoType,
)


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    client = MagicMock()
    client.fetch = AsyncMock()
    return client


@pytest.fixture
def tool(mock_http_client):
    """Create a FetchSafetyInfoTool instance."""
    return FetchSafetyInfoTool(http_client=mock_http_client)


class TestFetchSafetyInfoInput:
    """Tests for input validation."""

    def test_valid_input(self):
        """Test valid input parameters."""
        input_data = FetchSafetyInfoInput(
            latitude=35.6812,
            longitude=139.7671,
        )
        assert input_data.latitude == 35.6812
        assert input_data.longitude == 139.7671
        assert SafetyInfoType.TSUNAMI in input_data.info_types
        assert SafetyInfoType.STORM_SURGE in input_data.info_types
        assert SafetyInfoType.SHELTER in input_data.info_types

    def test_custom_info_types(self):
        """Test with custom info types."""
        input_data = FetchSafetyInfoInput(
            latitude=35.6812,
            longitude=139.7671,
            infoTypes=[SafetyInfoType.TSUNAMI],
        )
        assert len(input_data.info_types) == 1
        assert SafetyInfoType.TSUNAMI in input_data.info_types

    def test_invalid_latitude(self):
        """Test validation for latitude out of range."""
        with pytest.raises(ValueError):
            FetchSafetyInfoInput(
                latitude=50.0,  # Too high for Japan
                longitude=139.7671,
            )

    def test_invalid_longitude(self):
        """Test validation for longitude out of range."""
        with pytest.raises(ValueError):
            FetchSafetyInfoInput(
                latitude=35.6812,
                longitude=200.0,  # Too high
            )


class TestFetchSafetyInfoTool:
    """Tests for the FetchSafetyInfoTool."""

    @pytest.mark.asyncio
    async def test_fetch_tsunami_info(self, tool, mock_http_client):
        """Test fetching tsunami information."""
        # Mock response for tsunami API
        mock_http_client.fetch.return_value = MagicMock(
            data={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "depth_rank": "3m-5m",
                            "area_name": "Test Area",
                        },
                        "geometry": {"type": "Polygon", "coordinates": [[]]},
                    }
                ],
            },
            file_path=None,
        )

        input_data = FetchSafetyInfoInput(
            latitude=35.6812,
            longitude=139.7671,
            infoTypes=[SafetyInfoType.TSUNAMI],
        )
        result = await tool.run(input_data)

        assert isinstance(result, FetchSafetyInfoResponse)
        assert result.latitude == 35.6812
        assert result.longitude == 139.7671
        assert "tsunami" in result.safety_info
        assert len(result.safety_info["tsunami"]) > 0

    @pytest.mark.asyncio
    async def test_fetch_shelter_info(self, tool, mock_http_client):
        """Test fetching shelter information."""
        mock_http_client.fetch.return_value = MagicMock(
            data={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "P20_002": "避難所名",
                            "P20_003": "住所",
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

        input_data = FetchSafetyInfoInput(
            latitude=35.6812,
            longitude=139.7671,
            infoTypes=[SafetyInfoType.SHELTER],
        )
        result = await tool.run(input_data)

        assert isinstance(result, FetchSafetyInfoResponse)
        assert "shelter" in result.safety_info

    @pytest.mark.asyncio
    async def test_fetch_all_info_types(self, tool, mock_http_client):
        """Test fetching all safety info types."""
        mock_http_client.fetch.return_value = MagicMock(
            data={"type": "FeatureCollection", "features": []},
            file_path=None,
        )

        input_data = FetchSafetyInfoInput(
            latitude=35.6812,
            longitude=139.7671,
        )
        result = await tool.run(input_data)

        # Should have attempted to fetch all three types
        assert mock_http_client.fetch.call_count == 3
        assert "tsunami" in result.safety_info
        assert "storm_surge" in result.safety_info
        assert "shelter" in result.safety_info

    @pytest.mark.asyncio
    async def test_api_error_handling(self, tool, mock_http_client):
        """Test handling of API errors."""
        mock_http_client.fetch.side_effect = Exception("API Error")

        input_data = FetchSafetyInfoInput(
            latitude=35.6812,
            longitude=139.7671,
            infoTypes=[SafetyInfoType.TSUNAMI],
        )
        result = await tool.run(input_data)

        # Should still return a response with error in summary
        assert isinstance(result, FetchSafetyInfoResponse)
        assert any("Failed" in s or "Error" in s for s in result.summary)

    def test_descriptor(self, tool):
        """Test tool descriptor."""
        descriptor = tool.descriptor()
        assert descriptor["name"] == "mlit.fetch_safety_info"
        assert "description" in descriptor
        assert "inputSchema" in descriptor
