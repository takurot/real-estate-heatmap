from contextlib import asynccontextmanager
from pathlib import Path
import tempfile

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .cache import BinaryFileCache, InMemoryTTLCache
from .http_client import MLITHttpClient
from .settings import get_settings
from .tools import build_tools


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = get_settings()
        cache_root = Path(tempfile.gettempdir()) / "mlit_mcp_cache"
        json_cache = InMemoryTTLCache(maxsize=256, ttl=6 * 60 * 60)
        file_cache = BinaryFileCache(cache_root / "files", ttl_seconds=6 * 60 * 60)
        http_client = MLITHttpClient(
            base_url=str(settings.base_url),
            json_cache=json_cache,
            file_cache=file_cache,
        )

        app.state.settings = settings
        app.state.http_client = http_client
        app.state.tools = build_tools(http_client)
        yield
        await http_client.aclose()

    app = FastAPI(
        title="MLIT MCP Server",
        version="0.1.0",
        summary="MCP adapter for MLIT Real Estate Library APIs",
        lifespan=lifespan,
    )

    @app.api_route("/", methods=["GET", "POST"], tags=["internal"])
    async def index() -> dict[str, str]:
        return {"status": "ok", "service": "mlit-mcp"}

    @app.get("/healthz", tags=["internal"])
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/list_tools", tags=["mcp"])
    async def list_tools() -> dict[str, list]:
        tools = getattr(app.state, "tools", {})
        descriptors = [tool.descriptor() for tool in tools.values()]
        return {"tools": descriptors}

    @app.post("/call_tool", tags=["mcp"])
    async def call_tool(payload: dict = Body(default_factory=dict)) -> JSONResponse:
        tool_name = payload.get("toolName")
        if not tool_name:
            raise HTTPException(status_code=400, detail="toolName is required")
        tools = getattr(app.state, "tools", {})
        tool = tools.get(tool_name)
        if not tool:
            raise HTTPException(
                status_code=404, detail=f"Tool '{tool_name}' is not registered."
            )

        arguments = payload.get("arguments") or {}
        try:
            result = await tool.invoke(arguments)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=exc.errors()) from exc
        except ValueError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return JSONResponse(content={"data": result})

    @app.post("/list_resources", tags=["mcp"])
    async def list_resources() -> dict[str, list]:
        """List available resources (cached GeoJSON files)."""
        http_client = getattr(app.state, "http_client", None)
        if not http_client or not hasattr(http_client, "_file_cache"):
            return {"resources": []}

        file_cache = http_client._file_cache
        cache_dir = file_cache._cache_dir

        resources = []
        if cache_dir.exists():
            for file_path in cache_dir.glob("*.geojson"):
                resources.append(
                    {
                        "uri": f"resource://mlit/transaction_points/{file_path.name}",
                        "name": file_path.stem,
                        "mimeType": "application/geo+json",
                        "description": "Cached GeoJSON transaction points data",
                    }
                )

        return {"resources": resources}

    @app.post("/read_resource", tags=["mcp"])
    async def read_resource(payload: dict = Body(default_factory=dict)) -> JSONResponse:
        """Read a resource by URI."""
        resource_uri = payload.get("uri") or payload.get("resourceId")
        if not resource_uri:
            raise HTTPException(status_code=400, detail="uri or resourceId is required")

        # Parse resource URI: resource://mlit/transaction_points/{filename}
        if not resource_uri.startswith("resource://mlit/transaction_points/"):
            raise HTTPException(
                status_code=404, detail=f"Resource '{resource_uri}' not found"
            )

        filename = resource_uri.split("/")[-1]

        http_client = getattr(app.state, "http_client", None)
        if not http_client or not hasattr(http_client, "_file_cache"):
            raise HTTPException(status_code=500, detail="File cache not available")

        file_cache = http_client._file_cache
        cache_dir = file_cache._cache_dir
        file_path = cache_dir / filename

        if not file_path.exists():
            raise HTTPException(
                status_code=404, detail=f"Resource file '{filename}' not found"
            )

        try:
            content = file_path.read_text(encoding="utf-8")
            return JSONResponse(
                content={
                    "contents": [
                        {
                            "uri": resource_uri,
                            "mimeType": "application/geo+json",
                            "text": content,
                        }
                    ]
                }
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Failed to read resource: {exc}"
            ) from exc

    return app


app = create_app()
