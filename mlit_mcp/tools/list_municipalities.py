from __future__ import annotations

import logging
from typing import Any, Iterable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from mlit_mcp.http_client import FetchResult, MLITHttpClient

logger = logging.getLogger(__name__)


class Municipality(BaseModel):
    """Normalized municipality entry."""

    code: str = Field(
        description="5-digit municipality code assigned by MLIT",
        min_length=5,
        max_length=5,
    )
    name: str = Field(description="Municipality name", min_length=1)

    model_config = ConfigDict(populate_by_name=True)


class ResponseMeta(BaseModel):
    dataset: str = Field(default="XIT002")
    source: str = Field(default="reinfolib.mlit.go.jp")
    cache_hit: bool = Field(alias="cacheHit")

    model_config = ConfigDict(populate_by_name=True)


class ListMunicipalitiesResponse(BaseModel):
    prefecture_code: str = Field(alias="prefectureCode")
    municipalities: list[Municipality]
    meta: ResponseMeta

    model_config = ConfigDict(populate_by_name=True)


class ListMunicipalitiesInput(BaseModel):
    """Input schema for the list_municipalities tool."""

    prefecture_code: str = Field(
        alias="prefectureCode",
        description="Two digit prefecture code, e.g. '13' for Tokyo",
    )
    lang: str = Field(default="ja", description="Language for the response (ja/en)")
    force_refresh: bool = Field(
        default=False, description="If true, bypass cache and fetch fresh data"
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("prefecture_code")
    @classmethod
    def validate_prefecture_code(cls, value: str) -> str:
        digits = value.strip()
        if not digits.isdigit() or len(digits) != 2:
            raise ValueError("prefectureCode must be a 2-digit numeric string")
        return digits

    @field_validator("lang")
    @classmethod
    def validate_lang(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"ja", "en"}:
            raise ValueError("lang must be either 'ja' or 'en'")
        return normalized


class ListMunicipalitiesTool:
    """Tool implementation for listing municipalities within a prefecture."""

    name = "mlit.list_municipalities"
    description = (
        "Return the list of municipalities within the specified prefecture "
        "using MLIT dataset XIT002."
    )
    input_model = ListMunicipalitiesInput
    output_model = ListMunicipalitiesResponse

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

    async def run(self, payload: ListMunicipalitiesInput) -> ListMunicipalitiesResponse:
        fetch_result = await self._http_client.fetch(
            "XIT002",
            params={
                "area": payload.prefecture_code,
                "lang": payload.lang,
            },
            response_format="json",
            force_refresh=payload.force_refresh,
        )

        municipalities = self._transform_records(fetch_result)
        logger.info(
            "list_municipalities",
            extra={
                "prefecture_code": payload.prefecture_code,
                "municipality_count": len(municipalities),
                "cache_hit": fetch_result.from_cache,
            },
        )

        meta = ResponseMeta(cache_hit=fetch_result.from_cache)
        return ListMunicipalitiesResponse(
            prefecture_code=payload.prefecture_code,
            municipalities=municipalities,
            meta=meta,
        )

    def _transform_records(self, fetch_result: FetchResult) -> list[Municipality]:
        source = fetch_result.data
        records: Iterable[Any]
        if isinstance(source, list):
            records = source
        elif isinstance(source, dict):
            records = self._extract_list_from_dict(source)
        else:
            records = []

        municipalities: list[Municipality] = []
        for entry in records:
            if not isinstance(entry, dict):
                continue
            code = (
                entry.get("cityCode")
                or entry.get("MunicipalityCode")
                or entry.get("id")
                or entry.get("code")
            )
            name = (
                entry.get("cityName") or entry.get("Municipality") or entry.get("name")
            )
            if not code or not name:
                continue
            try:
                municipalities.append(Municipality(code=str(code), name=str(name)))
            except ValidationError:
                continue

        if not municipalities:
            raise ValueError(
                "MLIT API returned no municipalities "
                "for the provided prefecture code."
            )

        return municipalities

    @staticmethod
    def _extract_list_from_dict(payload: dict[str, Any]) -> Iterable[Any]:
        for key in ("data", "municipalities", "items", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return []


__all__ = [
    "ListMunicipalitiesInput",
    "ListMunicipalitiesResponse",
    "ListMunicipalitiesTool",
    "Municipality",
]
