from __future__ import annotations

from typing import Dict, Any

from mlit_mcp.http_client import MLITHttpClient

from .list_municipalities import ListMunicipalitiesTool
from .fetch_transactions import FetchTransactionsTool
from .fetch_transaction_points import FetchTransactionPointsTool
from .fetch_land_price_points import FetchLandPricePointsTool
from .fetch_urban_planning_zones import FetchUrbanPlanningZonesTool
from .fetch_school_districts import FetchSchoolDistrictsTool
from .fetch_safety_info import FetchSafetyInfoTool
from .fetch_nearby_amenities import FetchNearbyAmenitiesTool


def build_tools(http_client: MLITHttpClient) -> Dict[str, Any]:
    """Instantiate and return available tool instances keyed by name."""

    tools: list[Any] = [
        ListMunicipalitiesTool(http_client=http_client),
        FetchTransactionsTool(http_client=http_client),
        FetchTransactionPointsTool(http_client=http_client),
        FetchLandPricePointsTool(http_client=http_client),
        FetchUrbanPlanningZonesTool(http_client=http_client),
        FetchSchoolDistrictsTool(http_client=http_client),
        FetchSafetyInfoTool(http_client=http_client),
        FetchNearbyAmenitiesTool(http_client=http_client),
    ]
    return {tool.name: tool for tool in tools}


__all__ = [
    "build_tools",
    "ListMunicipalitiesTool",
    "FetchTransactionsTool",
    "FetchTransactionPointsTool",
    "FetchLandPricePointsTool",
    "FetchUrbanPlanningZonesTool",
    "FetchSchoolDistrictsTool",
    "FetchSafetyInfoTool",
    "FetchNearbyAmenitiesTool",
]
