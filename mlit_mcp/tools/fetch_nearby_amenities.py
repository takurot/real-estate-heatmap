"""Tool for fetching nearby amenities (schools, nurseries, medical, welfare)."""

from __future__ import annotations

import logging
import json
from typing import Any
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from mlit_mcp.http_client import MLITHttpClient
from .gis_helpers import lat_lon_to_tile

logger = logging.getLogger(__name__)


class AmenityType(str, Enum):
    """Types of amenities available."""

    SCHOOL = "school"
    NURSERY = "nursery"
    MEDICAL = "medical"
    WELFARE = "welfare"

    @property
    def dataset_id(self) -> str:
        """Return the MLIT dataset ID for this amenity type."""
        if self == AmenityType.SCHOOL:
            return "XKT008"  # 学校
        elif self == AmenityType.NURSERY:
            return "XKT009"  # 保育園・幼稚園
        elif self == AmenityType.MEDICAL:
            return "XKT010"  # 医療機関
        elif self == AmenityType.WELFARE:
            return "XKT011"  # 福祉施設
        return ""


class FetchNearbyAmenitiesInput(BaseModel):
    """Input schema for the fetch_nearby_amenities tool."""

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
    amenity_types: list[AmenityType] = Field(
        default=[
            AmenityType.SCHOOL,
            AmenityType.NURSERY,
            AmenityType.MEDICAL,
            AmenityType.WELFARE,
        ],
        alias="amenityTypes",
        description="List of amenity types to fetch",
    )
    force_refresh: bool = Field(
        default=False,
        alias="forceRefresh",
        description="If true, bypass cache and fetch fresh data",
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class FetchNearbyAmenitiesResponse(BaseModel):
    """Response schema for the fetch_nearby_amenities tool."""

    latitude: float
    longitude: float
    tile_coords: dict[str, int] = Field(
        description="Tile coordinates used (z/x/y)",
        alias="tileCoords",
    )
    amenities: dict[str, list[dict[str, Any]]] = Field(
        description="Amenities by type",
    )
    summary: list[str] = Field(
        description="Human readable summary of amenities found",
    )

    model_config = ConfigDict(populate_by_name=True)


class FetchNearbyAmenitiesTool:
    """Tool for fetching nearby amenities."""

    name = "mlit.fetch_nearby_amenities"
    description = (
        "Fetch nearby amenities (schools, nurseries, medical facilities, welfare) "
        "for a specific latitude/longitude. "
        "Uses MLIT Real Estate Information Library APIs (XKT008-011). "
        "Returns amenity lists for the surrounding tile area."
    )
    input_model = FetchNearbyAmenitiesInput
    output_model = FetchNearbyAmenitiesResponse

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
        self, payload: FetchNearbyAmenitiesInput
    ) -> FetchNearbyAmenitiesResponse:
        """Execute the tool with validated input."""
        # Use zoom level 14 for good coverage
        Z = 14
        x, y = lat_lon_to_tile(payload.latitude, payload.longitude, Z)

        amenities: dict[str, list[dict[str, Any]]] = {}
        summary: list[str] = []

        for amenity_type in payload.amenity_types:
            dataset_id = amenity_type.dataset_id
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

                # Extract properties from features
                valid_features = []
                for f in features:
                    props = f.get("properties", {})
                    if props:
                        valid_features.append(props)

                amenities[amenity_type.value] = valid_features

                if valid_features:
                    summary.append(
                        f"Found {len(valid_features)} {amenity_type.value} facilities."
                    )
                else:
                    summary.append(f"No {amenity_type.value} facilities in this area.")

            except Exception as e:
                logger.error(f"Failed to fetch {amenity_type}: {e}")
                amenities[amenity_type.value] = []
                summary.append(f"Failed to fetch {amenity_type.value} information: {e}")

        return FetchNearbyAmenitiesResponse(
            latitude=payload.latitude,
            longitude=payload.longitude,
            tileCoords={"z": Z, "x": x, "y": y},
            amenities=amenities,
            summary=summary,
        )


__all__ = [
    "FetchNearbyAmenitiesInput",
    "FetchNearbyAmenitiesResponse",
    "FetchNearbyAmenitiesTool",
    "AmenityType",
]
