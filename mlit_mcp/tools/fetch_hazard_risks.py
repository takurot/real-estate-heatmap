from __future__ import annotations

import logging
import json
from typing import Any
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from mlit_mcp.http_client import MLITHttpClient
from .gis_helpers import lat_lon_to_tile

logger = logging.getLogger(__name__)


class HazardType(str, Enum):
    FLOOD = "flood"
    LANDSLIDE = "landslide"
    # TSUNAMI = "tsunami" # ID pending verification

    @property
    def dataset_id(self) -> str:
        if self == HazardType.FLOOD:
            return "XKT026"
        elif self == HazardType.LANDSLIDE:
            return "XKT029"
        return ""


class FetchHazardRisksInput(BaseModel):
    """Input schema for the fetch_hazard_risks tool."""

    latitude: float = Field(description="Latitude of the location", ge=20, le=46)
    longitude: float = Field(description="Longitude of the location", ge=122, le=154)
    risk_types: list[HazardType] = Field(
        default=[HazardType.FLOOD, HazardType.LANDSLIDE],
        alias="riskTypes",
        description="List of risk types to fetch",
    )
    force_refresh: bool = Field(
        default=False,
        alias="forceRefresh",
        description="If true, bypass cache and fetch fresh data",
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class FetchHazardRisksResponse(BaseModel):
    latitude: float
    longitude: float
    tile_coords: dict[str, int] = Field(
        description="Tile coordinates used (z/x/y)", alias="tileCoords"
    )
    risks: dict[str, list[dict[str, Any]]] = Field(
        description="Found risk features by type"
    )
    summary: list[str] = Field(description="Human readable summary of risks")

    model_config = ConfigDict(populate_by_name=True)


class FetchHazardRisksTool:
    """Tool for fetching hazard map data (flood, landslide) for a specific location."""

    name = "mlit.fetch_hazard_risks"
    description = (
        "Fetch hazard risk information (Flood, Landslide) for a specific latitude/longitude. "
        "Uses MLIT Real Estate Information Library APIs (XKT026, XKT029). "
        "Returns a summary of risks in the surrounding map tile."
    )
    input_model = FetchHazardRisksInput
    output_model = FetchHazardRisksResponse

    def __init__(self, http_client: MLITHttpClient) -> None:
        self._http_client = http_client

    def descriptor(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_model.model_json_schema(),
            "outputSchema": self.output_model.model_json_schema(),
        }

    async def invoke(self, raw_arguments: dict | None) -> dict[str, Any]:
        payload = self.input_model.model_validate(raw_arguments or {})
        result = await self.run(payload)
        return result.model_dump(by_alias=True, exclude_none=True)

    async def run(self, payload: FetchHazardRisksInput) -> FetchHazardRisksResponse:
        # Standard zoom for detailed hazard maps
        Z = 15
        x, y = lat_lon_to_tile(payload.latitude, payload.longitude, Z)

        risks: dict[str, list[dict[str, Any]]] = {}
        summary: list[str] = []

        for risk_type in payload.risk_types:
            dataset_id = risk_type.dataset_id
            if not dataset_id:
                continue

            params = {
                "response_format": "geojson",
                "z": Z,
                "x": x,
                "y": y,
            }

            try:
                fetch_result = await self._http_client.fetch(
                    dataset_id,
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

                # Simple filtering: Return all features in the tile
                # Ideally we would do point-in-polygon check here
                # But without shapely, we return tile contents and let user/LLM decide
                # or we could attempt bounding box check if geometry is mostly boxes

                # For now, just return specific properties to save space
                valid_features = []
                for f in features:
                    props = f.get("properties", {})
                    # Add simple "distance" check if geometry is Point?
                    # Most hazard maps are Polygons.
                    valid_features.append(props)

                if valid_features:
                    risks[risk_type.value] = valid_features
                    summary.append(
                        f"Found {len(valid_features)} {risk_type.value} records in tile area."
                    )
                else:
                    risks[risk_type.value] = []

            except Exception as e:
                logger.error(f"Failed to fetch {risk_type}: {e}")
                summary.append(f"Failed to fetch {risk_type.value} information.")

        return FetchHazardRisksResponse(
            latitude=payload.latitude,
            longitude=payload.longitude,
            tileCoords={"z": Z, "x": x, "y": y},
            risks=risks,
            summary=summary,
        )


__all__ = [
    "FetchHazardRisksInput",
    "FetchHazardRisksResponse",
    "FetchHazardRisksTool",
    "HazardType",
]
