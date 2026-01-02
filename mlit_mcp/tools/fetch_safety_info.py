"""Tool for fetching comprehensive safety information (tsunami, storm surge, shelters)."""

from __future__ import annotations

import logging
import json
from typing import Any
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from mlit_mcp.http_client import MLITHttpClient
from .gis_helpers import lat_lon_to_tile

logger = logging.getLogger(__name__)


class SafetyInfoType(str, Enum):
    """Types of safety information available."""

    TSUNAMI = "tsunami"
    STORM_SURGE = "storm_surge"
    SHELTER = "shelter"

    @property
    def dataset_id(self) -> str:
        """Return the MLIT dataset ID for this safety info type."""
        if self == SafetyInfoType.TSUNAMI:
            return "XKT037"  # 津波浸水想定
        elif self == SafetyInfoType.STORM_SURGE:
            return "XKT038"  # 高潮浸水想定
        elif self == SafetyInfoType.SHELTER:
            return "XKT016"  # 避難施設
        return ""


class FetchSafetyInfoInput(BaseModel):
    """Input schema for the fetch_safety_info tool."""

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
    info_types: list[SafetyInfoType] = Field(
        default=[
            SafetyInfoType.TSUNAMI,
            SafetyInfoType.STORM_SURGE,
            SafetyInfoType.SHELTER,
        ],
        alias="infoTypes",
        description="List of safety information types to fetch",
    )
    force_refresh: bool = Field(
        default=False,
        alias="forceRefresh",
        description="If true, bypass cache and fetch fresh data",
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class FetchSafetyInfoResponse(BaseModel):
    """Response schema for the fetch_safety_info tool."""

    latitude: float
    longitude: float
    tile_coords: dict[str, int] = Field(
        description="Tile coordinates used (z/x/y)",
        alias="tileCoords",
    )
    safety_info: dict[str, list[dict[str, Any]]] = Field(
        description="Safety information by type",
        alias="safetyInfo",
    )
    summary: list[str] = Field(
        description="Human readable summary of safety information",
    )

    model_config = ConfigDict(populate_by_name=True)


class FetchSafetyInfoTool:
    """Tool for fetching comprehensive safety information."""

    name = "mlit.fetch_safety_info"
    description = (
        "Fetch comprehensive safety information (tsunami inundation, storm surge, "
        "evacuation shelters) for a specific latitude/longitude. "
        "Uses MLIT Real Estate Information Library APIs (XKT037, XKT038, XKT016). "
        "Returns safety data and nearby shelters for the area."
    )
    input_model = FetchSafetyInfoInput
    output_model = FetchSafetyInfoResponse

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

    async def run(self, payload: FetchSafetyInfoInput) -> FetchSafetyInfoResponse:
        """Execute the tool with validated input."""
        # Use zoom level 14 for good detail on safety maps
        Z = 14
        x, y = lat_lon_to_tile(payload.latitude, payload.longitude, Z)

        safety_info: dict[str, list[dict[str, Any]]] = {}
        summary: list[str] = []

        for info_type in payload.info_types:
            dataset_id = info_type.dataset_id
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

                safety_info[info_type.value] = valid_features

                if valid_features:
                    summary.append(
                        f"Found {len(valid_features)} {info_type.value} records."
                    )
                else:
                    summary.append(f"No {info_type.value} data in this area.")

            except Exception as e:
                logger.error(f"Failed to fetch {info_type}: {e}")
                safety_info[info_type.value] = []
                summary.append(f"Failed to fetch {info_type.value} information: {e}")

        return FetchSafetyInfoResponse(
            latitude=payload.latitude,
            longitude=payload.longitude,
            tileCoords={"z": Z, "x": x, "y": y},
            safetyInfo=safety_info,
            summary=summary,
        )


__all__ = [
    "FetchSafetyInfoInput",
    "FetchSafetyInfoResponse",
    "FetchSafetyInfoTool",
    "SafetyInfoType",
]
