from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mlit_mcp.http_client import MLITHttpClient


class ClearCacheInput(BaseModel):
    """Input schema for clear_cache tool (empty)."""

    model_config = ConfigDict(extra="forbid")


class ClearCacheResponse(BaseModel):
    """Response schema for clear_cache tool."""

    status: str = Field(description="Operation status (success)")
    message: str = Field(description="Result message")
    stats: dict[str, int] = Field(description="Server statistics after clearing")


class ClearCacheTool:
    """Tool for clearing all internal caches."""

    name = "mlit.clear_cache"
    description = (
        "Clear all internal API caches (in-memory and file-based) and reset statistics. "
        "Useful for debugging or freeing up disk space."
    )
    input_model = ClearCacheInput
    output_model = ClearCacheResponse

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

    async def run(self, payload: ClearCacheInput) -> ClearCacheResponse:
        self._http_client.clear_cache()
        stats = self._http_client.get_stats()

        return ClearCacheResponse(
            status="success",
            message="Cache cleared and statistics reset",
            stats=stats,
        )


__all__ = ["ClearCacheInput", "ClearCacheResponse", "ClearCacheTool"]
