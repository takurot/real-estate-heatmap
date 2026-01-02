"""Tool for comparing market prices to official land prices."""

from __future__ import annotations

import logging
import json
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from mlit_mcp.http_client import MLITHttpClient
from .gis_helpers import lat_lon_to_tile

logger = logging.getLogger(__name__)


class CompareMarketToLandPriceInput(BaseModel):
    """Input schema for the compare_market_to_land_price tool."""

    latitude: float = Field(
        description="Latitude of the location",
        ge=20,
        le=46,
    )
    longitude: float = Field(
        description="Longitude of the location",
        ge=122,
        le=154,
    )
    year: int = Field(
        default=2023,
        description="Year for comparison",
        ge=2005,
        le=2030,
    )
    force_refresh: bool = Field(
        default=False,
        alias="forceRefresh",
        description="If true, bypass cache and fetch fresh data",
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class CompareMarketToLandPriceResponse(BaseModel):
    """Response schema for the compare_market_to_land_price tool."""

    latitude: float
    longitude: float
    year: int
    land_price_avg: Optional[float] = Field(
        default=None,
        alias="landPriceAvg",
        description="Average official land price (per sqm)",
    )
    market_price_avg: Optional[float] = Field(
        default=None,
        alias="marketPriceAvg",
        description="Average transaction price (per sqm)",
    )
    divergence_ratio: Optional[float] = Field(
        default=None,
        alias="divergenceRatio",
        description="Market/Land price ratio (>1 means market is higher)",
    )
    summary: list[str] = Field(description="Human readable summary")

    model_config = ConfigDict(populate_by_name=True)


class CompareMarketToLandPriceTool:
    """Tool for comparing market prices to official land prices."""

    name = "mlit.compare_market_to_land_price"
    description = (
        "Compare actual transaction prices with official land prices for an area. "
        "Uses XPT002 (land price) and XIT001 (transactions) APIs. "
        "Returns divergence ratio showing how market prices compare to official prices."
    )
    input_model = CompareMarketToLandPriceInput
    output_model = CompareMarketToLandPriceResponse

    def __init__(self, http_client: MLITHttpClient) -> None:
        self._http_client = http_client

    def descriptor(self) -> dict[str, Any]:
        """Return the tool descriptor for MCP."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_model.model_json_schema(),
            "outputSchema": self.output_model.model_json_schema(),
        }

    async def invoke(self, raw_arguments: dict | None) -> dict[str, Any]:
        """Invoke the tool with raw arguments."""
        payload = self.input_model.model_validate(raw_arguments or {})
        result = await self.run(payload)
        return result.model_dump(by_alias=True, exclude_none=True)

    async def run(
        self, payload: CompareMarketToLandPriceInput
    ) -> CompareMarketToLandPriceResponse:
        """Execute the tool with validated input."""
        summary: list[str] = []
        land_price_avg: Optional[float] = None
        market_price_avg: Optional[float] = None
        divergence_ratio: Optional[float] = None

        try:
            Z = 13
            x, y = lat_lon_to_tile(payload.latitude, payload.longitude, Z)

            # Fetch land price data (XPT002)
            land_params = {
                "response_format": "geojson",
                "z": Z,
                "x": x,
                "y": y,
                "year": payload.year,
            }

            land_result = await self._http_client.fetch(
                "XPT002",
                params=land_params,
                response_format="geojson",
                force_refresh=payload.force_refresh,
            )

            land_data = land_result.data
            if land_data is None and land_result.file_path:
                try:
                    content = land_result.file_path.read_bytes()
                    land_data = json.loads(content)
                except Exception:
                    land_data = {}

            land_data = land_data or {}
            features = land_data.get("features", [])

            # Calculate average land price
            land_prices = []
            for f in features:
                props = f.get("properties", {})
                price_str = props.get("u_current_years_price_ja", "")
                if price_str:
                    try:
                        land_prices.append(int(price_str.replace(",", "")))
                    except ValueError:
                        pass

            if land_prices:
                land_price_avg = sum(land_prices) / len(land_prices)
                summary.append(
                    f"Land price: avg {land_price_avg:,.0f} yen/sqm "
                    f"({len(land_prices)} points)"
                )

            # Fetch transaction data - simplified
            from_quarter = payload.year * 10 + 1
            to_quarter = payload.year * 10 + 4

            trans_params = {
                "from": from_quarter,
                "to": to_quarter,
                "area": "13",  # Tokyo
            }

            trans_result = await self._http_client.fetch(
                "XIT001",
                params=trans_params,
                response_format="json",
                force_refresh=payload.force_refresh,
            )

            trans_data = trans_result.data or {}
            if trans_data.get("status") == "OK":
                transactions = trans_data.get("data", [])
                market_prices = []
                for t in transactions[:100]:
                    try:
                        price = int(t.get("TradePrice", "0"))
                        area = int(t.get("Area", "1") or "1")
                        if area > 0:
                            market_prices.append(price / area)
                    except (ValueError, TypeError):
                        pass

                if market_prices:
                    market_price_avg = sum(market_prices) / len(market_prices)
                    summary.append(
                        f"Market price: avg {market_price_avg:,.0f} yen/sqm "
                        f"({len(market_prices)} transactions)"
                    )

            # Calculate divergence
            if land_price_avg and market_price_avg:
                divergence_ratio = market_price_avg / land_price_avg
                if divergence_ratio > 1:
                    summary.append(
                        f"Market prices are {(divergence_ratio - 1) * 100:.1f}% "
                        f"higher than official land prices."
                    )
                else:
                    summary.append(
                        f"Market prices are {(1 - divergence_ratio) * 100:.1f}% "
                        f"lower than official land prices."
                    )

        except Exception as e:
            logger.error(f"Failed to compare prices: {e}")
            summary.append(f"Error: {e}")

        return CompareMarketToLandPriceResponse(
            latitude=payload.latitude,
            longitude=payload.longitude,
            year=payload.year,
            landPriceAvg=land_price_avg,
            marketPriceAvg=market_price_avg,
            divergenceRatio=divergence_ratio,
            summary=summary,
        )


__all__ = [
    "CompareMarketToLandPriceInput",
    "CompareMarketToLandPriceResponse",
    "CompareMarketToLandPriceTool",
]
