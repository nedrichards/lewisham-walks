from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .models import Coordinate

if TYPE_CHECKING:
    from .models import Discovery


@dataclass(frozen=True)
class MapBounds:
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


def coordinate_bounds(coordinates: list[Coordinate], padding_ratio: float = 0.08) -> MapBounds:
    if not coordinates:
        return MapBounds(51.40, 51.50, -0.08, 0.04)

    min_lat = min(coordinate.lat for coordinate in coordinates)
    max_lat = max(coordinate.lat for coordinate in coordinates)
    min_lon = min(coordinate.lon for coordinate in coordinates)
    max_lon = max(coordinate.lon for coordinate in coordinates)

    lat_span = max(max_lat - min_lat, 0.01)
    lon_span = max(max_lon - min_lon, 0.01)
    lat_padding = lat_span * padding_ratio
    lon_padding = lon_span * padding_ratio
    return MapBounds(
        min_lat=min_lat - lat_padding,
        max_lat=max_lat + lat_padding,
        min_lon=min_lon - lon_padding,
        max_lon=max_lon + lon_padding,
    )


def project_coordinate(coordinate: Coordinate, bounds: MapBounds, width: int, height: int, margin: int = 28) -> tuple[float, float]:
    drawable_width = max(width - margin * 2, 1)
    drawable_height = max(height - margin * 2, 1)
    x_ratio = (coordinate.lon - bounds.min_lon) / max(bounds.max_lon - bounds.min_lon, 0.000001)
    y_ratio = (bounds.max_lat - coordinate.lat) / max(bounds.max_lat - bounds.min_lat, 0.000001)
    return margin + drawable_width * x_ratio, margin + drawable_height * y_ratio


def unproject_coordinate(x: float, y: float, bounds: MapBounds, width: int, height: int, margin: int = 28) -> Coordinate:
    drawable_width = max(width - margin * 2, 1)
    drawable_height = max(height - margin * 2, 1)
    x_ratio = min(max((x - margin) / drawable_width, 0.0), 1.0)
    y_ratio = min(max((y - margin) / drawable_height, 0.0), 1.0)
    latitude = bounds.max_lat - y_ratio * (bounds.max_lat - bounds.min_lat)
    longitude = bounds.min_lon + x_ratio * (bounds.max_lon - bounds.min_lon)
    return Coordinate(latitude, longitude)


def discoveries_for_viewport(
    discoveries: list["Discovery"],
    bounds: MapBounds,
    centre: Coordinate,
    limit: int = 48,
    columns: int = 8,
    rows: int = 6,
) -> list["Discovery"]:
    """Choose a useful, spatially distributed set for the visible map.

    One pass through each grid cell prevents a dense cluster from consuming the
    whole marker budget. Further passes fill remaining space when zoomed in.
    """
    if limit <= 0:
        return []
    visible = [
        discovery
        for discovery in discoveries
        if bounds.min_lat <= discovery.coordinate.lat <= bounds.max_lat
        and bounds.min_lon <= discovery.coordinate.lon <= bounds.max_lon
    ]
    if not visible:
        return []

    lat_span = max(bounds.max_lat - bounds.min_lat, 0.000001)
    lon_span = max(bounds.max_lon - bounds.min_lon, 0.000001)
    buckets: dict[tuple[int, int], list["Discovery"]] = {}
    for discovery in visible:
        column = min(columns - 1, max(0, int((discovery.coordinate.lon - bounds.min_lon) / lon_span * columns)))
        row = min(rows - 1, max(0, int((discovery.coordinate.lat - bounds.min_lat) / lat_span * rows)))
        buckets.setdefault((column, row), []).append(discovery)

    def rank(discovery: "Discovery") -> tuple[int, int, int, float, str]:
        return (
            0 if discovery.curation_status == "in_scope" else 1,
            0 if discovery.is_accurate else 1,
            0 if discovery.description.strip() else 1,
            _coordinate_distance_m(centre, discovery.coordinate),
            discovery.id,
        )

    for bucket in buckets.values():
        bucket.sort(key=rank)
    ordered_cells = sorted(
        buckets,
        key=lambda cell: min(_coordinate_distance_m(centre, item.coordinate) for item in buckets[cell]),
    )

    selected: list["Discovery"] = []
    while ordered_cells and len(selected) < limit:
        next_cells: list[tuple[int, int]] = []
        for cell in ordered_cells:
            bucket = buckets[cell]
            while bucket:
                candidate = bucket.pop(0)
                if all(_coordinate_distance_m(candidate.coordinate, item.coordinate) >= 25 for item in selected):
                    selected.append(candidate)
                    break
            if bucket:
                next_cells.append(cell)
            if len(selected) >= limit:
                break
        ordered_cells = next_cells
    return selected


def _coordinate_distance_m(a: Coordinate, b: Coordinate) -> float:
    mean_latitude = math.radians((a.lat + b.lat) / 2)
    north_south = (a.lat - b.lat) * 111_320
    east_west = (a.lon - b.lon) * 111_320 * math.cos(mean_latitude)
    return math.hypot(north_south, east_west)


def find_discovery_at_position(
    x: float,
    y: float,
    bounds: MapBounds,
    width: int,
    height: int,
    discoveries: list["Discovery"],
    threshold_px: float = 14.0,
) -> "Discovery | None":
    closest = None
    closest_distance = threshold_px
    for discovery in discoveries:
        discovery_x, discovery_y = project_coordinate(discovery.coordinate, bounds, width, height)
        distance = math.hypot(discovery_x - x, discovery_y - y)
        if distance <= closest_distance:
            closest = discovery
            closest_distance = distance
    return closest
