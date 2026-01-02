"""Tool for searching transactions by station name."""

from __future__ import annotations

import logging
import json
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from mlit_mcp.http_client import MLITHttpClient
from .gis_helpers import lat_lon_to_tile

logger = logging.getLogger(__name__)


class SearchByStationInput(BaseModel):
    """Input schema for the search_by_station tool."""

    station_name: str = Field(
        alias="stationName",
        description="Station name to search for (partial match supported)",
    )
    from_year: int = Field(
        default=2020,
        alias="fromYear",
        description="Starting year for transaction search",
        ge=2005,
        le=2030,
    )
    to_year: int = Field(
        default=2024,
        alias="toYear",
        description="Ending year for transaction search",
        ge=2005,
        le=2030,
    )
    force_refresh: bool = Field(
        default=False,
        alias="forceRefresh",
        description="If true, bypass cache and fetch fresh data",
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class SearchByStationResponse(BaseModel):
    """Response schema for the search_by_station tool."""

    station_name: str = Field(alias="stationName")
    station_coords: Optional[list[float]] = Field(
        default=None,
        alias="stationCoords",
        description="[longitude, latitude] of the station",
    )
    transactions: list[dict[str, Any]] = Field(
        description="Transaction records in the area",
    )
    summary: list[str] = Field(
        description="Human readable summary",
    )

    model_config = ConfigDict(populate_by_name=True)


class SearchByStationTool:
    """Tool for searching transactions by station name."""

    name = "mlit.search_by_station"
    description = (
        "Search for real estate transactions near a train station by name. "
        "First finds the station location using XKT015, then fetches transactions "
        "from XIT001 for the surrounding area. "
        "Returns station coordinates and transaction records."
    )
    input_model = SearchByStationInput
    output_model = SearchByStationResponse

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

    async def run(self, payload: SearchByStationInput) -> SearchByStationResponse:
        """Execute the tool with validated input."""
        transactions: list[dict[str, Any]] = []
        summary: list[str] = []
        station_coords: Optional[list[float]] = None

        try:
            # Step 1: Find station coordinates using XKT015
            # We search for the station in Tokyo area as default
            # In production, we'd need to search across multiple tiles
            Z = 12  # Lower zoom for wider search
            default_lat, default_lon = 35.6812, 139.7671
            x, y = lat_lon_to_tile(default_lat, default_lon, Z)

            station_params = {
                "response_format": "geojson",
                "z": Z,
                "x": x,
                "y": y,
            }

            fetch_result = await self._http_client.fetch(
                "XKT015",
                params=station_params,
                response_format="geojson",
                force_refresh=payload.force_refresh,
            )

            data = fetch_result.data
            if data is None and fetch_result.file_path:
                try:
                    content = fetch_result.file_path.read_bytes()
                    data = json.loads(content)
                except Exception as ex:
                    logger.error(f"Failed to parse: {ex}")
                    data = {}

            data = data or {}
            features = data.get("features", [])

            # Find matching station
            for f in features:
                props = f.get("properties", {})
                geom = f.get("geometry", {})
                name = props.get("S12_001_ja", "")

                if payload.station_name in name:
                    coords = geom.get("coordinates", [])
                    if coords:
                        station_coords = coords
                        summary.append(f"Found station: {name}")
                        break

            if not station_coords:
                summary.append(f"Station '{payload.station_name}' not found.")
                return SearchByStationResponse(
                    stationName=payload.station_name,
                    stationCoords=None,
                    transactions=[],
                    summary=summary,
                )

            # Step 2: Fetch transactions for the area
            # Get prefecture code - simplified for demo
            from_quarter = payload.from_year * 10 + 1
            to_quarter = payload.to_year * 10 + 4

            trans_params = {
                "from": from_quarter,
                "to": to_quarter,
                "area": "13",  # Tokyo - would need geocoding for dynamic lookup
            }

            trans_result = await self._http_client.fetch(
                "XIT001",
                params=trans_params,
                response_format="json",
                force_refresh=payload.force_refresh,
            )

            trans_data = trans_result.data or {}
            if trans_data.get("status") == "OK":
                raw_transactions = trans_data.get("data", [])
                # Take first 20 for summary
                transactions = raw_transactions[:20]
                summary.append(f"Found {len(raw_transactions)} transactions.")
            else:
                summary.append("No transactions found in the area.")

        except Exception as e:
            logger.error(f"Failed to search by station: {e}")
            summary.append(f"Error: {e}")

        return SearchByStationResponse(
            stationName=payload.station_name,
            stationCoords=station_coords,
            transactions=transactions,
            summary=summary,
        )


__all__ = [
    "SearchByStationInput",
    "SearchByStationResponse",
    "SearchByStationTool",
]
