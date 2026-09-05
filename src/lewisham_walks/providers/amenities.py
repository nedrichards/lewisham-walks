from __future__ import annotations

import math
import os
import threading
import time
from typing import ClassVar

import requests

from ..models import AmenityStop, Coordinate
from ..planner import haversine_m


class AmenityLookupError(RuntimeError):
    pass


class OverpassAmenityProvider:
    _request_lock: ClassVar[threading.Lock] = threading.Lock()
    _last_request_started: ClassVar[float] = 0.0

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()
        self._endpoints = [
            "https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter",
        ]
        self._nominatim_endpoint = os.environ.get(
            "LEWISHAM_WALKS_NOMINATIM_ENDPOINT", "https://nominatim.openstreetmap.org/search"
        )

    def search(self, centre: Coordinate, kind: str, radius_m: int = 900) -> list[AmenityStop]:
        if kind not in {"cafe", "pub", "bar"}:
            raise ValueError("Unsupported amenity type.")
        radius = max(100, min(radius_m, 1500))
        query = f"""
        [out:json][timeout:8];
        (
          node["amenity"="{kind}"](around:{radius},{centre.lat},{centre.lon});
          way["amenity"="{kind}"](around:{radius},{centre.lat},{centre.lon});
          relation["amenity"="{kind}"](around:{radius},{centre.lat},{centre.lon});
        );
        out tags center 40;
        """
        overpass_error: AmenityLookupError | None = None
        amenities: list[AmenityStop] = []
        try:
            response = self._post_query(query)
            amenities.extend(self._parse_overpass_elements(response.json().get("elements", []), kind))
        except (AmenityLookupError, ValueError, TypeError, AttributeError) as error:
            overpass_error = AmenityLookupError(str(error))

        if not amenities:
            try:
                amenities.extend(self._search_nominatim(centre, kind, radius))
            except (requests.RequestException, ValueError, TypeError, AttributeError) as error:
                if overpass_error is not None:
                    raise AmenityLookupError(f"{overpass_error}; Nominatim fallback failed: {error}") from error
                raise AmenityLookupError(f"Nominatim fallback failed: {error}") from error

        if not amenities and overpass_error is not None:
            raise overpass_error

        return sorted(amenities, key=lambda amenity: (not amenity.name, haversine_m(centre, amenity.coordinate)))

    def _parse_overpass_elements(self, elements: list[dict], kind: str) -> list[AmenityStop]:
        amenities: list[AmenityStop] = []
        for element in elements:
            tags = {str(key): str(value) for key, value in element.get("tags", {}).items()}
            lat = element.get("lat", element.get("center", {}).get("lat"))
            lon = element.get("lon", element.get("center", {}).get("lon"))
            if lat is None or lon is None:
                continue
            amenities.append(
                AmenityStop(
                    id=f"{element.get('type', 'node')}/{element.get('id')}",
                    name=tags.get("name", kind.title()),
                    kind=kind,
                    coordinate=Coordinate(float(lat), float(lon)),
                    tags=tags,
                )
            )
        return amenities

    def _search_nominatim(self, centre: Coordinate, kind: str, radius_m: int) -> list[AmenityStop]:
        terms = ["cafe", "coffee"] if kind == "cafe" else ["pub", "bar", "beer"]
        lat_span = radius_m / 111_320
        lon_span = radius_m / max(111_320 * max(abs(math.cos(math.radians(centre.lat))), 0.2), 1)
        viewbox = f"{centre.lon - lon_span},{centre.lat + lat_span},{centre.lon + lon_span},{centre.lat - lat_span}"
        amenities: list[AmenityStop] = []
        seen: set[str] = set()
        for term in terms:
            provider_type = type(self)
            with provider_type._request_lock:
                delay = 1.0 - (time.monotonic() - provider_type._last_request_started)
                if delay > 0:
                    time.sleep(delay)
                provider_type._last_request_started = time.monotonic()
            response = self._session.get(
                self._nominatim_endpoint,
                params={"q": term, "format": "jsonv2", "limit": 20, "viewbox": viewbox, "bounded": 1},
                headers={"User-Agent": "LewishamWalks/0.1 (com.nedrichards.lewishamwalks)"},
                timeout=10,
            )
            response.raise_for_status()
            for item in response.json():
                amenity = self._amenity_from_nominatim_item(item, kind)
                if amenity is None or amenity.id in seen:
                    continue
                if haversine_m(centre, amenity.coordinate) > radius_m:
                    continue
                seen.add(amenity.id)
                amenities.append(amenity)
            if amenities:
                break
        return amenities

    def _amenity_from_nominatim_item(self, item: dict, kind: str) -> AmenityStop | None:
        lat = item.get("lat")
        lon = item.get("lon")
        osm_type = item.get("osm_type")
        osm_id = item.get("osm_id")
        if lat is None or lon is None or osm_type is None or osm_id is None:
            return None
        category = str(item.get("category", ""))
        item_type = str(item.get("type", ""))
        if kind == "cafe" and item_type != "cafe":
            return None
        if kind in {"pub", "bar"} and item_type not in {"pub", "bar", "biergarten"}:
            return None
        display_name = str(item.get("display_name", ""))
        name = display_name.split(",", 1)[0].strip() or kind.title()
        return AmenityStop(
            id=f"nominatim/{osm_type}/{osm_id}",
            name=name,
            kind="pub" if kind == "bar" else kind,
            coordinate=Coordinate(float(lat), float(lon)),
            tags={"category": category, "type": item_type, "display_name": display_name},
        )

    def _post_query(self, query: str) -> requests.Response:
        errors: list[str] = []
        for endpoint in self._endpoints:
            try:
                response = self._session.post(
                    endpoint, data={"data": query}, timeout=8,
                    headers={"User-Agent": "LewishamWalks/0.1 (com.nedrichards.lewishamwalks)"},
                )
                if response.status_code in {429, 502, 503, 504}:
                    errors.append(f"{endpoint} returned {response.status_code}")
                    continue
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as error:
                errors.append(str(error))
        raise AmenityLookupError("; ".join(errors) or "Overpass lookup failed.")
