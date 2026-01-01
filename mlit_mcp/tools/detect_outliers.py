from __future__ import annotations

import logging
from enum import Enum
from statistics import mean, stdev, quantiles
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mlit_mcp.http_client import MLITHttpClient

logger = logging.getLogger(__name__)


class OutlierMethod(str, Enum):
    """Method for outlier detection."""

    IQR = "iqr"
    ZSCORE = "zscore"


class DetectOutliersInput(BaseModel):
    """Input schema for the detect_outliers tool."""

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
    method: OutlierMethod = Field(
        default=OutlierMethod.IQR,
        description="Detection method: 'iqr' (default) or 'zscore'",
    )
    threshold: float = Field(
        default=1.5,
        description="Threshold for detection. IQR: multiplier (default 1.5). Z-score: std devs (default 3)",
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


class OutlierRecord(BaseModel):
    """A single detected outlier."""

    price: int
    type: str | None = None
    period: str | None = None
    reason: str = Field(description="Why this was flagged as an outlier")

    model_config = ConfigDict(populate_by_name=True)


class DetectOutliersResponse(BaseModel):
    """Response schema for detect_outliers tool."""

    total_count: int = Field(alias="totalCount")
    outlier_count: int = Field(alias="outlierCount")
    outliers: list[OutlierRecord] = Field(
        default_factory=list, description="List of detected outliers (up to 100)"
    )
    avg_before_exclusion: int | None = Field(default=None, alias="avgBeforeExclusion")
    avg_after_exclusion: int | None = Field(default=None, alias="avgAfterExclusion")
    method: str
    threshold: float

    model_config = ConfigDict(populate_by_name=True)


class DetectOutliersTool:
    """Tool for detecting outlier transactions using IQR or Z-score methods."""

    name = "mlit.detect_outliers"
    description = (
        "Detect outlier transactions in real estate data using IQR or Z-score methods. "
        "Returns list of outliers and statistics before/after exclusion. "
        "Useful for identifying unusual transactions or data quality issues."
    )
    input_model = DetectOutliersInput
    output_model = DetectOutliersResponse

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

    async def run(self, payload: DetectOutliersInput) -> DetectOutliersResponse:
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

        # Extract prices with metadata
        records: list[tuple[int, dict]] = []
        for record in all_data:
            price_str = record.get("TradePrice")
            if price_str:
                try:
                    price = int(price_str)
                    records.append((price, record))
                except (ValueError, TypeError):
                    pass

        if not records:
            return DetectOutliersResponse(
                totalCount=0,
                outlierCount=0,
                outliers=[],
                method=payload.method.value,
                threshold=payload.threshold,
            )

        prices = [r[0] for r in records]
        total_count = len(prices)
        avg_before = int(mean(prices))

        # Detect outliers based on method
        outlier_indices = set()

        if payload.method == OutlierMethod.IQR:
            if len(prices) >= 4:
                q = quantiles(prices, n=4)
                q1, q3 = q[0], q[2]
                iqr = q3 - q1
                lower_bound = q1 - payload.threshold * iqr
                upper_bound = q3 + payload.threshold * iqr

                for i, price in enumerate(prices):
                    if price < lower_bound or price > upper_bound:
                        outlier_indices.add(i)

        elif payload.method == OutlierMethod.ZSCORE:
            if len(prices) >= 2:
                avg = mean(prices)
                std = stdev(prices)
                if std > 0:
                    for i, price in enumerate(prices):
                        z = abs((price - avg) / std)
                        if z > payload.threshold:
                            outlier_indices.add(i)

        # Build outlier records
        outliers: list[OutlierRecord] = []
        for i in sorted(outlier_indices):
            price, record = records[i]
            reason = (
                f"Detected by {payload.method.value} (threshold={payload.threshold})"
            )
            outliers.append(
                OutlierRecord(
                    price=price,
                    type=record.get("Type"),
                    period=record.get("Period"),
                    reason=reason,
                )
            )
            if len(outliers) >= 100:  # Limit output size
                break

        # Calculate stats after exclusion
        non_outlier_prices = [
            prices[i] for i in range(len(prices)) if i not in outlier_indices
        ]
        avg_after = int(mean(non_outlier_prices)) if non_outlier_prices else None

        logger.info(
            "detect_outliers",
            extra={
                "from_year": payload.from_year,
                "to_year": payload.to_year,
                "area": payload.area,
                "method": payload.method.value,
                "total_count": total_count,
                "outlier_count": len(outlier_indices),
            },
        )

        return DetectOutliersResponse(
            totalCount=total_count,
            outlierCount=len(outlier_indices),
            outliers=outliers,
            avgBeforeExclusion=avg_before,
            avgAfterExclusion=avg_after,
            method=payload.method.value,
            threshold=payload.threshold,
        )


__all__ = [
    "DetectOutliersInput",
    "DetectOutliersResponse",
    "DetectOutliersTool",
    "OutlierMethod",
    "OutlierRecord",
]
