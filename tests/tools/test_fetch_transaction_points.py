from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock
from pydantic import ValidationError

from mlit_mcp.http_client import FetchResult, MLITHttpClient
from mlit_mcp.tools.fetch_transaction_points import (
    BoundingBox,
    FetchTransactionPointsInput,
    FetchTransactionPointsTool,
    RESOURCE_THRESHOLD_BYTES,
)


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    client = AsyncMock(spec=MLITHttpClient)
    return client


@pytest.fixture
def tool(mock_http_client):
    """Create a FetchTransactionPointsTool instance."""
    return FetchTransactionPointsTool(http_client=mock_http_client)


@pytest.fixture
def sample_geojson():
    """Sample GeoJSON data."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [139.7, 35.7]},
                "properties": {"price": 50000000},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [139.8, 35.8]},
                "properties": {"price": 60000000},
            },
        ],
    }


class TestBoundingBox:
    """Test BoundingBox validation."""

    def test_valid_bbox(self):
        """Test valid bounding box."""
        bbox = BoundingBox(minLon=139.0, minLat=35.0, maxLon=140.0, maxLat=36.0)
        assert bbox.min_lon == 139.0
        assert bbox.max_lat == 36.0

    def test_invalid_lon_range(self):
        """Test that maxLon < minLon fails."""
        with pytest.raises(ValidationError) as exc_info:
            BoundingBox(minLon=140.0, minLat=35.0, maxLon=139.0, maxLat=36.0)
        assert "maxLon" in str(exc_info.value)

    def test_invalid_lat_range(self):
        """Test that maxLat < minLat fails."""
        with pytest.raises(ValidationError) as exc_info:
            BoundingBox(minLon=139.0, minLat=36.0, maxLon=140.0, maxLat=35.0)
        assert "maxLat" in str(exc_info.value)


class TestFetchTransactionPointsInput:
    """Test input validation."""

    def test_valid_input(self):
        """Test valid input passes validation."""
        payload = FetchTransactionPointsInput(
            area="13",
            fromYear=2020,
            toYear=2024,
        )
        assert payload.area == "13"
        assert payload.from_year == 2020
        assert payload.to_year == 2024
        assert payload.bbox is None

    def test_year_range_validation(self):
        """Test year range validation."""
        with pytest.raises(ValidationError) as exc_info:
            FetchTransactionPointsInput(
                area="13",
                fromYear=2024,
                toYear=2020,
            )
        assert "toYear" in str(exc_info.value)

    def test_with_bbox(self):
        """Test input with bounding box."""
        payload = FetchTransactionPointsInput(
            area="13",
            fromYear=2020,
            toYear=2024,
            bbox={"minLon": 139.0, "minLat": 35.0, "maxLon": 140.0, "maxLat": 36.0},
        )
        assert payload.bbox is not None
        assert payload.bbox.min_lon == 139.0


class TestFetchTransactionPointsTool:
    """Test FetchTransactionPointsTool functionality."""

    @pytest.mark.anyio
    async def test_small_geojson_direct_return(self, tool, mock_http_client, sample_geojson):
        """Test small GeoJSON is returned directly."""
        mock_http_client.fetch.return_value = FetchResult(
            data=sample_geojson,
            from_cache=False,
        )

        payload = FetchTransactionPointsInput(
            area="13",
            fromYear=2020,
            toYear=2024,
        )
        result = await tool.run(payload)

        assert result.geojson == sample_geojson
        assert result.resource_uri is None
        assert result.meta.is_resource is False
        assert result.meta.cache_hit is False

    @pytest.mark.anyio
    async def test_large_geojson_resource_return(self, tool, mock_http_client, tmp_path):
        """Test large GeoJSON is returned as resource URI."""
        # Create a large GeoJSON file
        large_geojson = {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"data": "x" * 100000}} for _ in range(20)],
        }
        
        geojson_file = tmp_path / "large.geojson"
        geojson_file.write_text(json.dumps(large_geojson))

        mock_http_client.fetch.return_value = FetchResult(
            data=large_geojson,
            file_path=geojson_file,
            from_cache=False,
        )

        payload = FetchTransactionPointsInput(
            area="13",
            fromYear=2020,
            toYear=2024,
        )
        result = await tool.run(payload)

        assert result.geojson is None
        assert result.resource_uri is not None
        assert result.resource_uri.startswith("resource://mlit/transaction_points/")
        assert result.meta.is_resource is True
        assert result.meta.size_bytes > RESOURCE_THRESHOLD_BYTES

    @pytest.mark.anyio
    async def test_bbox_filtering(self, tool, mock_http_client, sample_geojson):
        """Test bounding box filtering."""
        mock_http_client.fetch.return_value = FetchResult(
            data=sample_geojson,
            from_cache=False,
        )

        # Bbox that includes only the first point (139.7, 35.7)
        payload = FetchTransactionPointsInput(
            area="13",
            fromYear=2020,
            toYear=2024,
            bbox={"minLon": 139.0, "minLat": 35.0, "maxLon": 139.75, "maxLat": 35.75},
        )
        result = await tool.run(payload)

        assert result.geojson is not None
        assert len(result.geojson["features"]) == 1
        assert result.geojson["features"][0]["geometry"]["coordinates"] == [139.7, 35.7]

    @pytest.mark.anyio
    async def test_bbox_not_specified(self, tool, mock_http_client, sample_geojson):
        """Test that missing bbox works correctly."""
        mock_http_client.fetch.return_value = FetchResult(
            data=sample_geojson,
            from_cache=False,
        )

        payload = FetchTransactionPointsInput(
            area="13",
            fromYear=2020,
            toYear=2024,
        )
        result = await tool.run(payload)

        # All features should be included
        assert result.geojson is not None
        assert len(result.geojson["features"]) == 2

    @pytest.mark.anyio
    async def test_force_refresh(self, tool, mock_http_client, sample_geojson):
        """Test force_refresh parameter."""
        mock_http_client.fetch.return_value = FetchResult(
            data=sample_geojson,
            from_cache=False,
        )

        payload = FetchTransactionPointsInput(
            area="13",
            fromYear=2020,
            toYear=2024,
            forceRefresh=True,
        )
        await tool.run(payload)

        # Verify force_refresh was passed to fetch
        call_args = mock_http_client.fetch.call_args
        assert call_args.kwargs["force_refresh"] is True
        assert call_args.kwargs["response_format"] == "geojson"

    @pytest.mark.anyio
    async def test_cache_hit(self, tool, mock_http_client, sample_geojson):
        """Test cache hit behavior."""
        mock_http_client.fetch.return_value = FetchResult(
            data=sample_geojson,
            from_cache=True,
        )

        payload = FetchTransactionPointsInput(
            area="13",
            fromYear=2020,
            toYear=2024,
        )
        result = await tool.run(payload)

        assert result.meta.cache_hit is True

    @pytest.mark.anyio
    async def test_dataset_id(self, tool, mock_http_client, sample_geojson):
        """Test correct dataset ID is returned."""
        mock_http_client.fetch.return_value = FetchResult(
            data=sample_geojson,
            from_cache=False,
        )

        payload = FetchTransactionPointsInput(
            area="13",
            fromYear=2020,
            toYear=2024,
        )
        result = await tool.run(payload)

        assert result.meta.dataset == "XPT001"
