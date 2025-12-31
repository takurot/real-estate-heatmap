from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mlit_mcp.http_client import MLITHttpClient

logger = logging.getLogger(__name__)

# Threshold for switching to resource URI (1MB)
RESOURCE_THRESHOLD_BYTES = 1024 * 1024


class BoundingBox(BaseModel):
    """Bounding box for filtering GeoJSON features."""

    min_lon: float = Field(alias="minLon", ge=-180, le=180)
    min_lat: float = Field(alias="minLat", ge=-90, le=90)
    max_lon: float = Field(alias="maxLon", ge=-180, le=180)
    max_lat: float = Field(alias="maxLat", ge=-90, le=90)

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("max_lon")
    @classmethod
    def validate_lon_range(cls, max_lon: float, info) -> float:
        min_lon = info.data.get("min_lon")
        if min_lon is not None and max_lon < min_lon:
            raise ValueError(f"maxLon ({max_lon}) must be >= minLon ({min_lon})")
        return max_lon

    @field_validator("max_lat")
    @classmethod
    def validate_lat_range(cls, max_lat: float, info) -> float:
        min_lat = info.data.get("min_lat")
        if min_lat is not None and max_lat < min_lat:
            raise ValueError(f"maxLat ({max_lat}) must be >= minLat ({min_lat})")
        return max_lat


