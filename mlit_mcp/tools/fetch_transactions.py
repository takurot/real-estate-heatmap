from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mlit_mcp.http_client import MLITHttpClient

logger = logging.getLogger(__name__)


class FetchTransactionsInput(BaseModel):
    """Input schema for the fetch_transactions tool."""

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
    format: Literal["json", "table"] = Field(
        default="json",
        description=(
            "Response format: 'json' for raw data, "
            "'table' for pandas-compatible structure"
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
    format: str

    model_config = ConfigDict(populate_by_name=True)


class FetchTransactionsResponse(BaseModel):
    data: list[dict[str, Any]]
    meta: ResponseMeta

    model_config = ConfigDict(populate_by_name=True)


class FetchTransactionsTool:
    """Tool implementation for fetching transaction data from MLIT XIT001 API."""

    name = "mlit.fetch_transactions"
    description = (
        "Fetch aggregated real estate transaction data from MLIT dataset "
        "XIT001. Returns data in JSON or table format (pandas-compatible)."
    )
    input_model = FetchTransactionsInput
    output_model = FetchTransactionsResponse

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
        return result.model_dump(by_alias=True)

    async def run(self, payload: FetchTransactionsInput) -> FetchTransactionsResponse:
        # XIT001 API uses 'year' parameter, not 'from'/'to'
        # If year range is specified, we need to fetch each year separately
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
            params["year"] = year

            fetch_result = await self._http_client.fetch(
                "XIT001",
                params=params,
                response_format="json",
                force_refresh=payload.force_refresh,
            )

            year_data = fetch_result.data
            # Extract data from response if it's wrapped
            # The API usually returns {"data": [...], "status": "OK"} or similar
            if isinstance(year_data, dict):
                if "data" in year_data and isinstance(year_data["data"], list):
                    all_data.extend(year_data["data"])
                elif "status" in year_data and year_data.get("status") == "OK":
                    if "data" in year_data and isinstance(year_data["data"], list):
                        all_data.extend(year_data["data"])
                    # Fallback if structure is different but has status OK
                    pass
                else:
                    # If it's a single record or other structure, add as is
                    all_data.append(year_data)
            elif isinstance(year_data, list):
                all_data.extend(year_data)

        # For XIT001, JSON and table format are both list of dicts,
        # but 'table' usually implies we ensure it's flat.
        # Since the API returns flat objects in 'data',
        # we likely just return all_data.

        logger.info(
            "fetch_transactions",
            extra={
                "from_year": payload.from_year,
                "to_year": payload.to_year,
                "area": payload.area,
                "format": payload.format,
                "record_count": len(all_data),
                "cache_hit": False,  # Multiple requests
            },
        )

        meta = ResponseMeta(
            cache_hit=False,
            format=payload.format,
        )
        return FetchTransactionsResponse(data=all_data, meta=meta)


__all__ = [
    "FetchTransactionsInput",
    "FetchTransactionsResponse",
    "FetchTransactionsTool",
]
