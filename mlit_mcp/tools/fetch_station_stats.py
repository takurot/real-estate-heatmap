"""Tool for fetching station passenger count statistics."""

from __future__ import annotations

import logging
import json
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mlit_mcp.http_client import MLITHttpClient
from .gis_helpers import lat_lon_to_tile

logger = logging.getLogger(__name__)


class FetchStationStatsInput(BaseModel):
    """Input schema for the fetch_station_stats tool."""

    latitude: Optional[float] = Field(
        default=None,
        description="Latitude of the location",
        ge=20,
        le=46,
    )
    longitude: Optional[float] = Field(
        default=None,
        description="Longitude of the location",
        ge=122,
        le=154,
    )
    station_name: Optional[str] = Field(
        default=None,
        alias="stationName",
        description="Station name to search for (partial match)",
    )
    force_refresh: bool = Field(
        default=False,
        alias="forceRefresh",
        description="If true, bypass cache and fetch fresh data",
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @model_validator(mode="after")
    def validate_search_params(self) -> "FetchStationStatsInput":
        """Validate that either coordinates or station name is provided."""
        has_coords = self.latitude is not None and self.longitude is not None
        has_name = self.station_name is not None

        if not has_coords and not has_name:
            raise ValueError(
                "Either latitude/longitude or stationName must be provided"
            )
        return self


class StationStats(BaseModel):
    """Statistics for a single station."""

    station_name: str = Field(alias="stationName")
    operator: str
    line_name: str = Field(alias="lineName")
    passenger_count: Optional[int] = Field(default=None, alias="passengerCount")
    coordinates: list[float]

    model_config = ConfigDict(populate_by_name=True)


class FetchStationStatsResponse(BaseModel):
    """Response schema for the fetch_station_stats tool."""

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    tile_coords: Optional[dict[str, int]] = Field(
        default=None,
        description="Tile coordinates used (z/x/y)",
        alias="tileCoords",
    )
    stations: list[dict[str, Any]] = Field(
        description="List of stations with their statistics",
    )
    summary: list[str] = Field(
        description="Human readable summary",
    )

    model_config = ConfigDict(populate_by_name=True)


class FetchStationStatsTool:
    """Tool for fetching station passenger count statistics."""

    name = "mlit.fetch_station_stats"
    description = (
        "Fetch train station passenger count statistics for a specific location "
        "or station name. Uses MLIT Real Estate Information Library API (XKT015). "
        "Returns station names, operators, line names, and passenger counts."
    )
    input_model = FetchStationStatsInput
    output_model = FetchStationStatsResponse

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

    async def run(self, payload: FetchStationStatsInput) -> FetchStationStatsResponse:
        """Execute the tool with validated input."""
        # Use zoom level 14 for station search
        Z = 14

        stations: list[dict[str, Any]] = []
        summary: list[str] = []
        tile_coords: Optional[dict[str, int]] = None

        try:
            # Search by coordinates
            if payload.latitude is not None and payload.longitude is not None:
                x, y = lat_lon_to_tile(payload.latitude, payload.longitude, Z)
                tile_coords = {"z": Z, "x": x, "y": y}

                params = {
                    "response_format": "geojson",
                    "z": Z,
                    "x": x,
                    "y": y,
                }

                fetch_result = await self._http_client.fetch(
                    "XKT015",
                    params=params,
                    response_format="geojson",
                    force_refresh=payload.force_refresh,
                )

                data = fetch_result.data
                if data is None and fetch_result.file_path:
                    try:
                        content = fetch_result.file_path.read_bytes()
                        data = json.loads(content)
                    except Exception as ex:
                        logger.error(
                            f"Failed to read/parse file {fetch_result.file_path}: {ex}"
                        )
                        data = {}

                data = data or {}
                features = data.get("features", [])

                for f in features:
                    props = f.get("properties", {})
                    geom = f.get("geometry", {})
                    coords = geom.get("coordinates", [0, 0])

                    station_name = props.get("S12_001_ja", "Unknown")

                    # Filter by station name if provided
                    if payload.station_name:
                        if payload.station_name not in station_name:
                            continue

                    # Extract passenger count (latest available year)
                    passenger_count = None
                    for key in ["S12_057", "S12_053", "S12_049", "S12_009"]:
                        if key in props and props[key]:
                            try:
                                passenger_count = int(props[key])
                                break
                            except (ValueError, TypeError):
                                pass

                    stations.append({
                        "station_name": station_name,
                        "operator": props.get("S12_002_ja", "Unknown"),
                        "line_name": props.get("S12_003_ja", "Unknown"),
                        "passenger_count": passenger_count,
                        "coordinates": coords,
                    })

                if stations:
                    summary.append(f"Found {len(stations)} stations in the area.")
                else:
                    summary.append("No stations found in this area.")

        except Exception as e:
            logger.error(f"Failed to fetch station stats: {e}")
            summary.append(f"Error fetching station data: {e}")

        return FetchStationStatsResponse(
            latitude=payload.latitude,
            longitude=payload.longitude,
            tileCoords=tile_coords,
            stations=stations,
            summary=summary,
        )


__all__ = [
    "FetchStationStatsInput",
    "FetchStationStatsResponse",
    "FetchStationStatsTool",
]
