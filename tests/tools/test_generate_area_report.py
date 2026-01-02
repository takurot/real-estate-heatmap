"""Tests for generate_area_report tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from mlit_mcp.tools.generate_area_report import (
    GenerateAreaReportInput,
    GenerateAreaReportResponse,
    GenerateAreaReportTool,
)


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    client = MagicMock()
    client.fetch = AsyncMock()
    return client


@pytest.fixture
def tool(mock_http_client):
    """Create a GenerateAreaReportTool instance."""
    return GenerateAreaReportTool(http_client=mock_http_client)


class TestGenerateAreaReportInput:
    """Tests for input validation."""

    def test_valid_input(self):
        """Test valid input parameters."""
        input_data = GenerateAreaReportInput(
            latitude=35.6812,
            longitude=139.7671,
        )
        assert input_data.latitude == 35.6812


class TestGenerateAreaReportTool:
    """Tests for the GenerateAreaReportTool."""

    @pytest.mark.asyncio
    async def test_generate_report(self, tool, mock_http_client):
        """Test generating area report."""
        mock_http_client.fetch.return_value = MagicMock(
            data={"type": "FeatureCollection", "features": []},
            file_path=None,
        )

        input_data = GenerateAreaReportInput(
            latitude=35.6812,
            longitude=139.7671,
        )
        result = await tool.run(input_data)

        assert isinstance(result, GenerateAreaReportResponse)
        assert result.latitude == 35.6812
        assert "report" in dir(result)

    def test_descriptor(self, tool):
        """Test tool descriptor."""
        descriptor = tool.descriptor()
        assert descriptor["name"] == "mlit.generate_area_report"
        assert "description" in descriptor
