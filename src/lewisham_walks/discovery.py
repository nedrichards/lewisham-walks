from __future__ import annotations

import re

from .models import Coordinate, Discovery, DiscoveryKind, RouteTheme
from .planner import haversine_m

LEWISHAM_CENTRE = Coordinate(51.4615, -0.0117)

THEME_LABELS = {
    RouteTheme.SURPRISE: "A bit of everything",
    RouteTheme.PEOPLE: "People & creativity",
    RouteTheme.PLACES: "Places & change",
    RouteTheme.LEWISHAM: "Lewisham's own plaques",
}

_PEOPLE_WORDS = {
    "actor", "artist", "author", "born", "campaigner", "composer", "designer",
    "director", "entertainer", "founder", "historian", "lived", "musician",
    "novelist", "painter", "photographer", "poet", "politician", "sculptor",
    "singer", "writer",
}
_PLACE_WORDS = {
    "bridge", "built", "building", "church", "cinema", "creek", "factory",
    "flood", "garden", "hall", "hospital", "house", "market", "mill", "park",
    "railway", "school", "site", "station", "street", "theatre", "war",
}


def discovery_topics(discovery: Discovery) -> set[str]:
    text = f"{discovery.title} {discovery.description}".lower()
    words = set(re.findall(r"[a-z]+", text))
    topics: set[str] = set()
    if words & _PEOPLE_WORDS:
        topics.add("people")
    if words & _PLACE_WORDS:
        topics.add("places")
    if discovery.collection == "lewisham-maroon":
        topics.add("lewisham")
    return topics or {"local-story"}


def discoveries_for_theme(discoveries: list[Discovery], theme: RouteTheme) -> list[Discovery]:
    if theme is RouteTheme.LEWISHAM:
        return [discovery for discovery in discoveries if discovery.collection == "lewisham-maroon"]
    if theme is RouteTheme.PEOPLE:
        return [discovery for discovery in discoveries if "people" in discovery_topics(discovery)]
    if theme is RouteTheme.PLACES:
        return [discovery for discovery in discoveries if "places" in discovery_topics(discovery)]
    return list(discoveries)


def featured_discoveries(
    discoveries: list[Discovery],
    centre: Coordinate = LEWISHAM_CENTRE,
    limit: int = 24,
) -> list[Discovery]:
    """Return a Lewisham-first preview with a little deliberate border context."""
    ranked = sorted(
        discoveries,
        key=lambda discovery: (
            0 if discovery.borough.casefold() == "lewisham" else 1,
            0 if discovery.curation_status == "in_scope" else 1,
            0 if discovery.collection == "lewisham-maroon" else 1,
            0 if len(discovery.title) <= 62 else 1,
            0 if discovery.is_accurate else 1,
            haversine_m(centre, discovery.coordinate),
        ),
    )

    border_quota = 2 if limit >= 16 else 1 if limit >= 8 else 0
    border_discoveries: list[Discovery] = []
    for borough in ("Greenwich", "Southwark"):
        candidates = sorted(
            (
                item for item in discoveries
                if item.kind is DiscoveryKind.PLAQUE
                and item.borough.casefold() == borough.casefold()
                and item.is_accurate
            ),
            key=lambda item: haversine_m(centre, item.coordinate),
        )
        border_discoveries.extend(candidates[:border_quota])

    local_limit = max(0, limit - len(border_discoveries))
    featured: list[Discovery] = []

    def append_unique(discovery: Discovery) -> bool:
        if any(haversine_m(discovery.coordinate, existing.coordinate) < 25 for existing in featured):
            return False
        featured.append(discovery)
        return True

    for discovery in ranked:
        if discovery in border_discoveries:
            continue
        append_unique(discovery)
        if len(featured) == local_limit:
            break
    for discovery in border_discoveries:
        append_unique(discovery)
    for discovery in ranked:
        if len(featured) >= limit:
            break
        append_unique(discovery)
    return featured


def display_title(discovery: Discovery) -> str:
    title = " ".join(discovery.title.split()).strip(" .")
    if not title:
        return "Local story"
    if len(title) <= 62:
        return title

    # Open Plaques' thin export has no subject field, so imports sometimes use
    # the opening words of the inscription. Prefer a natural first clause.
    clause = re.split(r"[.;:]", title, maxsplit=1)[0].strip()
    if 12 <= len(clause) <= 62:
        return clause
    shortened = title[:59].rsplit(" ", 1)[0]
    return f"{shortened}…"


def story_preview(discovery: Discovery, limit: int = 150) -> str:
    text = " ".join((discovery.description or discovery.title).split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rsplit(' ', 1)[0]}…"


def source_label(discovery: Discovery) -> str:
    if discovery.collection == "lewisham-maroon":
        return "Lewisham maroon plaque"
    if discovery.kind is DiscoveryKind.BLOSSOM:
        return discovery.source_name or "Freddy's Blossom Walk"
    if discovery.borough:
        return f"{discovery.source_name or 'Open Plaques'} · {discovery.borough}"
    return discovery.source_name or "Local discovery"
