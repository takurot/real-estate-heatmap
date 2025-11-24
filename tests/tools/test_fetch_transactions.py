from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from pydantic import ValidationError

from mlit_mcp.http_client import FetchResult, MLITHttpClient
from mlit_mcp.tools.fetch_transactions import (
    FetchTransactionsInput,
    FetchTransactionsTool,
)


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    client = AsyncMock(spec=MLITHttpClient)
    return client


@pytest.fixture
def tool(mock_http_client):
    """Create a FetchTransactionsTool instance."""
    return FetchTransactionsTool(http_client=mock_http_client)


class TestFetchTransactionsInput:
    """Test input validation."""

    def test_valid_input(self):
        """Test valid input passes validation."""
        payload = FetchTransactionsInput(
            fromYear=2020,
            toYear=2024,
            area="13",
        )
        assert payload.from_year == 2020
        assert payload.to_year == 2024
        assert payload.area == "13"
        assert payload.format == "json"
        assert payload.force_refresh is False

    def test_year_range_validation_fails(self):
        """Test that reversed year range fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            FetchTransactionsInput(
                fromYear=2024,
                toYear=2020,
                area="13",
            )
        assert "toYear" in str(exc_info.value)

    def test_year_bounds(self):
        """Test year bounds validation."""
        # Too early
        with pytest.raises(ValidationError):
            FetchTransactionsInput(fromYear=2000, toYear=2020, area="13")
        
        # Too late
        with pytest.raises(ValidationError):
            FetchTransactionsInput(fromYear=2020, toYear=2035, area="13")

    def test_format_validation(self):
        """Test format field accepts only json or table."""
        # Valid formats
        payload1 = FetchTransactionsInput(fromYear=2020, toYear=2024, area="13", format="json")
        assert payload1.format == "json"
        
        payload2 = FetchTransactionsInput(fromYear=2020, toYear=2024, area="13", format="table")
        assert payload2.format == "table"
        
        # Invalid format
        with pytest.raises(ValidationError):
            FetchTransactionsInput(fromYear=2020, toYear=2024, area="13", format="csv")


class TestFetchTransactionsTool:
    """Test FetchTransactionsTool functionality."""

    @pytest.mark.anyio
    async def test_normal_case_json_format(self, tool, mock_http_client):
        """Test normal execution with JSON format."""
        # Mock returns data for each year separately
        mock_http_client.fetch.return_value = FetchResult(
            data=[{"year": 2020, "price": 50000000}],
            from_cache=False,
        )

        payload = FetchTransactionsInput(
            fromYear=2020,
            toYear=2021,
            area="13101",
        )
        result = await tool.run(payload)

        # Should aggregate data from both years (2 API calls)
        assert len(result.data) == 2
        assert result.meta.cache_hit is False
        assert result.meta.format == "json"
        
        # Verify HTTP client was called twice (once per year)
        assert mock_http_client.fetch.call_count == 2

    @pytest.mark.anyio
    async def test_table_format_conversion(self, tool, mock_http_client):
        """Test table format conversion."""
        mock_http_client.fetch.return_value = FetchResult(
            data=[{"year": 2020}],
            from_cache=False,
        )

        payload = FetchTransactionsInput(
            fromYear=2020,
            toYear=2021,
            area="13",
            format="table",
        )
        result = await tool.run(payload)

        # Should aggregate data from both years
        assert len(result.data) == 2
        assert result.meta.format == "table"

    @pytest.mark.anyio
    async def test_table_format_with_list_response(self, tool, mock_http_client):
        """Test table format when response is already a list."""
        mock_http_client.fetch.return_value = FetchResult(
            data=[{"year": 2020}],
            from_cache=False,
        )

        payload = FetchTransactionsInput(
            fromYear=2020,
            toYear=2021,
            area="13",
            format="table",
        )
        result = await tool.run(payload)

        # Should aggregate data from both years
        assert len(result.data) == 2

    @pytest.mark.anyio
    async def test_cache_hit(self, tool, mock_http_client):
        """Test cache hit behavior."""
        mock_http_client.fetch.return_value = FetchResult(
            data=[{"year": 2020}],
            from_cache=True,
        )

        payload = FetchTransactionsInput(
            fromYear=2020,
            toYear=2020,
            area="13",
        )
        result = await tool.run(payload)

        # Cache hit is always False for multi-year requests
        assert result.meta.cache_hit is False

    @pytest.mark.anyio
    async def test_force_refresh(self, tool, mock_http_client):
        """Test force_refresh parameter."""
        mock_http_client.fetch.return_value = FetchResult(
            data=[{"year": 2020}],
            from_cache=False,
        )

        payload = FetchTransactionsInput(
            fromYear=2020,
            toYear=2020,
            area="13",
            forceRefresh=True,
        )
        await tool.run(payload)

        # Verify force_refresh was passed to fetch
        call_args = mock_http_client.fetch.call_args
        assert call_args.kwargs["force_refresh"] is True

    @pytest.mark.anyio
    async def test_with_classification(self, tool, mock_http_client):
        """Test with optional classification parameter."""
        mock_http_client.fetch.return_value = FetchResult(
            data=[{"year": 2020}],
            from_cache=False,
        )

        payload = FetchTransactionsInput(
            fromYear=2020,
            toYear=2020,
            area="13",
            classification="01",
        )
        await tool.run(payload)

        # Verify classification was included in params
        call_args = mock_http_client.fetch.call_args
        assert call_args.kwargs["params"]["classification"] == "01"
