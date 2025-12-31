from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from pydantic import ValidationError

from mlit_mcp.http_client import FetchResult, MLITHttpClient
from mlit_mcp.tools.fetch_hazard_risks import (
    FetchHazardRisksInput,
    FetchHazardRisksTool,
    HazardType,
)


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    client = AsyncMock(spec=MLITHttpClient)
    return client


@pytest.fixture
def tool(mock_http_client):
    """Create a FetchHazardRisksTool instance."""
    return FetchHazardRisksTool(http_client=mock_http_client)


class TestFetchHazardRisksInput:
    """Test input validation."""

    def test_valid_input(self):
        payload = FetchHazardRisksInput(
            latitude=35.6812, longitude=139.7671, riskTypes=[HazardType.FLOOD]
        )
        assert payload.latitude == 35.6812
        assert payload.longitude == 139.7671
        assert payload.risk_types == [HazardType.FLOOD]

    def test_invalid_lat_lon(self):
        with pytest.raises(ValidationError):
            FetchHazardRisksInput(latitude=100.0, longitude=139.7671)
        with pytest.raises(ValidationError):
            FetchHazardRisksInput(latitude=35.6812, longitude=200.0)


class TestFetchHazardRisksTool:
    """Test FetchHazardRisksTool functionality."""

    @pytest.mark.anyio
    async def test_fetch_multiple_risks(self, tool, mock_http_client):
        """Test fetching both flood and landslide data."""
        # Mock responses for Flood (XKT026) and Landslide (XKT029)
        flood_data = {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"rank": "rank_3"}}],
        }
        landslide_data = {"type": "FeatureCollection", "features": []}

        # Setup side effects for fetch
        async def side_effect(dataset_id, **kwargs):
            if dataset_id == "XKT026":
                return FetchResult(data=flood_data)
            elif dataset_id == "XKT029":
                return FetchResult(data=landslide_data)
            return FetchResult(data={})

        mock_http_client.fetch.side_effect = side_effect

        payload = FetchHazardRisksInput(
            latitude=35.6812,
            longitude=139.7671,
            riskTypes=[HazardType.FLOOD, HazardType.LANDSLIDE],
        )
        result = await tool.run(payload)

        # Verify lat/lon are passed back
        assert result.latitude == 35.6812
        assert result.longitude == 139.7671

        # Verify risks
        assert "flood" in result.risks
        assert len(result.risks["flood"]) == 1
        assert result.risks["flood"][0]["rank"] == "rank_3"

        assert "landslide" in result.risks
        assert len(result.risks["landslide"]) == 0

        # Verify calls
        assert mock_http_client.fetch.call_count == 2

        # Check params (Z=15 is hardcoded in tool)
        # Lat 35.6812, Lon 139.7671 at Z=15
        # x approx 29105, y approx 12902
        args, kwargs = mock_http_client.fetch.call_args_list[0]
        assert kwargs["params"]["z"] == 15
        assert "x" in kwargs["params"]
        assert "y" in kwargs["params"]

    @pytest.mark.anyio
    async def test_partial_failure(self, tool, mock_http_client):
        """Test that failure in one API doesn't crash the entire tool."""

        async def side_effect(dataset_id, **kwargs):
            if dataset_id == "XKT026":
                raise Exception("API Error")
            elif dataset_id == "XKT029":
                return FetchResult(
                    data={"features": [{"properties": {"type": "steep_slope"}}]}
                )
            return FetchResult()

        mock_http_client.fetch.side_effect = side_effect

        payload = FetchHazardRisksInput(
            latitude=35.0,
            longitude=139.0,
            riskTypes=[HazardType.FLOOD, HazardType.LANDSLIDE],
        )
        result = await tool.run(payload)

        assert "landslide" in result.risks
        assert len(result.risks["landslide"]) == 1

        # Flood should be absent or logged in summary
        assert "flood" not in result.risks
        assert any("Failed to fetch flood" in s for s in result.summary)
