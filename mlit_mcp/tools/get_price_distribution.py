from __future__ import annotations

import logging
from statistics import quantiles, median
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mlit_mcp.http_client import MLITHttpClient

logger = logging.getLogger(__name__)


class GetPriceDistributionInput(BaseModel):
    """Input schema for the get_price_distribution tool."""

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
    num_bins: int = Field(
        default=10,
        alias="numBins",
        description="Number of histogram bins (default 10)",
        ge=2,
        le=50,
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


class PriceBin(BaseModel):
    """A single price bin in the histogram."""

    min_value: int = Field(alias="minValue")
    max_value: int = Field(alias="maxValue")
    label: str = Field(description="Human-readable label for the bin")
    count: int = Field(description="Actual count of transactions in this bin")
    cumulative_percent: float = Field(alias="cumulativePercent")

    model_config = ConfigDict(populate_by_name=True)


class GetPriceDistributionResponse(BaseModel):
    """Response schema for get_price_distribution tool."""

    total_count: int = Field(alias="totalCount")
    min_price: int | None = Field(default=None, alias="minPrice")
    max_price: int | None = Field(default=None, alias="maxPrice")
    percentile_25: int | None = Field(default=None, alias="percentile25")
    percentile_50: int | None = Field(
        default=None, alias="percentile50", description="Median"
    )
    percentile_75: int | None = Field(default=None, alias="percentile75")
    bins: list[PriceBin] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class GetPriceDistributionTool:
    """Tool for generating price distribution histograms."""

    name = "mlit.get_price_distribution"
    description = (
        "Generate price distribution histogram from transaction data. "
        "Returns bin counts, cumulative distribution, and percentiles. "
        "Useful for understanding price range distribution in an area."
    )
    input_model = GetPriceDistributionInput
    output_model = GetPriceDistributionResponse

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
        self, payload: GetPriceDistributionInput
    ) -> GetPriceDistributionResponse:
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

        # Extract prices
        prices: list[int] = []
        for record in all_data:
            price_str = record.get("TradePrice")
            if price_str:
                try:
                    prices.append(int(price_str))
                except (ValueError, TypeError):
                    pass

        record_count = len(prices)
        if record_count == 0:
            return GetPriceDistributionResponse(
                totalCount=0,
                bins=[],
            )

        prices.sort()
        min_price = prices[0]
        max_price = prices[-1]

        # Calculate percentiles
        percentile_25 = None
        percentile_75 = None
        median_price = int(median(prices))

        if record_count >= 4:
            try:
                q = quantiles(prices, n=4)
                percentile_25 = int(q[0])
                percentile_75 = int(q[2])
            except Exception:
                pass  # Fallback if quantiles fails

        # Generate bins
        price_range = max_price - min_price
        # Avoid division by zero
        num_bins = payload.num_bins
        if price_range == 0:
            # All prices equal
            bin_size = 1
            num_bins = 1
        else:
            bin_size = price_range / num_bins

        bin_counts = [0] * num_bins

        for price in prices:
            if price_range == 0:
                bin_counts[0] += 1
                continue

            idx = int((price - min_price) / bin_size)
            if idx >= num_bins:
                idx = num_bins - 1
            bin_counts[idx] += 1

        bins: list[PriceBin] = []
        cumulative_count = 0

        for i in range(num_bins):
            bin_min = int(min_price + i * bin_size)
            bin_max = int(min_price + (i + 1) * bin_size)
            # Ensure last bin max matches max_price exactly for display
            if i == num_bins - 1:
                bin_max = max_price

            count = bin_counts[i]
            cumulative_count += count
            cumulative_percent = round((cumulative_count / record_count) * 100, 1)

            # Format label (in 万円)
            label = f"{bin_min // 10000}万〜{bin_max // 10000}万"

            bins.append(
                PriceBin(
                    minValue=bin_min,
                    maxValue=bin_max,
                    label=label,
                    count=count,
                    cumulativePercent=cumulative_percent,
                )
            )

        logger.info(
            "get_price_distribution",
            extra={
                "from_year": payload.from_year,
                "to_year": payload.to_year,
                "area": payload.area,
                "num_bins": payload.num_bins,
                "total_count": record_count,
            },
        )

        return GetPriceDistributionResponse(
            totalCount=record_count,
            minPrice=min_price,
            maxPrice=max_price,
            percentile25=percentile_25,
            percentile50=median_price,
            percentile75=percentile_75,
            bins=bins,
        )


__all__ = [
    "GetPriceDistributionInput",
    "GetPriceDistributionResponse",
    "GetPriceDistributionTool",
    "PriceBin",
]
