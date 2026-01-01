from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mlit_mcp.http_client import MLITHttpClient
from mlit_mcp.tools.summarize_transactions import (
    SummarizeTransactionsInput,
    SummarizeTransactionsTool,
)

logger = logging.getLogger(__name__)


class MarketTrend(str, Enum):
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    FLAT = "flat"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


class GetMarketTrendsInput(BaseModel):
    """Input schema for the get_market_trends tool."""

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
    area: str = Field(description="Area code (2-digit prefecture or 5-digit city code)")
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

    @field_validator("area")
    @classmethod
    def validate_area_code(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("Area code must be numeric")
        if len(v) not in (2, 5):
            raise ValueError(
                "Area code must be 2 digits (prefecture) or 5 digits (city)"
            )
        return v


class YearlyData(BaseModel):
    year: int
    price: int
    yoy_change: float | None = Field(default=None, alias="yoyChange")

    model_config = ConfigDict(populate_by_name=True)


class GetMarketTrendsResponse(BaseModel):
    cagr: float | None = Field(
        default=None, description="Compound Annual Growth Rate (e.g. 0.05 for 5%)"
    )
    average_yoy: float | None = Field(
        default=None, alias="averageYoy", description="Average Year-over-Year growth"
    )
    trend: MarketTrend = Field(description="Overall market trend")
    yearly_data: list[YearlyData] = Field(
        default_factory=list, alias="yearlyData", description="Yearly price data"
    )

    model_config = ConfigDict(populate_by_name=True)


class GetMarketTrendsTool:
    """Tool for analyzing market trends (CAGR, YoY) from transaction data."""

    name = "mlit.get_market_trends"
    description = (
        "Analyze market trends for a specific area and time range. "
        "Calculates CAGR (Compound Annual Growth Rate) and YoY (Year-over-Year) growth. "
        "Returns the overall trend (uptrend, downtrend, flat, etc.) and yearly data."
    )
    input_model = GetMarketTrendsInput
    output_model = GetMarketTrendsResponse

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

    async def run(self, payload: GetMarketTrendsInput) -> GetMarketTrendsResponse:
        # Reuse SummarizeTransactionsTool to fetch and aggregate data
        summary_input = SummarizeTransactionsInput(
            fromYear=payload.from_year,
            toYear=payload.to_year,
            area=payload.area,
            classification=payload.classification,
            forceRefresh=payload.force_refresh,
        )
        summary_result = await self._summarize_tool.run(summary_input)

        # Extract price by year
        price_by_year = summary_result.price_by_year
        if not price_by_year:
            return GetMarketTrendsResponse(trend=MarketTrend.UNKNOWN)

        # Sort years
        sorted_years = sorted([int(y) for y in price_by_year.keys()])
        yearly_data_list: list[YearlyData] = []

        # Calculate YoY
        previous_price = None
        yoy_changes = []

        for year in sorted_years:
            price = price_by_year[str(year)]
            yoy = None
            if previous_price is not None and previous_price > 0:
                yoy = (price - previous_price) / previous_price
                yoy_changes.append(yoy)

            yearly_data_list.append(
                YearlyData(
                    year=year,
                    price=price,
                    yoy_change=round(yoy, 4) if yoy is not None else None,
                )
            )
            previous_price = price

        # Calculate CAGR
        cagr = None
        first_year = sorted_years[0]
        last_year = sorted_years[-1]
        num_years = last_year - first_year

        if num_years > 0:
            first_price = price_by_year[str(first_year)]
            last_price = price_by_year[str(last_year)]
            if first_price > 0:
                cagr = (last_price / first_price) ** (1 / num_years) - 1

        # Calculate Average YoY
        avg_yoy = sum(yoy_changes) / len(yoy_changes) if yoy_changes else None

        # Determine Trend
        trend = MarketTrend.UNKNOWN
        if cagr is not None:
            if cagr >= 0.03:
                trend = MarketTrend.UPTREND
            elif cagr <= -0.03:
                trend = MarketTrend.DOWNTREND
            else:
                trend = MarketTrend.FLAT

            # Check for volatility (if std dev of yoy is high, maybe volatile? - simple check for now)
            # If sign of YoY flips frequently, it might be volatile.
            # keeping it simple based on CAGR for now as per plan.

        return GetMarketTrendsResponse(
            cagr=round(cagr, 4) if cagr is not None else None,
            averageYoy=round(avg_yoy, 4) if avg_yoy is not None else None,
            trend=trend,
            yearlyData=yearly_data_list,
        )


__all__ = [
    "GetMarketTrendsInput",
    "GetMarketTrendsResponse",
    "GetMarketTrendsTool",
    "MarketTrend",
]
