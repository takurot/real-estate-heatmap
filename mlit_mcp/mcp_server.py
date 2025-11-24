"""MCP server using FastMCP for stdio-based communication with Cursor."""

from pathlib import Path
import tempfile
import asyncio
import os

from dotenv import load_dotenv
from fastmcp import FastMCP

from .cache import BinaryFileCache, InMemoryTTLCache
from .http_client import MLITHttpClient
from .settings import get_settings
from .tools.list_municipalities import ListMunicipalitiesInput, ListMunicipalitiesTool

# Load .env file from project root
# Try to find project root by looking for .env file in current directory and parent directories
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
elif Path(".env").exists():
    load_dotenv(".env")
else:
    # Try to load from current working directory
    load_dotenv()


# Initialize FastMCP server
mcp = FastMCP("mlit-mcp")


@mcp.tool()
async def list_municipalities(prefecture_code: str, lang: str = "ja") -> dict:
    """
    Return the list of municipalities within the specified prefecture using MLIT dataset XIT002.
    
    Args:
        prefecture_code: Two digit prefecture code, e.g. '13' for Tokyo
        lang: Language for the response (ja/en), defaults to 'ja'
    
    Returns:
        Dictionary containing prefecture code, municipalities list, and metadata
    """
    # Get or create cached HTTP client
    if not hasattr(mcp, "_http_client"):
        settings = get_settings()
        cache_root = Path(tempfile.gettempdir()) / "mlit_mcp_cache"
        json_cache = InMemoryTTLCache(maxsize=256, ttl=6 * 60 * 60)
        file_cache = BinaryFileCache(cache_root / "files", ttl_seconds=6 * 60 * 60)
        mcp._http_client = MLITHttpClient(
            base_url=str(settings.base_url),
            json_cache=json_cache,
            file_cache=file_cache,
        )
    
    # Create tool instance and execute
    tool = ListMunicipalitiesTool(http_client=mcp._http_client)
    input_data = ListMunicipalitiesInput(prefecture_code=prefecture_code, lang=lang)
    result = await tool.run(input_data)
    
    return result.model_dump(by_alias=True)


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()

