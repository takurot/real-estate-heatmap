"""Tool for generating comprehensive area reports."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mlit_mcp.http_client import MLITHttpClient
from .gis_helpers import lat_lon_to_tile

logger = logging.getLogger(__name__)


class GenerateAreaReportInput(BaseModel):
    """Input schema for the generate_area_report tool."""

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


class GenerateAreaReportResponse(BaseModel):
    """Response schema for the generate_area_report tool."""

    latitude: float
    longitude: float
    report: str = Field(
        description="Markdown-formatted area report",
    )
    sections: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured data by section",
    )

    model_config = ConfigDict(populate_by_name=True)


class GenerateAreaReportTool:
    """Tool for generating comprehensive area reports."""

    name = "mlit.generate_area_report"
    description = (
        "Generate a comprehensive area analysis report for a specific location. "
        "Aggregates data from multiple sources: hazard risks, amenities, "
        "population trends, and station access. "
        "Returns a formatted Markdown report."
    )
    input_model = GenerateAreaReportInput
    output_model = GenerateAreaReportResponse

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

    async def run(self, payload: GenerateAreaReportInput) -> GenerateAreaReportResponse:
        """Execute the tool with validated input."""
        sections: dict[str, Any] = {}
        report_parts: list[str] = []

        lat, lon = payload.latitude, payload.longitude
        Z = 14
        x, y = lat_lon_to_tile(lat, lon, Z)

        report_parts.append(f"# Area Analysis Report")
        report_parts.append(f"**Location**: {lat:.4f}, {lon:.4f}")
        report_parts.append(f"**Tile**: z={Z}, x={x}, y={y}")
        report_parts.append("")

        # Section 1: Hazard Risks
        try:
            from .fetch_safety_info import FetchSafetyInfoInput, FetchSafetyInfoTool

            safety_tool = FetchSafetyInfoTool(http_client=self._http_client)
            safety_input = FetchSafetyInfoInput(
                latitude=lat,
                longitude=lon,
                forceRefresh=payload.force_refresh,
            )
            safety_result = await safety_tool.run(safety_input)

            sections["safety"] = {
                "summary": safety_result.summary,
                "data_count": {k: len(v) for k, v in safety_result.safety_info.items()},
            }

            report_parts.append("## Safety Information")
            for line in safety_result.summary:
                report_parts.append(f"- {line}")
            report_parts.append("")

        except Exception as e:
            logger.warning(f"Failed to fetch safety info: {e}")
            report_parts.append("## Safety Information")
            report_parts.append(f"*Data unavailable: {e}*")
            report_parts.append("")

        # Section 2: Nearby Amenities
        try:
            from .fetch_nearby_amenities import (
                FetchNearbyAmenitiesInput,
                FetchNearbyAmenitiesTool,
            )

            amenity_tool = FetchNearbyAmenitiesTool(http_client=self._http_client)
            amenity_input = FetchNearbyAmenitiesInput(
                latitude=lat,
                longitude=lon,
                forceRefresh=payload.force_refresh,
            )
            amenity_result = await amenity_tool.run(amenity_input)

            sections["amenities"] = {
                "summary": amenity_result.summary,
                "counts": {k: len(v) for k, v in amenity_result.amenities.items()},
            }

            report_parts.append("## Nearby Amenities")
            for line in amenity_result.summary:
                report_parts.append(f"- {line}")
            report_parts.append("")

        except Exception as e:
            logger.warning(f"Failed to fetch amenities: {e}")
            report_parts.append("## Nearby Amenities")
            report_parts.append(f"*Data unavailable: {e}*")
            report_parts.append("")

        # Section 3: Population Trend
        try:
            from .fetch_population_trend import (
                FetchPopulationTrendInput,
                FetchPopulationTrendTool,
            )

            pop_tool = FetchPopulationTrendTool(http_client=self._http_client)
            pop_input = FetchPopulationTrendInput(
                latitude=lat,
                longitude=lon,
                forceRefresh=payload.force_refresh,
            )
            pop_result = await pop_tool.run(pop_input)

            sections["population"] = {
                "summary": pop_result.summary,
                "mesh_count": len(pop_result.mesh_data),
            }

            report_parts.append("## Population Trends")
            for line in pop_result.summary:
                report_parts.append(f"- {line}")
            report_parts.append("")

        except Exception as e:
            logger.warning(f"Failed to fetch population data: {e}")
            report_parts.append("## Population Trends")
            report_parts.append(f"*Data unavailable: {e}*")
            report_parts.append("")

        # Section 4: Station Access
        try:
            from .fetch_station_stats import (
                FetchStationStatsInput,
                FetchStationStatsTool,
            )

            station_tool = FetchStationStatsTool(http_client=self._http_client)
            station_input = FetchStationStatsInput(
                latitude=lat,
                longitude=lon,
                forceRefresh=payload.force_refresh,
            )
            station_result = await station_tool.run(station_input)

            sections["stations"] = {
                "summary": station_result.summary,
                "station_count": len(station_result.stations),
            }

            report_parts.append("## Station Access")
            for line in station_result.summary:
                report_parts.append(f"- {line}")
            if station_result.stations:
                report_parts.append("")
                report_parts.append("### Nearby Stations")
                for station in station_result.stations[:5]:
                    name = station.get("station_name", "Unknown")
                    line_name = station.get("line_name", "")
                    passengers = station.get("passenger_count")
                    if passengers:
                        report_parts.append(
                            f"- **{name}** ({line_name}): "
                            f"{passengers:,} passengers/day"
                        )
                    else:
                        report_parts.append(f"- **{name}** ({line_name})")
            report_parts.append("")

        except Exception as e:
            logger.warning(f"Failed to fetch station data: {e}")
            report_parts.append("## Station Access")
            report_parts.append(f"*Data unavailable: {e}*")
            report_parts.append("")

        report = "\n".join(report_parts)

        return GenerateAreaReportResponse(
            latitude=payload.latitude,
            longitude=payload.longitude,
            report=report,
            sections=sections,
        )


__all__ = [
    "GenerateAreaReportInput",
    "GenerateAreaReportResponse",
    "GenerateAreaReportTool",
]
