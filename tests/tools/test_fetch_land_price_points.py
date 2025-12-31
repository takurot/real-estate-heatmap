from __future__ import annotations

import pytest
import json

from unittest.mock import AsyncMock

from mlit_mcp.http_client import FetchResult, MLITHttpClient
from mlit_mcp.tools.fetch_land_price_points import (
    FetchLandPricePointsInput,
    FetchLandPricePointsTool,
)
from mlit_mcp.tools.gis_helpers import decode_base64_to_mvt


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    client = AsyncMock(spec=MLITHttpClient)
    return client


@pytest.fixture
def tool(mock_http_client):
    """Create a FetchLandPricePointsTool instance."""
    return FetchLandPricePointsTool(http_client=mock_http_client)


@pytest.fixture
def sample_geojson():
    """Sample GeoJSON data."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [139.7, 35.7]},
                "properties": {"price": 500000},
            }
        ],
    }


class TestFetchLandPricePointsInput:
    """Test input validation."""

    def test_valid_input_geojson(self):
        """Test valid input for GeoJSON format."""
        payload = FetchLandPricePointsInput(
            z=13,
            x=7312,
            y=3008,
            year=2020,
            responseFormat="geojson",
        )
        assert payload.z == 13
        assert payload.x == 7312
        assert payload.y == 3008
        assert payload.year == 2020
        assert payload.response_format == "geojson"

    def test_valid_input_pbf(self):
        """Test valid input for PBF format."""
        payload = FetchLandPricePointsInput(
            z=14,
            x=14624,
            y=6016,
            year=2024,
            responseFormat="pbf",
        )
        assert payload.response_format == "pbf"

    def test_zoom_level_validation(self):
        """Test zoom level must be 13-15."""
        with pytest.raises(Exception):  # Pydantic validation error
            FetchLandPricePointsInput(
                z=10,  # Too low
                x=100,
                y=100,
                year=2020,
            )


class TestFetchLandPricePointsTool:
    """Test FetchLandPricePointsTool functionality."""

    @pytest.mark.anyio
    async def test_geojson_format(self, tool, mock_http_client, sample_geojson):
        """Test GeoJSON format response."""
        mock_http_client.fetch.return_value = FetchResult(
            data=sample_geojson,
            from_cache=False,
        )

        payload = FetchLandPricePointsInput(
            z=13,
            x=7312,
            y=3008,
            year=2020,
            responseFormat="geojson",
        )
        result = await tool.run(payload)

        assert result.geojson == sample_geojson
        assert result.pbf_base64 is None
        assert result.meta.format == "geojson"
        assert result.meta.cache_hit is False

    @pytest.mark.anyio
    async def test_pbf_format(self, tool, mock_http_client, tmp_path):
        """Test PBF format response with base64 encoding."""
        # Create a mock PBF file
        pbf_content = b"\x1a\x0bhello world"  # Mock MVT data
        pbf_file = tmp_path / "test.pbf"
        pbf_file.write_bytes(pbf_content)

        mock_http_client.fetch.return_value = FetchResult(
            data=None,
            file_path=pbf_file,
            from_cache=False,
        )

        payload = FetchLandPricePointsInput(
            z=13,
            x=7312,
            y=3008,
            year=2020,
            responseFormat="pbf",
        )
        result = await tool.run(payload)

        assert result.geojson is None
        assert result.pbf_base64 is not None
        assert result.meta.format == "pbf"

        # Verify we can decode it back
        decoded = decode_base64_to_mvt(result.pbf_base64)
        assert decoded == pbf_content

    @pytest.mark.anyio
    async def test_cache_hit(self, tool, mock_http_client, sample_geojson):
        """Test cache hit behavior."""
        mock_http_client.fetch.return_value = FetchResult(
            data=sample_geojson,
            from_cache=True,
        )

        payload = FetchLandPricePointsInput(
            z=13,
            x=7312,
            y=3008,
            year=2020,
        )
        result = await tool.run(payload)

        assert result.meta.cache_hit is True

    @pytest.mark.anyio
    async def test_force_refresh(self, tool, mock_http_client, sample_geojson):
        """Test force_refresh parameter."""
        mock_http_client.fetch.return_value = FetchResult(
            data=sample_geojson,
            from_cache=False,
        )

        payload = FetchLandPricePointsInput(
            z=13,
            x=7312,
            y=3008,
            year=2020,
            forceRefresh=True,
        )
        await tool.run(payload)

        call_args = mock_http_client.fetch.call_args
        assert call_args.kwargs["force_refresh"] is True

    @pytest.mark.anyio
    async def test_large_response_resource_uri(self, tool, mock_http_client, tmp_path):
        """Test that large responses return a resource URI."""
        # Create a large file (> 1MB)
        large_content = b"x" * (1024 * 1024 + 1)
        large_file = tmp_path / "large.geojson"
        large_file.write_bytes(large_content)

        mock_http_client.fetch.return_value = FetchResult(
            data=None,
            file_path=large_file,
            from_cache=False,
        )

        payload = FetchLandPricePointsInput(
            z=13,
            x=7312,
            y=3008,
            year=2020,
            responseFormat="geojson",
        )
        result = await tool.run(payload)

        assert result.geojson is None
        assert result.resource_uri is not None
        assert result.resource_uri.startswith("resource://mlit/land_price_points/")
        assert result.meta.is_resource is True
        assert result.meta.size_bytes > 1024 * 1024

    @pytest.mark.anyio
    async def test_cached_file_loading(self, tool, mock_http_client, tmp_path):
        """Test loading small GeoJSON from cached file (when data is None)."""
        # Create a small GeoJSON file
        small_geojson = {"type": "FeatureCollection", "features": []}
        geojson_file = tmp_path / "cached.geojson"
        geojson_file.write_text(json.dumps(small_geojson))

        # Mock fetch result with no memory data but with file path
        mock_http_client.fetch.return_value = FetchResult(
            data=None,
            file_path=geojson_file,
            from_cache=True,
        )

        payload = FetchLandPricePointsInput(
            z=13,
            x=7312,
            y=3008,
            year=2020,
            responseFormat="geojson",
        )
        result = await tool.run(payload)

        # Should load content from file
        assert result.geojson == small_geojson
        assert result.resource_uri is None
        assert result.meta.is_resource is False
        assert result.meta.cache_hit is True
