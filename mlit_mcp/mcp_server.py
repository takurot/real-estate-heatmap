"""MCP server using FastMCP for stdio-based communication with Cursor."""

from pathlib import Path
import tempfile
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP

from .cache import BinaryFileCache, InMemoryTTLCache
from .http_client import MLITHttpClient
from .settings import get_settings

# Load .env file from project root
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
elif Path(".env").exists():
    load_dotenv(".env")
else:
    load_dotenv()


# Initialize FastMCP server
mcp = FastMCP("mlit-mcp")

# Initialize HTTP client (shared across all tools)
_http_client = None


def _get_http_client() -> Any:
    """Get or create the shared HTTP client."""
    global _http_client
    if _http_client is None:
        settings = get_settings()
        cache_root = Path(tempfile.gettempdir()) / "mlit_mcp_cache"
        json_cache = InMemoryTTLCache(maxsize=256, ttl=6 * 60 * 60)
        file_cache = BinaryFileCache(cache_root / "files", ttl_seconds=6 * 60 * 60)
        _http_client = MLITHttpClient(
            base_url=str(settings.base_url),
            json_cache=json_cache,
            file_cache=file_cache,
        )
    return _http_client


@mcp.tool()
async def list_municipalities(
    prefecture_code: str, lang: str = "ja", force_refresh: bool = False
) -> dict:
    """
    Return the list of municipalities within the specified prefecture using
    MLIT dataset XIT002.

    Args:
        prefecture_code: Two digit prefecture code, e.g. '13' for Tokyo
        lang: Language for the response (ja/en), defaults to 'ja'
        force_refresh: If true, bypass cache and fetch fresh data
    """
    from .tools.list_municipalities import (
        ListMunicipalitiesInput,
        ListMunicipalitiesTool,
    )

    tool = ListMunicipalitiesTool(http_client=_get_http_client())
    input_data = ListMunicipalitiesInput(
        prefecture_code=prefecture_code,
        lang=lang,
        force_refresh=force_refresh,
    )
    result = await tool.run(input_data)
    return result.model_dump(by_alias=True)


@mcp.tool()
async def fetch_transactions(
    from_year: int,
    to_year: int,
    area: str,
    classification: str | None = None,
    format: str = "json",
    force_refresh: bool = False,
) -> dict:
    """
    Fetch aggregated real estate transaction data from MLIT dataset XIT001.

    Args:
        from_year: Starting year (2005-2030)
        to_year: Ending year (2005-2030)
        area: Area code (prefecture or city code)
        classification: Optional transaction classification code
        format: Response format ('json' or 'table'), defaults to 'json'
        force_refresh: If true, bypass cache and fetch fresh data
    """
    from .tools.fetch_transactions import (
        FetchTransactionsInput,
        FetchTransactionsTool,
    )

    tool = FetchTransactionsTool(http_client=_get_http_client())
    input_data = FetchTransactionsInput(
        from_year=from_year,
        to_year=to_year,
        area=area,
        classification=classification,
        format=format,
        force_refresh=force_refresh,
    )
    result = await tool.run(input_data)
    return result.model_dump(by_alias=True)


@mcp.tool()
async def fetch_transaction_points(
    z: int,
    x: int,
    y: int,
    from_quarter: str,
    to_quarter: str,
    response_format: str = "geojson",
    price_classification: str | None = None,
    land_type_code: str | None = None,
    bbox: dict | None = None,
    force_refresh: bool = False,
) -> dict:
    """
    Fetch real estate transaction points as GeoJSON from MLIT dataset XPT001.
    Requires XYZ tile coordinates. Large responses (>1MB) are returned as
    resource URIs.

    Args:
        z: Zoom level (11-15)
        x: Tile X coordinate
        y: Tile Y coordinate
        from_quarter: Start quarter in YYYYN format (e.g., 20231 for Q1 2023)
        to_quarter: End quarter in YYYYN format (e.g., 20244 for Q4 2024)
        response_format: 'geojson' or 'pbf', defaults to 'geojson'
        price_classification: Optional price classification (01=transaction,
                              02=contract)
        land_type_code: Optional land type codes, comma-separated
                        (e.g., '01,02,07')
        bbox: Optional bounding box filter with minLon, minLat, maxLon, maxLat
        force_refresh: If true, bypass cache and fetch fresh data
    """
    from .tools.fetch_transaction_points import (
        FetchTransactionPointsInput,
        FetchTransactionPointsTool,
    )

    tool = FetchTransactionPointsTool(http_client=_get_http_client())
    input_data = FetchTransactionPointsInput(
        z=z,
        x=x,
        y=y,
        from_quarter=from_quarter,
        to_quarter=to_quarter,
        response_format=response_format,
        price_classification=price_classification,
        land_type_code=land_type_code,
        bbox=bbox,
        force_refresh=force_refresh,
    )
    result = await tool.run(input_data)
    return result.model_dump(by_alias=True, exclude_none=True)


