from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from collections import Counter
import logging

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .cache import BinaryFileCache, InMemoryTTLCache
from .settings import get_settings


RETRYABLE_STATUS_CODES = {408, 409, 425, 429} | set(range(500, 600))

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FetchResult:
    data: Any | None = None
    file_path: Path | None = None
    from_cache: bool = False


class RetryableHTTPStatusError(Exception):
    def __init__(self, response: httpx.Response):
        self.response = response
        super().__init__(f"Retryable HTTP status: {response.status_code}")


class MLITHttpClient:
    """HTTP client with retry and caching helpers for MLIT APIs."""

    def __init__(
        self,
        base_url: str,
        json_cache: InMemoryTTLCache,
        file_cache: BinaryFileCache,
        *,
        api_key: str | None = None,
        timeout: float | None = None,
        max_attempts: int = 4,
        transport: Any = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.api_key
        self._base_url = base_url
        self._json_cache = json_cache
        self._file_cache = file_cache
        self._max_attempts = max_attempts
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout or settings.http_timeout,
            headers={"Ocp-Apim-Subscription-Key": self._api_key},
            transport=transport,
        )
        self._stats: Counter[str] = Counter()

    def get_stats(self) -> dict[str, int]:
        """Return a dictionary of collected statistics."""
        return {
            "total_requests": self._stats["total_requests"],
            "cache_hits": self._stats["cache_hits"],
            "cache_misses": self._stats["cache_misses"],
            "api_errors": self._stats["api_errors"],
        }

    def save_to_cache(self, key: str, content: bytes, suffix: str = ".json") -> Path:
        """Save content to the file cache and return the path."""
        return self._file_cache.set(key, content, suffix=suffix)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(
        self,
        endpoint: str,
        *,
        params: Mapping[str, Any] | None = None,
        response_format: str = "json",
        force_refresh: bool = False,
    ) -> FetchResult:
        cache_key = self._build_cache_key(endpoint, params, response_format)
        normalized_format = response_format.lower()

        self._stats["total_requests"] += 1
        logger.info(
            f"Fetching {endpoint}", extra={"params": params, "format": response_format}
        )

        if not force_refresh:
            cached = self._get_cached(normalized_format, cache_key)
            if cached is not None:
                self._stats["cache_hits"] += 1
                logger.info(f"Cache hit for {endpoint}")
                if normalized_format == "json":
                    return FetchResult(data=cached, from_cache=True)
                return FetchResult(file_path=cached, from_cache=True)
            logger.info(f"Cache miss for {endpoint}")

        self._stats["cache_misses"] += 1
        try:
            response = await self._send_with_retry(endpoint, params)
        except Exception as e:
            self._stats["api_errors"] += 1
            logger.error(f"Request failed for {endpoint}: {e}")
            raise

        if normalized_format == "json":
            data = response.json()
            self._json_cache.set(cache_key, data)
            return FetchResult(data=data, from_cache=False)

        suffix = self._suffix_for_format(normalized_format)
        path = self._file_cache.set(cache_key, response.content, suffix=suffix)
        return FetchResult(file_path=path, from_cache=False)

    def _get_cached(self, normalized_format: str, cache_key: str) -> Any | None:
        if normalized_format == "json":
            return self._json_cache.get(cache_key)
        return self._file_cache.get(cache_key)

    async def _send_with_retry(
        self, endpoint: str, params: Mapping[str, Any] | None
    ) -> httpx.Response:
        prepared_params = dict(params or {})

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            retry=retry_if_exception_type(RetryableHTTPStatusError),
            reraise=True,
        ):
            with attempt:
                response = await self._client.get(endpoint, params=prepared_params)
                if response.status_code in RETRYABLE_STATUS_CODES:
                    raise RetryableHTTPStatusError(response)
                response.raise_for_status()
                return response

        raise RuntimeError("Retry loop exited unexpectedly")

    @staticmethod
    def _build_cache_key(
        endpoint: str, params: Mapping[str, Any] | None, response_format: str
    ) -> str:
        payload = {
            "endpoint": endpoint,
            "params": params or {},
            "format": response_format,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _suffix_for_format(response_format: str) -> str:
        match response_format:
            case "geojson":
                return ".geojson"
            case "mvt":
                return ".mvt"
            case "pbf":
                return ".pbf"
            case _:
                return ".bin"

    def clear_cache(self) -> None:
        """Clear all in-memory and file caches and reset stats."""
        self._json_cache.clear()
        self._file_cache.clear()
        self._stats = Counter()
        logger.info("Cleared all caches and reset statistics")
