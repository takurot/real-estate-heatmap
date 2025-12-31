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


class FetchSchoolDistrictsInput(BaseModel):
    """Input schema for the fetch_school_districts tool."""

    z: int = Field(description="Zoom level (11-15)", ge=11, le=15)
    x: int = Field(description="Tile X coordinate", ge=0)
    y: int = Field(description="Tile Y coordinate", ge=0)
    administrative_area_code: str | None = Field(
        default=None,
        alias="administrativeAreaCode",
        description=(
            "5-digit administrative area code "
            "(optional, can be comma-separated for multiple codes)"
        ),
    )
    # fmt: off
    response_format: Literal["geojson", "pbf"] = Field(
        default="geojson",
        alias="responseFormat",
        description=(
            "Response format: 'geojson' for GeoJSON, "
            "'pbf' for Protocol Buffer (MVT)"
        ),
    )
    # fmt: on
    force_refresh: bool = Field(
        default=False,
        alias="forceRefresh",
        description="If true, bypass cache and fetch fresh data",
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ResponseMeta(BaseModel):
    dataset: str = Field(default="XKT004")
    source: str = Field(default="reinfolib.mlit.go.jp")
    cache_hit: bool = Field(alias="cacheHit")
    size_bytes: int = Field(alias="sizeBytes")
    is_resource: bool = Field(alias="isResource")
    format: str

    model_config = ConfigDict(populate_by_name=True)


class FetchSchoolDistrictsResponse(BaseModel):
    mvt_base64: str | None = Field(
        default=None,
        alias="mvtBase64",
        description="Base64-encoded MVT tile data",
    )
    geojson: dict[str, Any] | None = None
    resource_uri: str | None = Field(default=None, alias="resourceUri")
    meta: ResponseMeta

    model_config = ConfigDict(populate_by_name=True)


class FetchSchoolDistrictsTool:
    """Tool for fetching school district tiles from MLIT XKT004 API."""

    name = "mlit.fetch_school_districts"
    description = (
        "Fetch elementary school district (小学校区) tile data "
        "from MLIT dataset XKT004. "
        "Returns MVT (Mapbox Vector Tile) data encoded as base64. "
        "Supports optional administrative area code filtering."
    )
    input_model = FetchSchoolDistrictsInput
    output_model = FetchSchoolDistrictsResponse

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
        self, payload: FetchSchoolDistrictsInput
    ) -> FetchSchoolDistrictsResponse:
        params: dict[str, str | int] = {
            "response_format": payload.response_format,
            "z": payload.z,
            "x": payload.x,
            "y": payload.y,
        }

        if payload.administrative_area_code:
            params["administrativeAreaCode"] = payload.administrative_area_code

        fetch_result = await self._http_client.fetch(
            "XKT004",
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
            "fetch_school_districts",
            extra={
                "z": payload.z,
                "x": payload.x,
                "y": payload.y,
                "administrative_area_code": payload.administrative_area_code,
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
            resource_uri = f"resource://mlit/school_districts/{fname}"
            return FetchSchoolDistrictsResponse(
                resourceUri=resource_uri,
                meta=meta,
            )

        if payload.response_format == "pbf":
            # Read MVT/PBF file and encode to base64
            if fetch_result.file_path:
                mvt_content = fetch_result.file_path.read_bytes()
            else:
                # fmt: off
                mvt_content = (
                    fetch_result.data
                    if isinstance(fetch_result.data, bytes)
                    else b""
                )
                # fmt: on

            mvt_base64 = encode_mvt_to_base64(mvt_content)
            return FetchSchoolDistrictsResponse(
                mvtBase64=mvt_base64,
                meta=meta,
            )
        else:
            # GeoJSON format
            # If data is in a file, read it (only if it's a JSON/GeoJSON file)
            if fetch_result.file_path and not fetch_result.data:
                file_ext = fetch_result.file_path.suffix.lower()
                if file_ext in (".json", ".geojson"):
                    with open(fetch_result.file_path, "r", encoding="utf-8") as f:
                        geojson_data = json.load(f)
                else:
                    # File is not GeoJSON format (e.g., MVT), cannot parse
                    logger.warning(
                        "Expected GeoJSON file but got %s, returning None",
                        file_ext,
                    )
                    geojson_data = None
            else:
                geojson_data = fetch_result.data

            return FetchSchoolDistrictsResponse(
                geojson=geojson_data,
                meta=meta,
            )


__all__ = [
    "FetchSchoolDistrictsInput",
    "FetchSchoolDistrictsResponse",
    "FetchSchoolDistrictsTool",
]
