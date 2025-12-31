"""GIS helper utilities for MVT/PBF encoding and coordinate transformations."""

from __future__ import annotations

import base64
import math


def lat_lon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """
    Convert latitude/longitude to tile coordinates (Web Mercator projection).

    Args:
        lat: Latitude in degrees
        lon: Longitude in degrees
        zoom: Zoom level (0-18, typically 11-15 for MLIT APIs)

    Returns:
        Tuple of (tile_x, tile_y)
    """
    n = 2.0**zoom
    tile_x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    tile_y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return (tile_x, tile_y)


def bbox_to_tiles(
    min_lat: float, min_lon: float, max_lat: float, max_lon: float, zoom: int
) -> list[tuple[int, int]]:
    """
    Convert bounding box to list of tile coordinates covering the area.

    Args:
        min_lat: Minimum latitude
        min_lon: Minimum longitude
        max_lat: Maximum latitude
        max_lon: Maximum longitude
        zoom: Zoom level

    Returns:
        List of (tile_x, tile_y) tuples
    """
    min_tile_x, max_tile_y = lat_lon_to_tile(min_lat, min_lon, zoom)
    max_tile_x, min_tile_y = lat_lon_to_tile(max_lat, max_lon, zoom)

    tiles = []
    for x in range(min_tile_x, max_tile_x + 1):
        for y in range(min_tile_y, max_tile_y + 1):
            tiles.append((x, y))

    return tiles


def encode_mvt_to_base64(content: bytes) -> str:
    """
    Encode MVT/PBF binary data to base64 string.

    Args:
        content: Binary MVT/PBF data

    Returns:
        Base64-encoded string
    """
    return base64.b64encode(content).decode("ascii")


def decode_base64_to_mvt(encoded: str) -> bytes:
    """
    Decode base64 string back to MVT/PBF binary data.

    Args:
        encoded: Base64-encoded string

    Returns:
        Binary MVT/PBF data
    """
    return base64.b64decode(encoded)


__all__ = [
    "encode_mvt_to_base64",
    "decode_base64_to_mvt",
    "lat_lon_to_tile",
    "bbox_to_tiles",
]
