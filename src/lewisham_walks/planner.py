from __future__ import annotations

import math
from dataclasses import replace
from typing import Protocol

from .models import (
    AmenityStop,
    Coordinate,
    Discovery,
    DiscoveryKind,
    RouteMode,
    RoutePlan,
    RouteRequest,
    RouteStep,
    RouteVisit,
    StopPreference,
)

MAX_BLOSSOM_ROUTE_POINTS = 48


class RoutingProvider(Protocol):
    def route(self, waypoints: list[Coordinate], request: RouteRequest) -> tuple[list[Coordinate], list[RouteStep], float, float]:
        """Return geometry, steps, distance metres, walking seconds."""


class AmenityProvider(Protocol):
    def search(self, centre: Coordinate, kind: str, radius_m: int = 900) -> list[AmenityStop]:
        """Return candidate amenities near centre."""


def haversine_m(a: Coordinate, b: Coordinate) -> float:
    radius = 6371000.0
    lat1 = math.radians(a.lat)
    lat2 = math.radians(b.lat)
    dlat = math.radians(b.lat - a.lat)
    dlon = math.radians(b.lon - a.lon)
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


def straight_line_route(waypoints: list[Coordinate], request: RouteRequest) -> tuple[list[Coordinate], list[RouteStep], float, float]:
    distance = sum(haversine_m(a, b) for a, b in zip(waypoints, waypoints[1:]))
    walking_seconds = distance / (request.walking_speed_kmh * 1000 / 3600)
    steps = [
        RouteStep(
            instruction=f"Walk to stop {index + 1}",
            distance_m=haversine_m(a, b),
            duration_s=haversine_m(a, b) / (request.walking_speed_kmh * 1000 / 3600),
        )
        for index, (a, b) in enumerate(zip(waypoints, waypoints[1:]))
    ]
    return waypoints, steps, distance, walking_seconds


class StraightLineRoutingProvider:
    def route(self, waypoints: list[Coordinate], request: RouteRequest) -> tuple[list[Coordinate], list[RouteStep], float, float]:
        return straight_line_route(waypoints, request)


