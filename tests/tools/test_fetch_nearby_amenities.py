"""Tests for fetch_nearby_amenities tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from mlit_mcp.tools.fetch_nearby_amenities import (
    FetchNearbyAmenitiesInput,
    FetchNearbyAmenitiesResponse,
    FetchNearbyAmenitiesTool,
    AmenityType,
)


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    client = MagicMock()
    client.fetch = AsyncMock()
    return client


@pytest.fixture
def tool(mock_http_client):
    """Create a FetchNearbyAmenitiesTool instance."""
    return FetchNearbyAmenitiesTool(http_client=mock_http_client)


class TestFetchNearbyAmenitiesInput:
    """Tests for input validation."""

    def test_valid_input(self):
        """Test valid input parameters."""
        input_data = FetchNearbyAmenitiesInput(
            latitude=35.6812,
            longitude=139.7671,
        )
        assert input_data.latitude == 35.6812
        assert input_data.longitude == 139.7671
        assert AmenityType.SCHOOL in input_data.amenity_types
        assert AmenityType.NURSERY in input_data.amenity_types
        assert AmenityType.MEDICAL in input_data.amenity_types
        assert AmenityType.WELFARE in input_data.amenity_types

    def test_custom_amenity_types(self):
        """Test with custom amenity types."""
        input_data = FetchNearbyAmenitiesInput(
            latitude=35.6812,
            longitude=139.7671,
            amenityTypes=[AmenityType.SCHOOL, AmenityType.MEDICAL],
        )
        assert len(input_data.amenity_types) == 2
        assert AmenityType.SCHOOL in input_data.amenity_types
        assert AmenityType.MEDICAL in input_data.amenity_types

    def test_invalid_latitude(self):
        """Test validation for latitude out of range."""
        with pytest.raises(ValueError):
            FetchNearbyAmenitiesInput(
                latitude=50.0,  # Too high for Japan
                longitude=139.7671,
            )


class TestFetchNearbyAmenitiesTool:
    """Tests for the FetchNearbyAmenitiesTool."""

    @pytest.mark.asyncio
    async def test_fetch_school_amenities(self, tool, mock_http_client):
        """Test fetching school amenities."""
        mock_http_client.fetch.return_value = MagicMock(
            data={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "P29_003": "東京小学校",
                            "P29_004": "東京都千代田区",
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

        input_data = FetchNearbyAmenitiesInput(
            latitude=35.6812,
            longitude=139.7671,
            amenityTypes=[AmenityType.SCHOOL],
        )
        result = await tool.run(input_data)

        assert isinstance(result, FetchNearbyAmenitiesResponse)
        assert "school" in result.amenities
        assert len(result.amenities["school"]) > 0

    @pytest.mark.asyncio
    async def test_fetch_medical_amenities(self, tool, mock_http_client):
        """Test fetching medical facilities."""
        mock_http_client.fetch.return_value = MagicMock(
            data={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "P04_001": "東京病院",
                            "P04_002": "内科",
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

        input_data = FetchNearbyAmenitiesInput(
            latitude=35.6812,
            longitude=139.7671,
            amenityTypes=[AmenityType.MEDICAL],
        )
        result = await tool.run(input_data)

        assert isinstance(result, FetchNearbyAmenitiesResponse)
        assert "medical" in result.amenities

    @pytest.mark.asyncio
    async def test_fetch_all_amenity_types(self, tool, mock_http_client):
        """Test fetching all amenity types."""
        mock_http_client.fetch.return_value = MagicMock(
            data={"type": "FeatureCollection", "features": []},
            file_path=None,
        )

        input_data = FetchNearbyAmenitiesInput(
            latitude=35.6812,
            longitude=139.7671,
        )
        result = await tool.run(input_data)

        # Should have attempted to fetch all four types
        assert mock_http_client.fetch.call_count == 4
        assert "school" in result.amenities
        assert "nursery" in result.amenities
        assert "medical" in result.amenities
        assert "welfare" in result.amenities

    @pytest.mark.asyncio
    async def test_api_error_handling(self, tool, mock_http_client):
        """Test handling of API errors."""
        mock_http_client.fetch.side_effect = Exception("API Error")

        input_data = FetchNearbyAmenitiesInput(
            latitude=35.6812,
            longitude=139.7671,
            amenityTypes=[AmenityType.SCHOOL],
        )
        result = await tool.run(input_data)

        # Should still return a response with error in summary
        assert isinstance(result, FetchNearbyAmenitiesResponse)
        assert any("Failed" in s or "Error" in s for s in result.summary)

    def test_descriptor(self, tool):
        """Test tool descriptor."""
        descriptor = tool.descriptor()
        assert descriptor["name"] == "mlit.fetch_nearby_amenities"
        assert "description" in descriptor
        assert "inputSchema" in descriptor
