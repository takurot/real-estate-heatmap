from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mlit_mcp.http_client import MLITHttpClient
from mlit_mcp.tools.summarize_transactions import (
    SummarizeTransactionsInput,
    SummarizeTransactionsTool,
)

logger = logging.getLogger(__name__)


class CompareAreasInput(BaseModel):
    """Input schema for the compare_areas tool."""

    areas: list[str] = Field(
        description="List of area codes (2-digit prefecture or 5-digit city codes)"
    )
    from_year: int = Field(
        alias="fromYear",
        description="Starting year (e.g. 2015)",
        ge=2005,
        le=2030,
    )
    to_year: int = Field(
        alias="toYear",
        description="Ending year (e.g. 2024)",
        ge=2005,
        le=2030,
    )
    classification: str | None = Field(
        default=None,
        description=(
            "Transaction classification code (optional). "
            "01: Transaction Price, "
            "02: Contract Price"
        ),
    )
    force_refresh: bool = Field(
        default=False,
        alias="forceRefresh",
        description="If true, bypass cache and fetch fresh data",
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("to_year")
    @classmethod
    def validate_year_range(cls, to_year: int, info) -> int:
        from_year = info.data.get("from_year")
        if from_year is not None and to_year < from_year:
            raise ValueError(f"toYear ({to_year}) must be >= fromYear ({from_year})")
        return to_year

    @field_validator("areas")
    @classmethod
    def validate_areas(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one area code is required")
        for area in v:
            if not area.isdigit():
                raise ValueError(f"Area code must be numeric: {area}")
            if len(area) not in (2, 5):
                raise ValueError(
                    f"Area code must be 2 digits (prefecture) or 5 digits (city): {area}"
                )
        return v


class AreaStats(BaseModel):
    """Statistics for a single area."""

    area: str = Field(description="Area code")
    record_count: int = Field(alias="recordCount")
    average_price: int | None = Field(default=None, alias="averagePrice")
    median_price: int | None = Field(default=None, alias="medianPrice")
    min_price: int | None = Field(default=None, alias="minPrice")
    max_price: int | None = Field(default=None, alias="maxPrice")
    price_change: float | None = Field(
        default=None,
        alias="priceChange",
        description="Price change ratio from first to last year",
    )

    model_config = ConfigDict(populate_by_name=True)


class CompareAreasResponse(BaseModel):
    """Response schema for compare_areas tool."""

    area_stats: list[AreaStats] = Field(alias="areaStats")
    ranking_by_price: list[str] = Field(
        alias="rankingByPrice", description="Areas ranked by average price (descending)"
    )
    ranking_by_count: list[str] = Field(
        alias="rankingByCount",
        description="Areas ranked by transaction count (descending)",
    )

    model_config = ConfigDict(populate_by_name=True)


class CompareAreasTool:
    """Tool for comparing multiple areas by price and transaction volume."""

    name = "mlit.compare_areas"
    description = (
        "Compare multiple areas by average price and transaction count. "
        "Returns statistics for each area and rankings. "
        "Useful for market analysis across different regions."
    )
    input_model = CompareAreasInput
    output_model = CompareAreasResponse

    def __init__(self, http_client: MLITHttpClient) -> None:
        self._http_client = http_client
        self._summarize_tool = SummarizeTransactionsTool(http_client)

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

    async def run(self, payload: CompareAreasInput) -> CompareAreasResponse:
        async def process_area(area: str) -> AreaStats:
            summary_input = SummarizeTransactionsInput(
                fromYear=payload.from_year,
                toYear=payload.to_year,
                area=area,
                classification=payload.classification,
                forceRefresh=payload.force_refresh,
            )
            summary = await self._summarize_tool.run(summary_input)

            # Calculate price change
            price_change = None
            if summary.price_by_year:
                sorted_years = sorted(summary.price_by_year.keys())
                if len(sorted_years) >= 2:
                    first_price = summary.price_by_year[sorted_years[0]]
                    last_price = summary.price_by_year[sorted_years[-1]]
                    if first_price > 0:
                        price_change = round(
                            (last_price - first_price) / first_price, 4
                        )

            return AreaStats(
                area=area,
                recordCount=summary.record_count,
                averagePrice=summary.average_price,
                medianPrice=summary.median_price,
                minPrice=summary.min_price,
                maxPrice=summary.max_price,
                priceChange=price_change,
            )

        # Run summaries in parallel
        area_stats_list = await asyncio.gather(
            *(process_area(area) for area in payload.areas)
        )

        # Create rankings
        # Ranking by price (descending, None values at the end)
        ranked_by_price = sorted(
            area_stats_list,
            key=lambda x: x.average_price if x.average_price is not None else -1,
            reverse=True,
        )
        ranking_by_price = [s.area for s in ranked_by_price if s.average_price]
        # Add areas without price data at the end
        for s in area_stats_list:
            if s.area not in ranking_by_price:
                ranking_by_price.append(s.area)

        # Ranking by count (descending)
        ranked_by_count = sorted(
            area_stats_list,
            key=lambda x: x.record_count,
            reverse=True,
        )
        ranking_by_count = [s.area for s in ranked_by_count]

        logger.info(
            "compare_areas",
            extra={
                "areas": payload.areas,
                "from_year": payload.from_year,
                "to_year": payload.to_year,
                "num_areas": len(payload.areas),
            },
        )

        return CompareAreasResponse(
            areaStats=list(area_stats_list),
            rankingByPrice=ranking_by_price,
            rankingByCount=ranking_by_count,
        )


__all__ = [
    "CompareAreasInput",
    "CompareAreasResponse",
    "CompareAreasTool",
    "AreaStats",
]
