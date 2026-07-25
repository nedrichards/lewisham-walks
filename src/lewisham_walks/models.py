from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True)
class Coordinate:
    lat: float
    lon: float


class DiscoveryKind(str, Enum):
    PLAQUE = "plaque"
    BLOSSOM = "blossom"


@dataclass(frozen=True)
class Discovery:
    id: str
    title: str
    description: str
    coordinate: Coordinate
    address: str = ""
    kind: DiscoveryKind = DiscoveryKind.PLAQUE
    collection: str = ""
    source_name: str = ""
    source_url: str = ""
    image_url: str = ""
    external_id: str = ""
    borough: str = ""
    is_accurate: bool = False
    curation_status: str = "candidate"
    curation_note: str = ""
    route_order: int | None = None
    attributes: dict[str, str] = field(default_factory=dict)

    @property
    def coordinate_label(self) -> str:
        return f"{self.coordinate.lat:.5f}, {self.coordinate.lon:.5f}"


class StopPreference(str, Enum):
    NONE = "none"
    CAFE_END = "cafe_end"
    PUB_END = "pub_end"
    CAFE_ALONG = "cafe_along"
    PUB_ALONG = "pub_along"


class RouteMode(str, Enum):
    DISCOVERIES = "discoveries"
    BLOSSOM_WALK = "blossom_walk"
    MIXED = "mixed"


class RouteTheme(str, Enum):
    SURPRISE = "surprise"
    PEOPLE = "people"
    PLACES = "places"
    LEWISHAM = "lewisham"


@dataclass(frozen=True)
class AmenityStop:
    id: str
    name: str
    kind: str
    coordinate: Coordinate
    tags: dict[str, str] = field(default_factory=dict)
    detour_minutes: float = 0.0


@dataclass(frozen=True)
class RouteRequest:
    start: Coordinate
    duration_minutes: int
    stop_preference: StopPreference = StopPreference.NONE
    end: Coordinate | None = None
    max_discoveries: int = 8
    walking_speed_kmh: float = 4.5
    discovery_dwell_minutes: float = 3.0
    route_mode: RouteMode = RouteMode.DISCOVERIES
    route_theme: RouteTheme = RouteTheme.SURPRISE
    seen_story_ids: tuple[str, ...] = ()
    variation_seed: int = 0


@dataclass(frozen=True)
class RouteStep:
    instruction: str
    distance_m: float
    duration_s: float


@dataclass(frozen=True)
class RouteVisit:
    kind: str
    title: str
    coordinate: Coordinate
    description: str = ""
    address: str = ""
    source_id: str = ""

    @property
    def coordinate_label(self) -> str:
        return f"{self.coordinate.lat:.5f}, {self.coordinate.lon:.5f}"


@dataclass(frozen=True)
class RoutePlan:
    request: RouteRequest
    discoveries: list[Discovery]
    amenities: list[AmenityStop]
    visits: list[RouteVisit]
    waypoints: list[Coordinate]
    geometry: list[Coordinate]
    steps: list[RouteStep]
    distance_m: float
    walking_seconds: float
    dwell_seconds: float
    warnings: list[str] = field(default_factory=list)

    @property
    def total_seconds(self) -> float:
        return self.walking_seconds + self.dwell_seconds

    @property
    def total_minutes(self) -> float:
        return self.total_seconds / 60.0
