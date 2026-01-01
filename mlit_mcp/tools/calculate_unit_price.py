from __future__ import annotations

import logging
from collections import defaultdict
from statistics import median
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mlit_mcp.http_client import MLITHttpClient

logger = logging.getLogger(__name__)

# Conversion factor: 1 tsubo = 3.30578 sqm
TSUBO_TO_SQM = 3.30578


class CalculateUnitPriceInput(BaseModel):
    """Input schema for the calculate_unit_price tool."""

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


class TypeUnitPrice(BaseModel):
    """Unit price statistics for a property type."""

    count: int
    avg_price_per_sqm: int = Field(alias="avgPricePerSqm")
    avg_price_per_tsubo: int = Field(alias="avgPricePerTsubo")
    median_price_per_sqm: int | None = Field(default=None, alias="medianPricePerSqm")

    model_config = ConfigDict(populate_by_name=True)


class CalculateUnitPriceResponse(BaseModel):
    """Response schema for calculate_unit_price tool."""

    record_count: int = Field(alias="recordCount")
    avg_price_per_sqm: int | None = Field(default=None, alias="avgPricePerSqm")
    avg_price_per_tsubo: int | None = Field(default=None, alias="avgPricePerTsubo")
    median_price_per_sqm: int | None = Field(default=None, alias="medianPricePerSqm")
    median_price_per_tsubo: int | None = Field(
        default=None, alias="medianPricePerTsubo"
    )
    min_price_per_sqm: int | None = Field(default=None, alias="minPricePerSqm")
    max_price_per_sqm: int | None = Field(default=None, alias="maxPricePerSqm")
    by_type: dict[str, dict[str, Any]] = Field(
        default_factory=dict, alias="byType", description="Unit prices by property type"
    )

    model_config = ConfigDict(populate_by_name=True)


class CalculateUnitPriceTool:
    """Tool for calculating unit prices (per sqm and per tsubo)."""

    name = "mlit.calculate_unit_price"
    description = (
        "Calculate unit prices (price per square meter and price per tsubo) "
        "from real estate transaction data. Returns average, median, and "
        "distribution by property type."
    )
    input_model = CalculateUnitPriceInput
    output_model = CalculateUnitPriceResponse

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

    async def run(self, payload: CalculateUnitPriceInput) -> CalculateUnitPriceResponse:
        all_data = []

        # Determine if area is prefecture or city
        params_base = {}
        if len(payload.area) == 2:
            params_base["area"] = payload.area
        else:
            params_base["city"] = payload.area

        if payload.classification:
            params_base["priceClassification"] = payload.classification

        for year in range(payload.from_year, payload.to_year + 1):
            params = params_base.copy()
            params["year"] = str(year)

            fetch_result = await self._http_client.fetch(
                "XIT001",
                params=params,
                response_format="json",
                force_refresh=payload.force_refresh,
            )

            year_data = fetch_result.data
            if isinstance(year_data, dict):
                if "data" in year_data and isinstance(year_data["data"], list):
                    all_data.extend(year_data["data"])
            elif isinstance(year_data, list):
                all_data.extend(year_data)

        # Calculate unit prices
        prices_per_sqm: list[float] = []
        type_prices: dict[str, list[float]] = defaultdict(list)

        for record in all_data:
            price_str = record.get("TradePrice")
            area_str = record.get("Area")

            if price_str and area_str:
                try:
                    price = float(price_str)
                    area_val = float(area_str)
                    if area_val > 0:
                        price_per_sqm = price / area_val
                        prices_per_sqm.append(price_per_sqm)

                        # Group by type
                        prop_type = record.get("Type", "Unknown")
                        type_prices[prop_type].append(price_per_sqm)
                except (ValueError, TypeError):
                    pass

        # Calculate statistics
        record_count = len(prices_per_sqm)
        avg_per_sqm = (
            int(sum(prices_per_sqm) / len(prices_per_sqm)) if prices_per_sqm else None
        )
        avg_per_tsubo = int(avg_per_sqm * TSUBO_TO_SQM) if avg_per_sqm else None
        median_per_sqm = int(median(prices_per_sqm)) if prices_per_sqm else None
        median_per_tsubo = (
            int(median_per_sqm * TSUBO_TO_SQM) if median_per_sqm else None
        )
        min_per_sqm = int(min(prices_per_sqm)) if prices_per_sqm else None
        max_per_sqm = int(max(prices_per_sqm)) if prices_per_sqm else None

        # Calculate by type
        by_type: dict[str, dict[str, Any]] = {}
        for prop_type, prices in type_prices.items():
            avg = int(sum(prices) / len(prices))
            by_type[prop_type] = {
                "count": len(prices),
                "avgPricePerSqm": avg,
                "avgPricePerTsubo": int(avg * TSUBO_TO_SQM),
                "medianPricePerSqm": int(median(prices)) if len(prices) > 0 else None,
            }

        logger.info(
            "calculate_unit_price",
            extra={
                "from_year": payload.from_year,
                "to_year": payload.to_year,
                "area": payload.area,
                "record_count": record_count,
            },
        )

        return CalculateUnitPriceResponse(
            recordCount=record_count,
            avgPricePerSqm=avg_per_sqm,
            avgPricePerTsubo=avg_per_tsubo,
            medianPricePerSqm=median_per_sqm,
            medianPricePerTsubo=median_per_tsubo,
            minPricePerSqm=min_per_sqm,
            maxPricePerSqm=max_per_sqm,
            byType=by_type,
        )


__all__ = [
    "CalculateUnitPriceInput",
    "CalculateUnitPriceResponse",
    "CalculateUnitPriceTool",
]