@mcp.tool()
async def fetch_land_price_points(
    z: int,
    x: int,
    y: int,
    year: int,
    response_format: str = "geojson",
    force_refresh: bool = False,
) -> dict:
    """
    Fetch land price (地価公示) point data from MLIT dataset XPT002.
    Supports both GeoJSON and PBF (Protocol Buffer) formats.

    Args:
        z: Zoom level (13-15)
        x: Tile X coordinate
        y: Tile Y coordinate
        year: Target year (1995-2024)
        response_format: 'geojson' or 'pbf', defaults to 'geojson'
        force_refresh: If true, bypass cache and fetch fresh data
    """
    from .tools.fetch_land_price_points import (
        FetchLandPricePointsInput,
        FetchLandPricePointsTool,
    )

    tool = FetchLandPricePointsTool(http_client=_get_http_client())
    input_data = FetchLandPricePointsInput(
        z=z,
        x=x,
        y=y,
        year=year,
        response_format=response_format,
        force_refresh=force_refresh,
    )
    result = await tool.run(input_data)
    return result.model_dump(by_alias=True, exclude_none=True)


@mcp.tool()
async def fetch_urban_planning_zones(
    z: int,
    x: int,
    y: int,
    response_format: str = "geojson",
    force_refresh: bool = False,
) -> dict:
    """
    Fetch urban planning zone (都市計画区域) data from MLIT dataset XKT001.
    Requires z/x/y tile coordinates.

    Args:
        z: Zoom level (11-15)
        x: Tile X coordinate
        y: Tile Y coordinate
        response_format: 'geojson' or 'pbf', defaults to 'geojson'
        force_refresh: If true, bypass cache and fetch fresh data
    """
    from .tools.fetch_urban_planning_zones import (
        FetchUrbanPlanningZonesInput,
        FetchUrbanPlanningZonesTool,
    )

    tool = FetchUrbanPlanningZonesTool(http_client=_get_http_client())
    input_data = FetchUrbanPlanningZonesInput(
        z=z,
        x=x,
        y=y,
        response_format=response_format,
        force_refresh=force_refresh,
    )
    result = await tool.run(input_data)
    return result.model_dump(by_alias=True, exclude_none=True)


@mcp.tool()
async def fetch_school_districts(
    z: int,
    x: int,
    y: int,
    administrative_area_code: str | None = None,
    response_format: str = "geojson",
    force_refresh: bool = False,
) -> dict:
    """
    Fetch elementary school district (小学校区) tile data from MLIT dataset XKT004.
    Returns MVT (Mapbox Vector Tile) data encoded as base64.

    Args:
        z: Zoom level (11-15)
        x: Tile X coordinate
        y: Tile Y coordinate
        administrative_area_code: Optional 5-digit administrative area code
        response_format: 'geojson' or 'pbf', defaults to 'geojson'
        force_refresh: If true, bypass cache and fetch fresh data
    """
    from .tools.fetch_school_districts import (
        FetchSchoolDistrictsInput,
        FetchSchoolDistrictsTool,
    )

    tool = FetchSchoolDistrictsTool(http_client=_get_http_client())
    input_data = FetchSchoolDistrictsInput(
        z=z,
        x=x,
        y=y,
        administrative_area_code=administrative_area_code,
        response_format=response_format,
        force_refresh=force_refresh,
    )
    result = await tool.run(input_data)
    return result.model_dump(by_alias=True, exclude_none=True)


@mcp.tool()
async def get_server_stats() -> dict:
    """
    Get internal server statistics including cache hits, misses, and request counts.
    """
    client = _get_http_client()
    return client.get_stats()


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
