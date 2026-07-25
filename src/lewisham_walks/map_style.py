from __future__ import annotations

GNOME_VECTOR_TILE_URL = "https://tileserver-gl-light.apps.openshift.gnome.org/data/v3/{z}/{x}/{y}.pbf"


def vector_map_style(dark: bool) -> dict[str, object]:
    """Build the local map style while keeping the same open vector tiles."""
    palette = (
        {
            "background": "#171a1d",
            "park": "#263d2d",
            "landuse": "#20252a",
            "water": "#18384a",
            "building": "#30343a",
            "path": "#555e68",
            "minor-road": "#606872",
            "major-road": "#887951",
            "rail": "#737b85",
            "label": "#d8dde3",
            "secondary-label": "#b9c0c8",
            "halo": "#15181b",
        }
        if dark
        else {
            "background": "#ece7da",
            "park": "#b9d69b",
            "landuse": "#e2dccf",
            "water": "#9ec8df",
            "building": "#d5c6ad",
            "path": "#ffffff",
            "minor-road": "#ffffff",
            "major-road": "#fff7d6",
            "rail": "#9a958c",
            "label": "#333333",
            "secondary-label": "#555555",
            "halo": "#ffffff",
        }
    )

    return {
        "version": 8,
        "name": f"Lewisham Walks {'Night' if dark else 'Day'}",
        "sources": {
            "openmaptiles": {
                "type": "vector",
                "tiles": [GNOME_VECTOR_TILE_URL],
                "minzoom": 0,
                "maxzoom": 14,
            }
        },
        "layers": [
            {
                "id": "background",
                "type": "background",
                "paint": {"background-color": palette["background"]},
            },
            {
                "id": "park",
                "type": "fill",
                "source": "openmaptiles",
                "source-layer": "landcover",
                "filter": ["in", "class", "grass", "wood"],
                "paint": {"fill-color": palette["park"], "fill-opacity": 0.68 if dark else 0.55},
            },
            {
                "id": "landuse",
                "type": "fill",
                "source": "openmaptiles",
                "source-layer": "landuse",
                "filter": ["in", "class", "residential", "suburb", "neighbourhood"],
                "paint": {"fill-color": palette["landuse"], "fill-opacity": 0.72 if dark else 0.55},
            },
            {
                "id": "water",
                "type": "fill",
                "source": "openmaptiles",
                "source-layer": "water",
                "paint": {"fill-color": palette["water"]},
            },
            {
                "id": "waterway",
                "type": "line",
                "source": "openmaptiles",
                "source-layer": "waterway",
                "paint": {"line-color": palette["water"], "line-width": 1.5},
            },
            {
                "id": "building",
                "type": "fill",
                "source": "openmaptiles",
                "source-layer": "building",
                "minzoom": 15,
                "paint": {"fill-color": palette["building"], "fill-opacity": 0.8 if dark else 0.75},
            },
            {
                "id": "road-path",
                "type": "line",
                "source": "openmaptiles",
                "source-layer": "transportation",
                "filter": ["in", "class", "path", "track"],
                "paint": {"line-color": palette["path"], "line-width": 1.2, "line-dasharray": [1, 1]},
            },
            {
                "id": "road-minor",
                "type": "line",
                "source": "openmaptiles",
                "source-layer": "transportation",
                "filter": ["in", "class", "minor", "service"],
                "paint": {"line-color": palette["minor-road"], "line-width": 1.8},
            },
            {
                "id": "road-major",
                "type": "line",
                "source": "openmaptiles",
                "source-layer": "transportation",
                "filter": ["in", "class", "primary", "secondary", "tertiary", "trunk"],
                "paint": {"line-color": palette["major-road"], "line-width": 3.0},
            },
            {
                "id": "rail",
                "type": "line",
                "source": "openmaptiles",
                "source-layer": "transportation",
                "filter": ["in", "class", "rail", "transit"],
                "paint": {"line-color": palette["rail"], "line-width": 1.2},
            },
            {
                "id": "road-label",
                "type": "symbol",
                "source": "openmaptiles",
                "source-layer": "transportation_name",
                "minzoom": 14,
                "layout": {
                    "symbol-placement": "line",
                    "text-field": "{name}",
                    "text-font": ["Noto Sans Regular"],
                    "text-size": 11,
                },
                "paint": {
                    "text-color": palette["label"],
                    "text-halo-color": palette["halo"],
                    "text-halo-width": 1.5,
                },
            },
            {
                "id": "place-label",
                "type": "symbol",
                "source": "openmaptiles",
                "source-layer": "place",
                "layout": {
                    "text-field": "{name}",
                    "text-font": ["Noto Sans Regular"],
                    "text-size": 13,
                },
                "paint": {
                    "text-color": palette["label"],
                    "text-halo-color": palette["halo"],
                    "text-halo-width": 1.5,
                },
            },
            {
                "id": "poi-label",
                "type": "symbol",
                "source": "openmaptiles",
                "source-layer": "poi",
                "minzoom": 16,
                "layout": {
                    "text-field": "{name}",
                    "text-font": ["Noto Sans Regular"],
                    "text-size": 10,
                },
                "paint": {
                    "text-color": palette["secondary-label"],
                    "text-halo-color": palette["halo"],
                    "text-halo-width": 1,
                },
            },
        ],
    }
