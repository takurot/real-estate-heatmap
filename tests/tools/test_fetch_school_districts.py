from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from pydantic import ValidationError

from mlit_mcp.http_client import FetchResult, MLITHttpClient
from mlit_mcp.tools.fetch_school_districts import (
    FetchSchoolDistrictsInput,
    FetchSchoolDistrictsTool,
)
from mlit_mcp.tools.gis_helpers import decode_base64_to_mvt


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    client = AsyncMock(spec=MLITHttpClient)
    return client


@pytest.fixture
def tool(mock_http_client):
    """Create a FetchSchoolDistrictsTool instance."""
    return FetchSchoolDistrictsTool(http_client=mock_http_client)


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
                "properties": {"A27_005": "Example School"},
            }
        ],
    }


class TestFetchSchoolDistrictsInput:
    """Test input validation."""

    def test_valid_input(self):
        """Test valid input."""
        payload = FetchSchoolDistrictsInput(
            z=11,
            x=1819,
            y=806,
        )
        assert payload.z == 11
        assert payload.x == 1819
        assert payload.y == 806
        assert payload.administrative_area_code is None

    def test_valid_input_with_admin_code(self):
        """Test valid input with administrative area code."""
        payload = FetchSchoolDistrictsInput(
            z=11,
            x=1819,
            y=806,
            administrativeAreaCode="13108",
        )
        assert payload.administrative_area_code == "13108"

    def test_zoom_level_validation(self):
        """Test zoom level must be 11-15."""
        with pytest.raises(ValidationError):
            FetchSchoolDistrictsInput(
                z=10,  # Too low
                x=100,
                y=100,
            )


class TestFetchSchoolDistrictsTool:
    """Test FetchSchoolDistrictsTool functionality."""

    @pytest.mark.anyio
    async def test_mvt_base64_return(self, tool, mock_http_client, tmp_path):
        """Test MVT base64 encoding."""
        mvt_content = b"\x1a\x0eschool district data"
        mvt_file = tmp_path / "test.mvt"
        mvt_file.write_bytes(mvt_content)

        mock_http_client.fetch.return_value = FetchResult(
            data=None,
            file_path=mvt_file,
            from_cache=False,
        )

        payload = FetchSchoolDistrictsInput(
            z=11,
            x=1819,
            y=806,
            responseFormat="pbf",
        )
        result = await tool.run(payload)

        assert result.mvt_base64 is not None
        assert result.geojson is None
        assert result.meta.cache_hit is False
        assert result.meta.format == "pbf"

        # Verify we can decode it back
        decoded = decode_base64_to_mvt(result.mvt_base64)
        assert decoded == mvt_content

    @pytest.mark.anyio
    # fmt: off
    async def test_geojson_return(
        self, tool, mock_http_client, sample_geojson
    ):
        # fmt: on
        """Test GeoJSON return."""
        mock_http_client.fetch.return_value = FetchResult(
            data=sample_geojson,
            from_cache=False,
        )

        payload = FetchSchoolDistrictsInput(
            z=11,
            x=1819,
            y=806,
            responseFormat="geojson",
        )
        result = await tool.run(payload)

        assert result.geojson == sample_geojson
        assert result.mvt_base64 is None
        assert result.meta.format == "geojson"

    @pytest.mark.anyio
    async def test_with_admin_code(self, tool, mock_http_client, tmp_path):
        """Test request with administrative area code parameter."""
        mvt_content = b"\x1a\x04test"
        mvt_file = tmp_path / "test.mvt"
        mvt_file.write_bytes(mvt_content)

        mock_http_client.fetch.return_value = FetchResult(
            data=None,
            file_path=mvt_file,
            from_cache=False,
        )

        payload = FetchSchoolDistrictsInput(
            z=11,
            x=1819,
            y=806,
            administrativeAreaCode="13108",
        )
        result = await tool.run(payload)

        assert result.meta.format == "geojson"  # default format

        # Verify admin code was passed to API
        call_args = mock_http_client.fetch.call_args
        assert call_args.kwargs["params"]["administrativeAreaCode"] == "13108"

    @pytest.mark.anyio
    async def test_cache_hit(self, tool, mock_http_client, tmp_path):
        """Test cache hit behavior."""
        mvt_content = b"\x1a\x04test"
        mvt_file = tmp_path / "test.mvt"
        mvt_file.write_bytes(mvt_content)

        mock_http_client.fetch.return_value = FetchResult(
            data=None,
            file_path=mvt_file,
            from_cache=True,
        )

        payload = FetchSchoolDistrictsInput(
            z=11,
            x=1819,
            y=806,
        )
        result = await tool.run(payload)

        assert result.meta.cache_hit is True

    @pytest.mark.anyio
    async def test_force_refresh(self, tool, mock_http_client, tmp_path):
        """Test force_refresh parameter."""
        mvt_content = b"\x1a\x04test"
        mvt_file = tmp_path / "test.mvt"
        mvt_file.write_bytes(mvt_content)

        mock_http_client.fetch.return_value = FetchResult(
            data=None,
            file_path=mvt_file,
            from_cache=False,
        )

        payload = FetchSchoolDistrictsInput(
            z=11,
            x=1819,
            y=806,
            forceRefresh=True,
        )
        await tool.run(payload)

        call_args = mock_http_client.fetch.call_args
        assert call_args.kwargs["force_refresh"] is True

    @pytest.mark.anyio
    # fmt: off
    async def test_large_response_resource_uri(
        self, tool, mock_http_client, tmp_path
    ):
        # fmt: on
        """Test that large responses return a resource URI."""
        # Create a large file (> 1MB)
        large_content = b"x" * (1024 * 1024 + 1)
        large_file = tmp_path / "large.pbf"
        large_file.write_bytes(large_content)

        mock_http_client.fetch.return_value = FetchResult(
            data=None,
            file_path=large_file,
            from_cache=False,
        )

        payload = FetchSchoolDistrictsInput(
            z=11,
            x=1819,
            y=806,
            responseFormat="pbf",
        )
        result = await tool.run(payload)

        assert result.mvt_base64 is None
        assert result.geojson is None
        assert result.resource_uri is not None
        # fmt: off
        assert result.resource_uri.startswith(
            "resource://mlit/school_districts/"
        )
        # fmt: on
        assert result.meta.is_resource is True
        assert result.meta.size_bytes > 1024 * 1024
