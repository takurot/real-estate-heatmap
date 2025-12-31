from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mlit_mcp.http_client import MLITHttpClient
from .gis_helpers import encode_mvt_to_base64

logger = logging.getLogger(__name__)

# Threshold for switching to resource URI (1MB)
RESOURCE_THRESHOLD_BYTES = 1024 * 1024


class FetchUrbanPlanningZonesInput(BaseModel):
    """Input schema for the fetch_urban_planning_zones tool."""

    # Tile coordinates (z/x/y) - all required
    z: int = Field(description="Zoom level for tile request (11-15)", ge=11, le=15)
    x: int = Field(description="Tile X coordinate", ge=0)
    y: int = Field(description="Tile Y coordinate", ge=0)
    response_format: Literal["geojson", "pbf"] = Field(
        default="geojson",
        alias="responseFormat",
        description=(
            "Response format: 'geojson' for GeoJSON, " "'pbf' for Protocol Buffer (MVT)"
        ),
    )
    force_refresh: bool = Field(
        default=False,
        alias="forceRefresh",
        description="If true, bypass cache and fetch fresh data",
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ResponseMeta(BaseModel):
    dataset: str = Field(default="XKT001")
    source: str = Field(default="reinfolib.mlit.go.jp")
    cache_hit: bool = Field(alias="cacheHit")
    size_bytes: int = Field(alias="sizeBytes")
    is_resource: bool = Field(alias="isResource")
    format: str

    model_config = ConfigDict(populate_by_name=True)


class FetchUrbanPlanningZonesResponse(BaseModel):
    geojson: dict[str, Any] | None = None
    pbf_base64: str | None = Field(default=None, alias="pbfBase64")
    resource_uri: str | None = Field(default=None, alias="resourceUri")
    meta: ResponseMeta

    model_config = ConfigDict(populate_by_name=True)


class FetchUrbanPlanningZonesTool:
    """Tool implementation for fetching urban zones from MLIT XKT011 API."""

    name = "mlit.fetch_urban_planning_zones"
    description = (
        "Fetch urban planning zone (都市計画区域) data from MLIT dataset XKT011. "
        "Supports both GeoJSON and PBF (Protocol Buffer) formats. "
        "Requires either z/x/y tile coordinates or a bounding box."
    )
    input_model = FetchUrbanPlanningZonesInput
    output_model = FetchUrbanPlanningZonesResponse

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

    async def run(
        self, payload: FetchUrbanPlanningZonesInput
    ) -> FetchUrbanPlanningZonesResponse:
        params = {
            "response_format": payload.response_format,
            "z": payload.z,
            "x": payload.x,
            "y": payload.y,
        }

        fetch_result = await self._http_client.fetch(
            "XKT001",
            params=params,
            response_format=payload.response_format,
            force_refresh=payload.force_refresh,
        )

        # Determine response size
        if fetch_result.file_path:
            size_bytes = fetch_result.file_path.stat().st_size
            is_large = size_bytes > RESOURCE_THRESHOLD_BYTES
        else:
            # Data is in memory
            if isinstance(fetch_result.data, bytes):
                size_bytes = len(fetch_result.data)
            else:
                # Assume JSON/Dict
                json_str = json.dumps(fetch_result.data)
                size_bytes = len(json_str.encode("utf-8"))
            is_large = size_bytes > RESOURCE_THRESHOLD_BYTES

        logger.info(
            "fetch_urban_planning_zones",
            extra={
                "z": payload.z,
                "x": payload.x,
                "y": payload.y,
                "format": payload.response_format,
                "cache_hit": fetch_result.from_cache,
                "size_bytes": size_bytes,
                "is_resource": is_large,
            },
        )

        meta = ResponseMeta(
            cacheHit=fetch_result.from_cache,
            format=payload.response_format,
            sizeBytes=size_bytes,
            isResource=is_large,
        )

        if is_large and fetch_result.file_path:
            # Return as resource URI
            fname = fetch_result.file_path.name
            resource_uri = f"resource://mlit/urban_planning_zones/{fname}"
            return FetchUrbanPlanningZonesResponse(
                resourceUri=resource_uri,
                meta=meta,
            )

        # Load data if not large and data is missing (e.g., cached as file)
        geojson_data = fetch_result.data
        if not geojson_data and fetch_result.file_path and not is_large:
            try:
                content = fetch_result.file_path.read_bytes()
                geojson_data = json.loads(content)
            except Exception as e:
                logger.error(f"Failed to read/parse file {fetch_result.file_path}: {e}")
                # Fallback to None or raise? None is safer here.


        if payload.response_format == "pbf":
            # Read PBF file and encode to base64
            if fetch_result.file_path:
                pbf_content = fetch_result.file_path.read_bytes()
            else:
                # If data is in memory
                pbf_content = (
                    fetch_result.data if isinstance(fetch_result.data, bytes) else b""
                )

            pbf_base64 = encode_mvt_to_base64(pbf_content)
            return FetchUrbanPlanningZonesResponse(
                pbfBase64=pbf_base64,
                meta=meta,
            )
        else:
            # GeoJSON format
            return FetchUrbanPlanningZonesResponse(
                geojson=geojson_data,
                meta=meta,
            )


__all__ = [
    "FetchUrbanPlanningZonesInput",
    "FetchUrbanPlanningZonesResponse",
    "FetchUrbanPlanningZonesTool",
]
