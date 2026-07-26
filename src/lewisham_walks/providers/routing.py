from __future__ import annotations

import threading
import time
from typing import ClassVar

import requests

from ..models import Coordinate, RouteRequest, RouteStep


class RoutingError(RuntimeError):
    pass


class OpenStreetMapRoutingProvider:
    """Keyless pedestrian routing from the FOSSGIS OpenStreetMap service."""

    ENDPOINT = "https://routing.openstreetmap.de/routed-foot/route/v1/driving"
    _request_lock: ClassVar[threading.Lock] = threading.Lock()
    _last_request_started: ClassVar[float] = 0.0

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def route(self, waypoints: list[Coordinate], _request: RouteRequest) -> tuple[list[Coordinate], list[RouteStep], float, float]:
        if len(waypoints) < 2:
            return list(waypoints), [], 0.0, 0.0
        coordinates = ";".join(f"{point.lon:.6f},{point.lat:.6f}" for point in waypoints)
        provider_type = type(self)
        with provider_type._request_lock:
            delay = 1.0 - (time.monotonic() - provider_type._last_request_started)
            if delay > 0:
                time.sleep(delay)
            provider_type._last_request_started = time.monotonic()
        response = self._session.get(
            f"{self.ENDPOINT}/{coordinates}",
            params={"overview": "full", "geometries": "geojson", "steps": "true"},
            headers={"User-Agent": "LewishamWalks/0.1 (com.nedrichards.lewishamwalks)"},
            timeout=30,
        )
        try:
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            raise RoutingError(f"Walking directions are unavailable: {error}") from error
        routes = payload.get("routes") or []
        if payload.get("code") != "Ok" or not routes:
            raise RoutingError(str(payload.get("message") or "No walking route was returned."))

        route = routes[0]
        raw_geometry = route.get("geometry", {}).get("coordinates", [])
        geometry = [Coordinate(lat=float(lat), lon=float(lon)) for lon, lat in raw_geometry]
        steps = [
            RouteStep(
                instruction=_osrm_instruction(step),
                distance_m=float(step.get("distance", 0)),
                duration_s=float(step.get("duration", 0)),
                leg_index=leg_index,
            )
            for leg_index, leg in enumerate(route.get("legs", []))
            for step in leg.get("steps", [])
        ]
        return geometry, steps, float(route.get("distance", 0)), float(route.get("duration", 0))


def _osrm_instruction(step: dict) -> str:
    maneuver = step.get("maneuver", {})
    kind = str(maneuver.get("type", "continue")).replace("_", " ")
    modifier = str(maneuver.get("modifier", "")).replace("_", " ")
    road = str(step.get("name", "")).strip()
    if kind == "depart":
        instruction = "Set off"
    elif kind == "arrive":
        instruction = "Arrive"
    elif kind == "turn" and modifier:
        instruction = f"Turn {modifier}"
    elif modifier:
        instruction = f"{kind.title()} {modifier}"
    else:
        instruction = kind.title()
    return f"{instruction} onto {road}" if road and kind != "arrive" else instruction
