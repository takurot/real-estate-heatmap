from __future__ import annotations

import pytest
import json
from unittest.mock import AsyncMock
from pydantic import ValidationError

from mlit_mcp.http_client import FetchResult, MLITHttpClient
from mlit_mcp.tools.fetch_urban_planning_zones import (
    FetchUrbanPlanningZonesInput,
    FetchUrbanPlanningZonesTool,
)
from mlit_mcp.tools.gis_helpers import decode_base64_to_mvt


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    client = AsyncMock(spec=MLITHttpClient)
    return client


@pytest.fixture
def tool(mock_http_client):
    """Create a FetchUrbanPlanningZonesTool instance."""
    return FetchUrbanPlanningZonesTool(http_client=mock_http_client)


@pytest.fixture
def sample_geojson():
    """Sample GeoJSON data."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [139.7, 35.7],
                            [139.8, 35.7],
                            [139.8, 35.8],
                            [139.7, 35.7],
                        ]
                    ],
                },
                "properties": {"zone": "residential"},
            }
        ],
    }


class TestFetchUrbanPlanningZonesInput:
    """Test input validation."""

    def test_valid_input_with_tiles(self):
        """Test valid input with z/x/y tiles."""
        payload = FetchUrbanPlanningZonesInput(
            z=11,
            x=1819,
            y=806,
        )
        assert payload.z == 11
        assert payload.x == 1819
        assert payload.y == 806

    def test_zoom_level_validation(self):
        """Test zoom level must be 11-15."""
        with pytest.raises(ValidationError):
            FetchUrbanPlanningZonesInput(
                z=10,  # Too low
                x=100,
                y=100,
            )


class TestFetchUrbanPlanningZonesTool:
    """Test FetchUrbanPlanningZonesTool functionality."""

    @pytest.mark.anyio
    async def test_tiles_request_geojson(self, tool, mock_http_client, sample_geojson):
        """Test tile request with GeoJSON format."""
        mock_http_client.fetch.return_value = FetchResult(
            data=sample_geojson,
            from_cache=False,
        )

        payload = FetchUrbanPlanningZonesInput(
            z=11,
            x=1819,
            y=806,
            responseFormat="geojson",
        )
        result = await tool.run(payload)

        assert result.geojson == sample_geojson
        assert result.pbf_base64 is None
        assert result.meta.format == "geojson"

        # Verify correct params were sent
        call_args = mock_http_client.fetch.call_args
        assert call_args.kwargs["params"]["z"] == 11
        assert call_args.kwargs["params"]["x"] == 1819
        assert call_args.kwargs["params"]["y"] == 806

    @pytest.mark.anyio
    async def test_pbf_format(self, tool, mock_http_client, tmp_path):
        """Test PBF format response."""
        pbf_content = b"\x1a\x0btest data"
        pbf_file = tmp_path / "test.pbf"
        pbf_file.write_bytes(pbf_content)

        mock_http_client.fetch.return_value = FetchResult(
            data=None,
            file_path=pbf_file,
            from_cache=False,
        )

        payload = FetchUrbanPlanningZonesInput(
            z=11,
            x=1819,
            y=806,
            responseFormat="pbf",
        )
        result = await tool.run(payload)

        assert result.geojson is None
        assert result.pbf_base64 is not None

        # Verify decoding
        decoded = decode_base64_to_mvt(result.pbf_base64)
        assert decoded == pbf_content

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

        payload = FetchUrbanPlanningZonesInput(
            z=11,
            x=1819,
            y=806,
            responseFormat="geojson",
        )
        result = await tool.run(payload)

        assert result.geojson is None
        assert result.resource_uri is not None
        assert result.resource_uri.startswith("resource://mlit/urban_planning_zones/")
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

        payload = FetchUrbanPlanningZonesInput(
            z=11,
            x=1819,
            y=806,
            responseFormat="geojson",
        )
        result = await tool.run(payload)

        # Should load content from file
        assert result.geojson == small_geojson
        assert result.resource_uri is None
        assert result.meta.is_resource is False
        assert result.meta.cache_hit is True
