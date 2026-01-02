"""Tool for fetching future population trend data by mesh."""

from __future__ import annotations

import logging
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mlit_mcp.http_client import MLITHttpClient
from .gis_helpers import lat_lon_to_tile

logger = logging.getLogger(__name__)


class FetchPopulationTrendInput(BaseModel):
    """Input schema for the fetch_population_trend tool."""

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
    force_refresh: bool = Field(
        default=False,
        alias="forceRefresh",
        description="If true, bypass cache and fetch fresh data",
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class FetchPopulationTrendResponse(BaseModel):
    """Response schema for the fetch_population_trend tool."""

    latitude: float
    longitude: float
    tile_coords: dict[str, int] = Field(
        description="Tile coordinates used (z/x/y)",
        alias="tileCoords",
    )
    mesh_data: list[dict[str, Any]] = Field(
        description="Population data by mesh with future projections",
        alias="meshData",
    )
    summary: list[str] = Field(
        description="Human readable summary",
    )

    model_config = ConfigDict(populate_by_name=True)


class FetchPopulationTrendTool:
    """Tool for fetching future population trend data."""

    name = "mlit.fetch_population_trend"
    description = (
        "Fetch future population projection data (250m mesh) for a specific location. "
        "Uses MLIT Real Estate Information Library API (XKT013). "
        "Returns population projections from 2020 to 2050 in 5-year intervals."
    )
    input_model = FetchPopulationTrendInput
    output_model = FetchPopulationTrendResponse

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
        self, payload: FetchPopulationTrendInput
    ) -> FetchPopulationTrendResponse:
        """Execute the tool with validated input."""
        # Use zoom level 14 for population mesh
        Z = 14
        x, y = lat_lon_to_tile(payload.latitude, payload.longitude, Z)

        mesh_data: list[dict[str, Any]] = []
        summary: list[str] = []

        try:
            params = {
                "response_format": "geojson",
                "z": Z,
                "x": x,
                "y": y,
            }

            fetch_result = await self._http_client.fetch(
                "XKT013",
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
                mesh_id = props.get("MESH_ID", "Unknown")

                # Extract population projections by year
                population_by_year = {}
                for year in [2020, 2025, 2030, 2035, 2040, 2045, 2050]:
                    key = f"PTN_{year}"
                    if key in props and props[key]:
                        try:
                            population_by_year[str(year)] = int(props[key])
                        except (ValueError, TypeError):
                            pass

                if population_by_year:
                    mesh_data.append(
                        {
                            "mesh_id": mesh_id,
                            "population_by_year": population_by_year,
                        }
                    )

            if mesh_data:
                summary.append(f"Found population data for {len(mesh_data)} meshes.")

                # Calculate aggregated trend across all meshes when possible
                total_2020 = 0
                total_2050 = 0
                for m in mesh_data:
                    py = m.get("population_by_year", {})
                    if "2020" in py and "2050" in py:
                        total_2020 += int(py["2020"])
                        total_2050 += int(py["2050"])

                if total_2020 > 0:
                    change_pct = (total_2050 - total_2020) / total_2020 * 100
                    trend = "decrease" if change_pct < 0 else "increase"
                    summary.append(
                        f"Population {trend} of {abs(change_pct):.1f}% "
                        f"projected from 2020 to 2050 (aggregated)."
                    )
            else:
                summary.append("No population mesh data available for this area.")

        except Exception as e:
            logger.error(f"Failed to fetch population data: {e}")
            summary.append(f"Error fetching population data: {e}")

        return FetchPopulationTrendResponse(
            latitude=payload.latitude,
            longitude=payload.longitude,
            tileCoords={"z": Z, "x": x, "y": y},
            meshData=mesh_data,
            summary=summary,
        )


__all__ = [
    "FetchPopulationTrendInput",
    "FetchPopulationTrendResponse",
    "FetchPopulationTrendTool",
]