class RoutePlanner:
    def __init__(
        self,
        discoveries: list[Discovery],
        routing_provider: RoutingProvider | None = None,
        amenity_provider: AmenityProvider | None = None,
    ) -> None:
        self._discoveries = discoveries
        self._routing_provider = routing_provider or StraightLineRoutingProvider()
        self._amenity_provider = amenity_provider

    def plan(self, request: RouteRequest) -> RoutePlan:
        request = self._normalise_request(request)
        warnings: list[str] = []
        selected = self._select_discoveries(request)
        amenities = self._select_amenities(request, selected, warnings)
        waypoints, visits = self._build_itinerary(request, selected, amenities)
        geometry, steps, distance_m, walking_seconds = self._routing_provider.route(waypoints, request)
        dwell_seconds = self._dwell_seconds(selected, request)

        if not selected:
            warnings.append("No discoveries fitted into the requested time. Try a longer walk or a different start point.")
        if walking_seconds + dwell_seconds > request.duration_minutes * 60 * 1.15:
            warnings.append("The generated walk is likely to exceed the requested time.")

        return RoutePlan(
            request=request,
            discoveries=selected,
            amenities=amenities,
            visits=visits,
            waypoints=waypoints,
            geometry=geometry,
            steps=steps,
            distance_m=distance_m,
            walking_seconds=walking_seconds,
            dwell_seconds=dwell_seconds,
            warnings=warnings,
        )

    def _normalise_request(self, request: RouteRequest) -> RouteRequest:
        max_points = MAX_BLOSSOM_ROUTE_POINTS if request.route_mode is RouteMode.BLOSSOM_WALK else 20
        return replace(
            request,
            duration_minutes=max(15, min(240, request.duration_minutes)),
            max_discoveries=max(1, min(max_points, request.max_discoveries)),
            walking_speed_kmh=max(2.0, min(7.0, request.walking_speed_kmh)),
        )

    def _select_discoveries(self, request: RouteRequest) -> list[Discovery]:
        if request.route_mode is RouteMode.BLOSSOM_WALK:
            return self._select_ordered_route_points(request)

        budget_seconds = request.duration_minutes * 60 * 0.82
        selected: list[Discovery] = []
        current = request.start
        unseen = [discovery for discovery in self._discoveries if discovery.id not in request.seen_story_ids]
        candidates = unseen or list(self._discoveries)
        seen_topics: set[str] = set()

        while candidates and len(selected) < request.max_discoveries:
            best = min(candidates, key=lambda discovery: self._candidate_score(discovery, current, seen_topics, request.variation_seed))
            candidate_selection = selected + [best]
            trial_points = [request.start, *[discovery.coordinate for discovery in candidate_selection], request.end or request.start]
            distance = sum(haversine_m(a, b) for a, b in zip(trial_points, trial_points[1:]))
            walking_seconds = distance / (request.walking_speed_kmh * 1000 / 3600)
            dwell_seconds = self._dwell_seconds(candidate_selection, request)
            if walking_seconds + dwell_seconds > budget_seconds and selected:
                break
            if walking_seconds + dwell_seconds <= budget_seconds:
                selected.append(best)
                current = best.coordinate
                seen_topics.update(self._topics_for(best))
            candidates.remove(best)
            candidates = [candidate for candidate in candidates if haversine_m(best.coordinate, candidate.coordinate) >= 25]
        return selected

    def _candidate_score(self, discovery: Discovery, current: Coordinate, seen_topics: set[str], variation_seed: int) -> float:
        """Prefer nearby, trustworthy stories while keeping a walk varied."""
        score = haversine_m(current, discovery.coordinate)
        if discovery.curation_status == "in_scope":
            score -= 180
        if discovery.borough.casefold() == "lewisham":
            score -= 40
        if discovery.is_accurate:
            score -= 70
        if self._topics_for(discovery) - seen_topics:
            score -= 120
        description_length = len(discovery.description.strip())
        if 25 <= description_length <= 500:
            score -= 40
        if variation_seed:
            # Stable per-walk variation: enough to change choices among nearby
            # stories without turning a local walk into a random scatter plot.
            fingerprint = sum((index + 1) * ord(character) for index, character in enumerate(discovery.id))
            score += ((fingerprint * (variation_seed + 17)) % 241) - 120
        return score

    @staticmethod
    def _topics_for(discovery: Discovery) -> set[str]:
        # Kept local to the planner to avoid coupling the route engine to GTK-facing
        # discovery copy. These broad signals are only used to avoid repetitive walks.
        text = f"{discovery.title} {discovery.description}".lower()
        topics = set()
        for topic, words in {
            "people": (" born ", " lived ", " artist", " writer", " poet", " musician", " actor"),
            "places": (" built ", " site ", " station", " bridge", " market", " factory", " school"),
            "community": (" founded ", " campaign", " community", " society", " hospital", " church"),
        }.items():
            if any(word in f" {text} " for word in words):
                topics.add(topic)
        if discovery.collection == "lewisham-maroon":
            topics.add("lewisham")
        return topics or {"local-story"}

    def _select_ordered_route_points(self, request: RouteRequest) -> list[Discovery]:
        candidates = sorted(
            (point for point in self._discoveries if point.route_order is not None),
            key=lambda point: point.route_order or 0,
        )
        if not candidates:
            return []

        budget_seconds = request.duration_minutes * 60 * 0.90
        selected: list[Discovery] = []
        start_index = min(range(len(candidates)), key=lambda index: haversine_m(request.start, candidates[index].coordinate))
        ordered = candidates[start_index:] + candidates[:start_index]

        for point in ordered[: request.max_discoveries]:
            candidate_selection = selected + [point]
            endpoint = request.end if request.end is not None else candidate_selection[-1].coordinate
            trial_points = [request.start, *[item.coordinate for item in candidate_selection], endpoint]
            distance = sum(haversine_m(a, b) for a, b in zip(trial_points, trial_points[1:]))
            walking_seconds = distance / (request.walking_speed_kmh * 1000 / 3600)
            dwell_seconds = self._dwell_seconds(candidate_selection, request)
            if walking_seconds + dwell_seconds > budget_seconds and selected:
                break
            if walking_seconds + dwell_seconds <= budget_seconds:
                selected.append(point)
        return selected

    def _dwell_seconds(self, points: list[Discovery], request: RouteRequest) -> float:
        if request.route_mode is RouteMode.BLOSSOM_WALK:
            return 0.0
        return sum(
            0.0 if point.kind is DiscoveryKind.BLOSSOM else request.discovery_dwell_minutes * 60
            for point in points
        )

    def _select_amenities(self, request: RouteRequest, discoveries: list[Discovery], warnings: list[str]) -> list[AmenityStop]:
        if request.stop_preference is StopPreference.NONE or self._amenity_provider is None:
            return []
        kind = "pub" if "PUB" in request.stop_preference.name else "cafe"
        centre = discoveries[-1].coordinate if discoveries else request.start
        if request.stop_preference in (StopPreference.CAFE_ALONG, StopPreference.PUB_ALONG) and discoveries:
            centre = discoveries[len(discoveries) // 2].coordinate
        try:
            candidates = self._amenity_provider.search(centre, kind)
        except Exception as error:
            warnings.append(f"Could not find a nearby {kind}: {error}")
            return []
        if not candidates:
            warnings.append(f"No nearby {kind} found for the requested stop.")
            return []
        return [min(candidates, key=lambda amenity: haversine_m(centre, amenity.coordinate))]

    def _build_itinerary(
        self,
        request: RouteRequest,
        discoveries: list[Discovery],
        amenities: list[AmenityStop],
    ) -> tuple[list[Coordinate], list[RouteVisit]]:
        visits: list[RouteVisit] = []
        ordered_stops: list[Discovery | AmenityStop] = []
        if amenities and request.stop_preference in (StopPreference.CAFE_ALONG, StopPreference.PUB_ALONG):
            midpoint = max(1, len(discoveries) // 2)
            ordered_stops.extend(discoveries[:midpoint])
            ordered_stops.append(amenities[0])
            ordered_stops.extend(discoveries[midpoint:])
        else:
            ordered_stops.extend(discoveries)
        if amenities and request.stop_preference in (StopPreference.CAFE_END, StopPreference.PUB_END):
            ordered_stops.append(amenities[0])

        points = [request.start]
        for stop in ordered_stops:
            points.append(stop.coordinate)
            if isinstance(stop, Discovery):
                visits.append(
                    RouteVisit(
                        kind=stop.kind.value,
                        title=stop.title,
                        coordinate=stop.coordinate,
                        description=stop.description,
                        address=stop.address,
                        source_id=stop.id,
                    )
                )
            else:
                visits.append(
                    RouteVisit(
                        kind=stop.kind,
                        title=stop.name,
                        coordinate=stop.coordinate,
                        address=stop.tags.get("addr:full", ""),
                        source_id=stop.id,
                    )
                )

        if amenities and request.stop_preference in (StopPreference.CAFE_END, StopPreference.PUB_END):
            pass
        elif request.end is not None:
            points.append(request.end)
            visits.append(RouteVisit(kind="end", title="End point", coordinate=request.end))
        elif request.route_mode is RouteMode.BLOSSOM_WALK and discoveries:
            visits.append(RouteVisit(kind="end", title="Continue from Freddy's Blossom Walk", coordinate=discoveries[-1].coordinate))
        else:
            points.append(request.start)
            visits.append(RouteVisit(kind="end", title="Return to start", coordinate=request.start))
        return points, visits
