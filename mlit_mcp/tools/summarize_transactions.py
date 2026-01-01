from __future__ import annotations

import logging
import re
from collections import defaultdict
from statistics import median, stdev, variance, quantiles
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mlit_mcp.http_client import MLITHttpClient

logger = logging.getLogger(__name__)


class SummarizeTransactionsInput(BaseModel):
    """Input schema for the summarize_transactions tool."""

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


class ResponseMeta(BaseModel):
    dataset: str = Field(default="XIT001")
    source: str = Field(default="reinfolib.mlit.go.jp")
    cache_hit: bool = Field(alias="cacheHit")

    model_config = ConfigDict(populate_by_name=True)


class SummarizeTransactionsResponse(BaseModel):
    record_count: int = Field(alias="recordCount")
    average_price: int | None = Field(default=None, alias="averagePrice")
    median_price: int | None = Field(default=None, alias="medianPrice")
    min_price: int | None = Field(default=None, alias="minPrice")
    max_price: int | None = Field(default=None, alias="maxPrice")
    std_dev: int | None = Field(
        default=None, alias="stdDev", description="Standard deviation"
    )
    variance: int | None = Field(default=None, description="Variance")
    percentile_25: int | None = Field(
        default=None, alias="percentile25", description="25th percentile"
    )
    percentile_75: int | None = Field(
        default=None, alias="percentile75", description="75th percentile"
    )
    avg_price_per_sqm: int | None = Field(
        default=None,
        alias="avgPricePerSqm",
        description="Average price per square meter",
    )
    coefficient_of_variation: float | None = Field(
        default=None, alias="coefficientOfVariation", description="Std dev / mean"
    )
    price_by_year: dict[str, int] = Field(default_factory=dict, alias="priceByYear")
    count_by_year: dict[str, int] = Field(default_factory=dict, alias="countByYear")
    type_distribution: dict[str, int] = Field(
        default_factory=dict, alias="typeDistribution"
    )
    meta: ResponseMeta

    model_config = ConfigDict(populate_by_name=True)


class SummarizeTransactionsTool:
    """Tool for aggregating transaction statistics without returning raw data."""

    name = "mlit.summarize_transactions"
    description = (
        "Fetch and summarize real estate transaction data from MLIT dataset XIT001. "
        "Returns aggregated statistics (count, average, median, distribution) "
        "instead of raw data. Useful for large datasets that would overflow context."
    )
    input_model = SummarizeTransactionsInput
    output_model = SummarizeTransactionsResponse

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
        self, payload: SummarizeTransactionsInput
    ) -> SummarizeTransactionsResponse:
        all_data = []
        fetch_results = []

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
            fetch_results.append(fetch_result)

            year_data = fetch_result.data
            if isinstance(year_data, dict):
                if "data" in year_data and isinstance(year_data["data"], list):
                    all_data.extend(year_data["data"])
            elif isinstance(year_data, list):
                all_data.extend(year_data)

        # Aggregate statistics
        prices = []
        areas = []  # For price per sqm
        type_counts: dict[str, int] = defaultdict(int)
        year_prices: dict[str, list[int]] = defaultdict(list)
        year_counts: dict[str, int] = defaultdict(int)

        for record in all_data:
            # Extract price
            price_str = record.get("TradePrice")
            if price_str:
                try:
                    price = int(price_str)
                    prices.append(price)

                    # Extract year from Period (e.g., "2020年第1四半期")
                    period = record.get("Period", "")
                    year_match = re.match(r"(\d{4})年", period)
                    if year_match:
                        year_key = year_match.group(1)
                        year_prices[year_key].append(price)
                        year_counts[year_key] += 1

                    # Extract area for price per sqm
                    area_str = record.get("Area")
                    if area_str:
                        try:
                            area_val = float(area_str)
                            if area_val > 0:
                                areas.append((price, area_val))
                        except (ValueError, TypeError):
                            pass
                except (ValueError, TypeError):
                    pass

            # Count by type
            prop_type = record.get("Type")
            if prop_type:
                type_counts[prop_type] += 1

        # Calculate statistics
        record_count = len(all_data)
        average_price = int(sum(prices) / len(prices)) if prices else None
        median_price = int(median(prices)) if prices else None
        min_price = min(prices) if prices else None
        max_price = max(prices) if prices else None

        # Standard deviation and variance (requires at least 2 data points)
        std_dev_val = int(stdev(prices)) if len(prices) >= 2 else None
        variance_val = int(variance(prices)) if len(prices) >= 2 else None

        # Percentiles (requires at least 4 data points for quartiles)
        if len(prices) >= 4:
            q = quantiles(prices, n=4)  # Returns [Q1, Q2, Q3]
            percentile_25 = int(q[0])
            percentile_75 = int(q[2])
        else:
            percentile_25 = None
            percentile_75 = None

        # Coefficient of variation
        cv = (
            round(std_dev_val / average_price, 3)
            if std_dev_val and average_price
            else None
        )

        # Average price per sqm
        if areas:
            total_price_per_sqm = sum(p / a for p, a in areas)
            avg_price_per_sqm = int(total_price_per_sqm / len(areas))
        else:
            avg_price_per_sqm = None

        # Average price by year
        price_by_year = {
            year: int(sum(p) / len(p)) for year, p in year_prices.items() if p
        }

        # Count by year
        count_by_year = dict(year_counts)

        logger.info(
            "summarize_transactions",
            extra={
                "from_year": payload.from_year,
                "to_year": payload.to_year,
                "area": payload.area,
                "record_count": record_count,
            },
        )

        cache_hit_all = (
            all(res.from_cache for res in fetch_results) if fetch_results else False
        )
        meta = ResponseMeta(cacheHit=cache_hit_all)
        return SummarizeTransactionsResponse(
            recordCount=record_count,
            averagePrice=average_price,
            medianPrice=median_price,
            minPrice=min_price,
            maxPrice=max_price,
            stdDev=std_dev_val,
            variance=variance_val,
            percentile25=percentile_25,
            percentile75=percentile_75,
            avgPricePerSqm=avg_price_per_sqm,
            coefficientOfVariation=cv,
            priceByYear=price_by_year,
            countByYear=count_by_year,
            typeDistribution=dict(type_counts),
            meta=meta,
        )


__all__ = [
    "SummarizeTransactionsInput",
    "SummarizeTransactionsResponse",
    "SummarizeTransactionsTool",
]