class FetchTransactionPointsInput(BaseModel):
    """Input schema for the fetch_transaction_points tool.

    Uses XYZ tile coordinates as required by the MLIT XPT001 API.
    """

    z: int = Field(description="Zoom level (11-15)", ge=11, le=15)
    x: int = Field(description="Tile X coordinate", ge=0)
    y: int = Field(description="Tile Y coordinate", ge=0)
    from_quarter: str = Field(
        alias="fromQuarter",
        description="Start quarter in YYYYN format (e.g., 20231 for Q1 2023)",
        pattern=r"^\d{5}$",
    )
    to_quarter: str = Field(
        alias="toQuarter",
        description="End quarter in YYYYN format (e.g., 20244 for Q4 2024)",
        pattern=r"^\d{5}$",
    )
    response_format: Literal["geojson", "pbf"] = Field(
        default="geojson",
        alias="responseFormat",
        description="Response format: 'geojson' or 'pbf'",
    )
    price_classification: str | None = Field(
        default=None,
        alias="priceClassification",
        description="Price classification (01=transaction, 02=contract, None=both)",
    )
    land_type_code: str | None = Field(
        default=None,
        alias="landTypeCode",
        description="Land type codes, comma-separated (e.g., '01,02,07')",
    )
    bbox: BoundingBox | None = Field(
        default=None,
        description="Optional bounding box filter for GeoJSON features",
    )
    force_refresh: bool = Field(
        default=False,
        alias="forceRefresh",
        description="If true, bypass cache and fetch fresh data",
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("to_quarter")
    @classmethod
    def validate_quarter_range(cls, to_quarter: str, info) -> str:
        from_quarter = info.data.get("from_quarter")
        if from_quarter is not None and to_quarter < from_quarter:
            raise ValueError(
                f"toQuarter ({to_quarter}) must be >= fromQuarter ({from_quarter})"
            )
        return to_quarter


class ResponseMeta(BaseModel):
    dataset: str = Field(default="XPT001")
    source: str = Field(default="reinfolib.mlit.go.jp")
    cache_hit: bool = Field(alias="cacheHit")
    size_bytes: int = Field(alias="sizeBytes")
    is_resource: bool = Field(alias="isResource")

    model_config = ConfigDict(populate_by_name=True)


class FetchTransactionPointsResponse(BaseModel):
    geojson: dict[str, Any] | None = None
    resource_uri: str | None = Field(default=None, alias="resourceUri")
    meta: ResponseMeta

    model_config = ConfigDict(populate_by_name=True)


class FetchTransactionPointsTool:
    """Tool implementation for fetching transaction points as GeoJSON.

    Uses MLIT XPT001 API with XYZ tile coordinates.
    """

    name = "mlit.fetch_transaction_points"
    description = (
        "Fetch real estate transaction points as GeoJSON from MLIT dataset XPT001. "
        "Requires XYZ tile coordinates (z/x/y). "
        "Large responses (>1MB) are returned as resource URIs."
    )
    input_model = FetchTransactionPointsInput
    output_model = FetchTransactionPointsResponse

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
        self, payload: FetchTransactionPointsInput
    ) -> FetchTransactionPointsResponse:
        # Build API parameters per XPT001 specification
        params: dict[str, Any] = {
            "response_format": payload.response_format,
            "z": payload.z,
            "x": payload.x,
            "y": payload.y,
            "from": payload.from_quarter,
            "to": payload.to_quarter,
        }

        # Add optional parameters
        if payload.price_classification:
            params["priceClassification"] = payload.price_classification
        if payload.land_type_code:
            params["landTypeCode"] = payload.land_type_code

        fetch_result = await self._http_client.fetch(
            "XPT001",
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
            geojson_str = json.dumps(fetch_result.data)
            size_bytes = len(geojson_str.encode("utf-8"))
            is_large = size_bytes > RESOURCE_THRESHOLD_BYTES

        # Apply bbox filter if provided (only for geojson format)
        geojson_data = fetch_result.data
        if not geojson_data and fetch_result.file_path and not is_large:
            try:
                content = fetch_result.file_path.read_bytes()
                geojson_data = json.loads(content)
            except Exception as e:
                logger.error(f"Failed to read/parse file {fetch_result.file_path}: {e}")

        if payload.bbox and geojson_data and payload.response_format == "geojson":
            geojson_data = self._filter_by_bbox(geojson_data, payload.bbox)

        logger.info(
            "fetch_transaction_points",
            extra={
                "z": payload.z,
                "x": payload.x,
                "y": payload.y,
                "from_quarter": payload.from_quarter,
                "to_quarter": payload.to_quarter,
                "size_bytes": size_bytes,
                "is_resource": is_large,
                "cache_hit": fetch_result.from_cache,
            },
        )

        meta = ResponseMeta(
            cacheHit=fetch_result.from_cache,
            sizeBytes=size_bytes,
            isResource=is_large,
        )

        if is_large and fetch_result.file_path:
            # Return as resource URI
            resource_uri = (
                f"resource://mlit/transaction_points/{fetch_result.file_path.name}"
            )
            return FetchTransactionPointsResponse(
                resourceUri=resource_uri,
                meta=meta,
            )
        else:
            # Return inline GeoJSON
            return FetchTransactionPointsResponse(
                geojson=geojson_data,
                meta=meta,
            )

    def _filter_by_bbox(
        self, geojson: dict[str, Any], bbox: BoundingBox
    ) -> dict[str, Any]:
        """Filter GeoJSON features by bounding box."""
        if not isinstance(geojson, dict) or "features" not in geojson:
            return geojson

        filtered_features = []
        for feature in geojson.get("features", []):
            if self._is_in_bbox(feature, bbox):
                filtered_features.append(feature)

        return {
            **geojson,
            "features": filtered_features,
        }

    def _is_in_bbox(self, feature: dict[str, Any], bbox: BoundingBox) -> bool:
        """Check if a GeoJSON feature is within the bounding box."""
        geometry = feature.get("geometry")
        if not geometry or geometry.get("type") != "Point":
            return True  # Include non-point features

        coordinates = geometry.get("coordinates")
        if not coordinates or len(coordinates) < 2:
            return True

        lon, lat = coordinates[0], coordinates[1]
        return (
            bbox.min_lon <= lon <= bbox.max_lon and bbox.min_lat <= lat <= bbox.max_lat
        )


__all__ = [
    "FetchTransactionPointsInput",
    "FetchTransactionPointsResponse",
    "FetchTransactionPointsTool",
    "BoundingBox",
]
