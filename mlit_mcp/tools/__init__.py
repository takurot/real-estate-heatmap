from __future__ import annotations

from typing import Dict

from mlit_mcp.http_client import MLITHttpClient

from .list_municipalities import ListMunicipalitiesTool


def build_tools(http_client: MLITHttpClient) -> Dict[str, ListMunicipalitiesTool]:
    """Instantiate and return available tool instances keyed by name."""

    tools = [ListMunicipalitiesTool(http_client=http_client)]
    return {tool.name: tool for tool in tools}


__all__ = ["build_tools", "ListMunicipalitiesTool"]



