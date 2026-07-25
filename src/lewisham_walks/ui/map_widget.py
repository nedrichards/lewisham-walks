from __future__ import annotations

import json
import math
from collections.abc import Callable

import gi

try:
    gi.require_version("Gdk", "4.0")
    gi.require_version("Shumate", "1.0")
    from gi.repository import Gdk, Shumate

    HAS_SHUMATE = True
except (ImportError, ValueError):
    Gdk = None
    Shumate = None
    HAS_SHUMATE = False

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from ..map_geometry import (
    MapBounds,
    coordinate_bounds,
    discoveries_for_viewport,
    find_discovery_at_position,
    project_coordinate,
    unproject_coordinate,
)
from ..models import Coordinate, Discovery, DiscoveryKind, RoutePlan, RouteVisit
from .layout import MAP_COMPACT_MIN_HEIGHT, MAP_COMPACT_MIN_WIDTH

DiscoveryCallback = Callable[[Discovery], None]
VisitCallback = Callable[[RouteVisit], None]


def create_map_widget(
    discoveries: list[Discovery],
    discovery_pool: list[Discovery] | None = None,
) -> Gtk.Widget:
    if HAS_SHUMATE:
        return ShumateDiscoveryMapWidget(discoveries, discovery_pool)
    return DiscoveryMapWidget(discoveries, discovery_pool)


class ShumateDiscoveryMapWidget(Gtk.Box):
    VIEWPORT_DISCOVERY_MIN = 18
    VIEWPORT_DISCOVERY_MAX = 48
    VIEWPORT_PIXELS_PER_DISCOVERY = 14_000
    VIEWPORT_REFRESH_DELAY_MS = 180

    def __init__(self, discoveries: list[Discovery], discovery_pool: list[Discovery] | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_hexpand(True)
        self.set_vexpand(True)
        # Keep only a genuinely compact floor. The surrounding adaptive split
        # view gives the map all remaining desktop space; a desktop-sized hard
        # request here would prevent the window from ever reaching its compact
        # breakpoint during an interactive resize.
        self.set_size_request(MAP_COMPACT_MIN_WIDTH, MAP_COMPACT_MIN_HEIGHT)
        self._discoveries = discoveries
        self._discovery_pool = list(discovery_pool if discovery_pool is not None else discoveries)
        self._discovery_refresh_source_id = 0
        self._plan: RoutePlan | None = None
        self._picked_start: Coordinate | None = None
        self._picked_end: Coordinate | None = None
        self._location_selected_callback: Callable[[Coordinate], None] | None = None
        self._discovery_selected_callback: DiscoveryCallback | None = None
        self._visit_selected_callback: VisitCallback | None = None
        self._discovery_selection_enabled = True

        self._map_view = Shumate.SimpleMap.new()
        self._map_view.set_hexpand(True)
        self._map_view.set_vexpand(True)
        self._map_view.set_show_zoom_buttons(True)
        self.append(self._map_view)

        self._map = self._map_view.get_map()
        self._viewport = self._map_view.get_viewport()
        for property_name in ("latitude", "longitude", "zoom-level"):
            self._viewport.connect(f"notify::{property_name}", self._schedule_discovery_refresh)
        self._map_view.connect("notify::width", self._schedule_discovery_refresh)
        self._map_view.connect("notify::height", self._schedule_discovery_refresh)
        self._route_layer = Shumate.PathLayer.new(self._viewport)
        self._route_layer.set_stroke_width(5.0)
        self._route_layer.set_outline_width(2.0)
        self._route_layer.set_stroke_color(_rgba("#1f6aa5"))
        self._route_layer.set_outline_color(_rgba("#ffffff"))
        self._marker_layer = Shumate.MarkerLayer.new(self._viewport)
        self._selection_layer = Shumate.MarkerLayer.new(self._viewport)
        self._click_gesture = Gtk.GestureClick.new()
        self._click_gesture.set_button(1)
        self._click_gesture.connect("released", self._on_map_clicked)
        self._map_view.add_controller(self._click_gesture)

        self._set_default_map_source()
        self._map_view.add_overlay_layer(self._route_layer)
        self._map_view.add_overlay_layer(self._marker_layer)
        self._map_view.add_overlay_layer(self._selection_layer)
        self._render_all_discoveries()
        self._render_picked_locations()
        self._centre_on(self._all_coordinates(), 13.0)

    def set_plan(self, plan: RoutePlan | None) -> None:
        self._plan = plan
        self._route_layer.remove_all()
        self._marker_layer.remove_all()
        self._selection_layer.remove_all()
        self._render_all_discoveries()
        if plan is not None:
            self._render_plan(plan)
            self._centre_on([*plan.geometry, *plan.waypoints], 14.0)
        self._render_picked_locations()

    def set_discoveries(
        self,
        discoveries: list[Discovery],
        discovery_pool: list[Discovery] | None = None,
    ) -> None:
        self._discoveries = discoveries
        self._discovery_pool = list(discovery_pool if discovery_pool is not None else discoveries)
        self._plan = None
        self._route_layer.remove_all()
        self._marker_layer.remove_all()
        self._selection_layer.remove_all()
        self._render_all_discoveries()
        self._render_picked_locations()
        self._centre_on(self._all_coordinates(), 13.0)
        self._schedule_discovery_refresh()

    def set_location_selected_callback(self, callback: Callable[[Coordinate], None] | None) -> None:
        self._location_selected_callback = callback

    def set_discovery_selected_callback(self, callback: DiscoveryCallback | None) -> None:
        self._discovery_selected_callback = callback
        self._refresh_markers()

    def set_visit_selected_callback(self, callback: VisitCallback | None) -> None:
        self._visit_selected_callback = callback
        self._refresh_markers()

    def set_discovery_selection_enabled(self, enabled: bool) -> None:
        self._discovery_selection_enabled = enabled
        self._refresh_markers()

    def set_picked_locations(self, start: Coordinate | None, end: Coordinate | None) -> None:
        self._picked_start = start
        self._picked_end = end
        self._render_picked_locations()

    def _set_default_map_source(self) -> None:
        map_source = self._create_vector_map_source()
        if map_source is None:
            registry = Shumate.MapSourceRegistry.new_with_defaults()
            map_source = registry.get_by_id("osm-mapnik")
        if map_source is not None:
            self._map_view.set_map_source(map_source)

    def _create_vector_map_source(self):
        if not hasattr(Shumate, "VectorRenderer") or not Shumate.VectorRenderer.is_supported():
            return None
        try:
            source = Shumate.VectorRenderer.new("gnome-openmaptiles", json.dumps(_GNOME_VECTOR_STYLE))
            source.set_property("name", "GNOME OpenMapTiles")
            source.set_property("license", "OpenMapTiles and OpenStreetMap contributors")
            source.set_property("license-uri", "https://www.openstreetmap.org/copyright")
            return source
        except Exception:
            return None

    def _render_all_discoveries(self) -> None:
        route_ids = {item.id for item in self._plan.discoveries} if self._plan is not None else set()
        for discovery in self._discoveries:
            if discovery.id in route_ids:
                continue
            self._marker_layer.add_marker(self._point_marker(discovery))

    def _schedule_discovery_refresh(self, *_args) -> None:
        if self._discovery_refresh_source_id:
            GLib.source_remove(self._discovery_refresh_source_id)
        self._discovery_refresh_source_id = GLib.timeout_add(
            self.VIEWPORT_REFRESH_DELAY_MS,
            self._refresh_visible_discoveries,
        )

    def _refresh_visible_discoveries(self) -> bool:
        self._discovery_refresh_source_id = 0
        width = self._map_view.get_width()
        height = self._map_view.get_height()
        if width <= 1 or height <= 1:
            return GLib.SOURCE_REMOVE
        try:
            corners = [
                self._viewport.widget_coords_to_location(self._map_view, x, y)
                for x, y in ((0, 0), (width, 0), (0, height), (width, height))
            ]
        except Exception:
            return GLib.SOURCE_REMOVE
        latitudes = [latitude for latitude, _longitude in corners]
        longitudes = [longitude for _latitude, longitude in corners]
        bounds = MapBounds(min(latitudes), max(latitudes), min(longitudes), max(longitudes))
        centre = Coordinate(self._viewport.get_latitude(), self._viewport.get_longitude())
        marker_limit = max(
            self.VIEWPORT_DISCOVERY_MIN,
            min(self.VIEWPORT_DISCOVERY_MAX, width * height // self.VIEWPORT_PIXELS_PER_DISCOVERY),
        )
        visible = discoveries_for_viewport(
            self._discovery_pool,
            bounds,
            centre,
            limit=marker_limit,
        )
        if [item.id for item in visible] != [item.id for item in self._discoveries]:
            self._discoveries = visible
            self._refresh_markers()
        return GLib.SOURCE_REMOVE

    def _render_plan(self, plan: RoutePlan) -> None:
        for coordinate in reversed(plan.geometry or plan.waypoints):
            self._route_layer.add_node(Shumate.Coordinate.new_full(coordinate.lat, coordinate.lon))

        for index, discovery in enumerate(plan.discoveries, start=1):
            self._marker_layer.add_marker(self._label_marker(discovery, str(index), discovery.title))

        if plan.waypoints:
            self._marker_layer.add_marker(
                self._label_marker(
                    RouteVisit(kind="start", title="Start point", coordinate=plan.waypoints[0]),
                    "S",
                    "Start point",
                )
            )
            if len(plan.waypoints) > 1:
                end_visit = next((visit for visit in reversed(plan.visits) if visit.kind == "end"), None)
                self._marker_layer.add_marker(
                    self._label_marker(
                        end_visit or RouteVisit(kind="end", title="End point", coordinate=plan.waypoints[-1]),
                        "E",
                        (end_visit.title if end_visit is not None else "End point"),
                    )
                )

        for visit in plan.visits:
            if visit.kind not in {"cafe", "pub"}:
                continue
            label = "C" if visit.kind == "cafe" else "P"
            self._marker_layer.add_marker(self._label_marker(visit, label, visit.title))

    def _render_picked_locations(self) -> None:
        self._selection_layer.remove_all()
        if self._picked_start is not None:
            self._selection_layer.add_marker(
                self._label_marker(RouteVisit(kind="start", title="Picked start", coordinate=self._picked_start), "S", "Picked start")
            )
        if self._picked_end is not None:
            self._selection_layer.add_marker(
                self._label_marker(RouteVisit(kind="end", title="Picked end", coordinate=self._picked_end), "E", "Picked end")
            )

    def _on_map_clicked(self, _gesture, n_press: int, x: float, y: float) -> None:
        if n_press != 1 or self._location_selected_callback is None:
            return
        latitude, longitude = self._viewport.widget_coords_to_location(self._map_view, x, y)
        self._location_selected_callback(Coordinate(latitude, longitude))

    def _point_marker(self, discovery: Discovery) -> object:
        marker = Shumate.Marker.new()
        marker.set_location(discovery.coordinate.lat, discovery.coordinate.lon)
        marker.set_tooltip_text(discovery.title)
        icon = Gtk.Image.new_from_icon_name("media-record-symbolic")
        icon.set_pixel_size(10)
        button = Gtk.Button.new()
        button.set_child(icon)
        button.set_tooltip_text(discovery.title)
        button.set_size_request(22, 22)
        button.add_css_class("circular")
        button.add_css_class("map-pin")
        if discovery.collection == "lewisham-maroon":
            button.add_css_class("local")
        button.set_sensitive(self._discovery_selection_enabled and self._discovery_selected_callback is not None)
        if self._discovery_selected_callback is not None:
            button.connect("clicked", lambda _button, current=discovery: self._discovery_selected_callback(current))
        marker.set_child(button)
        return marker

    def _label_marker(self, marker_item: Coordinate | Discovery | RouteVisit, label_text: str, tooltip: str) -> object:
        coordinate = marker_item.coordinate if hasattr(marker_item, "coordinate") else marker_item
        marker = Shumate.Marker.new()
        marker.set_location(coordinate.lat, coordinate.lon)
        child = Gtk.Button.new_with_label(label_text)
        child.add_css_class("flat")
        child.add_css_class("circular")
        child.set_size_request(28, 28)
        child.set_tooltip_text(tooltip)

        if isinstance(marker_item, Discovery):
            child.set_sensitive(self._discovery_selection_enabled and self._discovery_selected_callback is not None)
            if self._discovery_selected_callback is not None:
                child.connect("clicked", lambda _button, current=marker_item: self._discovery_selected_callback(current))
        elif isinstance(marker_item, RouteVisit):
            child.set_sensitive(self._visit_selected_callback is not None)
            if self._visit_selected_callback is not None:
                child.connect("clicked", lambda _button, current=marker_item: self._visit_selected_callback(current))
        else:
            child.set_sensitive(False)

        child.add_css_class("osd")
        child.add_css_class("route-marker")
        marker.set_child(child)
        marker.set_tooltip_text(tooltip)
        return marker

    def _refresh_markers(self) -> None:
        self._marker_layer.remove_all()
        self._render_all_discoveries()
        if self._plan is not None:
            self._render_plan(self._plan)
        self._render_picked_locations()

    def _all_coordinates(self) -> list[Coordinate]:
        coordinates = [discovery.coordinate for discovery in self._discoveries]
        if self._plan is not None:
            coordinates.extend(self._plan.geometry)
            coordinates.extend(self._plan.waypoints)
        if self._picked_start is not None:
            coordinates.append(self._picked_start)
        if self._picked_end is not None:
            coordinates.append(self._picked_end)
        return coordinates

    def _centre_on(self, coordinates: list[Coordinate], fallback_zoom: float) -> None:
        if not coordinates:
            self._map.go_to_full(51.462, -0.010, fallback_zoom)
            return
        bounds = coordinate_bounds(coordinates)
        latitude = (bounds.min_lat + bounds.max_lat) / 2
        longitude = (bounds.min_lon + bounds.max_lon) / 2
        zoom = min(fallback_zoom, _zoom_for_bounds(bounds))
        self._map.go_to_full(latitude, longitude, zoom)


class DiscoveryMapWidget(Gtk.DrawingArea):
    def __init__(self, discoveries: list[Discovery], discovery_pool: list[Discovery] | None = None) -> None:
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_content_width(MAP_COMPACT_MIN_WIDTH)
        self.set_content_height(MAP_COMPACT_MIN_HEIGHT)
        self._discoveries = discoveries
        self._discovery_pool = list(discovery_pool if discovery_pool is not None else discoveries)
        self._plan: RoutePlan | None = None
        self._picked_start: Coordinate | None = None
        self._picked_end: Coordinate | None = None
        self._location_selected_callback: Callable[[Coordinate], None] | None = None
        self._discovery_selected_callback: DiscoveryCallback | None = None
        self._visit_selected_callback: VisitCallback | None = None
        self._discovery_selection_enabled = True
        self._last_width = 560
        self._last_height = 560
        self._click_gesture = Gtk.GestureClick.new()
        self._click_gesture.set_button(1)
        self._click_gesture.connect("released", self._on_map_clicked)
        self.add_controller(self._click_gesture)
        self.set_draw_func(self._draw)

    def set_plan(self, plan: RoutePlan | None) -> None:
        self._plan = plan
        self.queue_draw()

    def set_discoveries(
        self,
        discoveries: list[Discovery],
        discovery_pool: list[Discovery] | None = None,
    ) -> None:
        self._discoveries = discoveries
        self._discovery_pool = list(discovery_pool if discovery_pool is not None else discoveries)
        self._plan = None
        self.queue_draw()

    def set_location_selected_callback(self, callback: Callable[[Coordinate], None] | None) -> None:
        self._location_selected_callback = callback

    def set_discovery_selected_callback(self, callback: DiscoveryCallback | None) -> None:
        self._discovery_selected_callback = callback

    def set_visit_selected_callback(self, callback: VisitCallback | None) -> None:
        self._visit_selected_callback = callback

    def set_discovery_selection_enabled(self, enabled: bool) -> None:
        self._discovery_selection_enabled = enabled

    def set_picked_locations(self, start: Coordinate | None, end: Coordinate | None) -> None:
        self._picked_start = start
        self._picked_end = end
        self.queue_draw()

    def _draw(self, _area, context, width: int, height: int) -> None:
        self._last_width = width
        self._last_height = height
        self._draw_background(context, width, height)
        bounds = self._current_bounds()
        self._draw_grid(context, width, height)
        self._draw_all_discoveries(context, bounds, width, height)
        if self._plan is not None:
            self._draw_plan(context, self._plan, bounds, width, height)
        self._draw_picked_locations(context, bounds, width, height)
        self._draw_caption(context, width, height)

    def _current_bounds(self) -> MapBounds:
        coordinates = [discovery.coordinate for discovery in self._discoveries]
        if self._plan is not None:
            coordinates.extend(self._plan.geometry)
            coordinates.extend(self._plan.waypoints)
        if self._picked_start is not None:
            coordinates.append(self._picked_start)
        if self._picked_end is not None:
            coordinates.append(self._picked_end)
        return coordinate_bounds(coordinates)

    def _draw_background(self, context, width: int, height: int) -> None:
        context.set_source_rgb(0.96, 0.97, 0.95)
        context.rectangle(0, 0, width, height)
        context.fill()
        context.set_source_rgb(0.78, 0.82, 0.78)
        context.set_line_width(1)
        context.rectangle(12, 12, max(width - 24, 0), max(height - 24, 0))
        context.stroke()

    def _draw_grid(self, context, width: int, height: int) -> None:
        context.set_source_rgba(0.55, 0.62, 0.58, 0.25)
        context.set_line_width(1)
        for index in range(1, 5):
            x = width * index / 5
            context.move_to(x, 20)
            context.line_to(x, height - 20)
            y = height * index / 5
            context.move_to(20, y)
            context.line_to(width - 20, y)
        context.stroke()

    def _draw_all_discoveries(self, context, bounds: MapBounds, width: int, height: int) -> None:
        for discovery in self._discoveries:
            x, y = project_coordinate(discovery.coordinate, bounds, width, height)
            if discovery.kind is DiscoveryKind.BLOSSOM:
                if discovery.collection == "freddys-blossom-outlying":
                    context.set_source_rgb(0.06, 0.45, 0.22)
                elif discovery.attributes.get("colour") == "yellow":
                    context.set_source_rgb(0.86, 0.66, 0.08)
                else:
                    context.set_source_rgb(0.10, 0.24, 0.62)
                radius = 3.6
            elif discovery.curation_status == "in_scope":
                context.set_source_rgb(0.45, 0.25, 0.12)
                radius = 4.5
            else:
                context.set_source_rgba(0.45, 0.25, 0.12, 0.42)
                radius = 3.2
            context.arc(x, y, radius, 0, math.tau)
            context.fill()

    def _draw_plan(self, context, plan: RoutePlan, bounds: MapBounds, width: int, height: int) -> None:
        route = plan.geometry or plan.waypoints
        if len(route) >= 2:
            context.set_source_rgb(0.10, 0.33, 0.57)
            context.set_line_width(4)
            context.set_line_join(1)
            first_x, first_y = project_coordinate(route[0], bounds, width, height)
            context.move_to(first_x, first_y)
            for coordinate in route[1:]:
                x, y = project_coordinate(coordinate, bounds, width, height)
                context.line_to(x, y)
            context.stroke()

        for index, discovery in enumerate(plan.discoveries, start=1):
            x, y = project_coordinate(discovery.coordinate, bounds, width, height)
            context.set_source_rgb(0.98, 0.86, 0.55)
            context.arc(x, y, 8, 0, math.tau)
            context.fill()
            context.set_source_rgb(0.12, 0.16, 0.18)
            context.set_line_width(1.2)
            context.arc(x, y, 8, 0, math.tau)
            context.stroke()
            self._draw_number(context, str(index), x, y)

        if plan.waypoints:
            self._draw_endpoint(context, plan.waypoints[0], bounds, width, height, "S", (0.10, 0.45, 0.20))
            self._draw_endpoint(context, plan.waypoints[-1], bounds, width, height, "E", (0.62, 0.16, 0.13))

        for amenity in plan.amenities:
            x, y = project_coordinate(amenity.coordinate, bounds, width, height)
            context.set_source_rgb(0.12, 0.43, 0.48)
            context.rectangle(x - 7, y - 7, 14, 14)
            context.fill()
            self._draw_number(context, "C" if amenity.kind == "cafe" else "P", x, y)

    def _draw_picked_locations(self, context, bounds: MapBounds, width: int, height: int) -> None:
        if self._picked_start is not None:
            self._draw_endpoint(context, self._picked_start, bounds, width, height, "S", (0.10, 0.45, 0.20))
        if self._picked_end is not None:
            self._draw_endpoint(context, self._picked_end, bounds, width, height, "E", (0.62, 0.16, 0.13))

    def _draw_endpoint(
        self,
        context,
        coordinate: Coordinate,
        bounds: MapBounds,
        width: int,
        height: int,
        label: str,
        colour: tuple[float, float, float],
    ) -> None:
        x, y = project_coordinate(coordinate, bounds, width, height)
        context.set_source_rgb(*colour)
        context.arc(x, y, 9, 0, math.tau)
        context.fill()
        self._draw_number(context, label, x, y)

    def _draw_number(self, context, text: str, x: float, y: float) -> None:
        context.set_source_rgb(1, 1, 1)
        context.select_font_face("Sans")
        context.set_font_size(10)
        extents = context.text_extents(text)
        context.move_to(x - extents.width / 2 - extents.x_bearing, y - extents.height / 2 - extents.y_bearing)
        context.show_text(text)

    def _draw_caption(self, context, width: int, height: int) -> None:
        context.set_source_rgba(0.12, 0.16, 0.18, 0.72)
        context.select_font_face("Sans")
        context.set_font_size(12)
        caption = f"{len(self._discoveries)} discoveries"
        if self._plan is not None:
            caption = f"{len(self._plan.discoveries)} discoveries · {self._plan.distance_m / 1000:.1f} km"
        context.move_to(24, height - 24)
        context.show_text(caption)

    def _on_map_clicked(self, _gesture, n_press: int, x: float, y: float) -> None:
        if n_press != 1:
            return
        if self._discovery_selection_enabled and self._discovery_selected_callback is not None:
            discovery = find_discovery_at_position(
                x,
                y,
                self._current_bounds(),
                self._last_width,
                self._last_height,
                self._plan.discoveries if self._plan is not None else self._discoveries,
            )
            if discovery is not None:
                self._discovery_selected_callback(discovery)
                return
        if self._plan is not None and self._visit_selected_callback is not None:
            visit = _find_visit_at_position(
                x,
                y,
                self._current_bounds(),
                self._last_width,
                self._last_height,
                self._interactive_visits(),
            )
            if visit is not None:
                self._visit_selected_callback(visit)
                return
        if self._location_selected_callback is None:
            return
        bounds = self._current_bounds()
        self._location_selected_callback(unproject_coordinate(x, y, bounds, self._last_width, self._last_height))

    def _interactive_visits(self) -> list[RouteVisit]:
        if self._plan is None:
            return []
        visits = [RouteVisit(kind="start", title="Start point", coordinate=self._plan.waypoints[0])] if self._plan.waypoints else []
        visits.extend(visit for visit in self._plan.visits if visit.kind in {"cafe", "pub", "end"})
        return visits


def _rgba(value: str):
    colour = Gdk.RGBA()
    colour.parse(value)
    return colour


def _zoom_for_bounds(bounds: MapBounds) -> float:
    span = max(bounds.max_lat - bounds.min_lat, bounds.max_lon - bounds.min_lon)
    if span <= 0.01:
        return 15.0
    if span <= 0.025:
        return 14.0
    if span <= 0.05:
        return 13.0
    return 12.0


def _find_visit_at_position(
    x: float,
    y: float,
    bounds: MapBounds,
    width: int,
    height: int,
    visits: list[RouteVisit],
    threshold: float = 16.0,
) -> RouteVisit | None:
    closest: tuple[float, RouteVisit] | None = None
    for visit in visits:
        visit_x, visit_y = project_coordinate(visit.coordinate, bounds, width, height)
        distance = math.hypot(visit_x - x, visit_y - y)
        if distance > threshold:
            continue
        if closest is None or distance < closest[0]:
            closest = (distance, visit)
    return closest[1] if closest is not None else None


_GNOME_VECTOR_STYLE = {
    "version": 8,
    "name": "Lewisham Walks",
    "sources": {
        "openmaptiles": {
            "type": "vector",
            "tiles": ["https://tileserver-gl-light.apps.openshift.gnome.org/data/v3/{z}/{x}/{y}.pbf"],
            "minzoom": 0,
            "maxzoom": 14,
        }
    },
    "layers": [
        {
            "id": "background",
            "type": "background",
            "paint": {"background-color": "#ece7da"},
        },
        {
            "id": "park",
            "type": "fill",
            "source": "openmaptiles",
            "source-layer": "landcover",
            "filter": ["in", "class", "grass", "wood"],
            "paint": {"fill-color": "#b9d69b", "fill-opacity": 0.55},
        },
        {
            "id": "landuse",
            "type": "fill",
            "source": "openmaptiles",
            "source-layer": "landuse",
            "filter": ["in", "class", "residential", "suburb", "neighbourhood"],
            "paint": {"fill-color": "#e2dccf", "fill-opacity": 0.55},
        },
        {
            "id": "water",
            "type": "fill",
            "source": "openmaptiles",
            "source-layer": "water",
            "paint": {"fill-color": "#9ec8df"},
        },
        {
            "id": "waterway",
            "type": "line",
            "source": "openmaptiles",
            "source-layer": "waterway",
            "paint": {"line-color": "#9ec8df", "line-width": 1.5},
        },
        {
            "id": "building",
            "type": "fill",
            "source": "openmaptiles",
            "source-layer": "building",
            "minzoom": 15,
            "paint": {"fill-color": "#d5c6ad", "fill-opacity": 0.75},
        },
        {
            "id": "road-path",
            "type": "line",
            "source": "openmaptiles",
            "source-layer": "transportation",
            "filter": ["in", "class", "path", "track"],
            "paint": {"line-color": "#ffffff", "line-width": 1.2, "line-dasharray": [1, 1]},
        },
        {
            "id": "road-minor",
            "type": "line",
            "source": "openmaptiles",
            "source-layer": "transportation",
            "filter": ["in", "class", "minor", "service"],
            "paint": {"line-color": "#ffffff", "line-width": 1.8},
        },
        {
            "id": "road-major",
            "type": "line",
            "source": "openmaptiles",
            "source-layer": "transportation",
            "filter": ["in", "class", "primary", "secondary", "tertiary", "trunk"],
            "paint": {"line-color": "#fff7d6", "line-width": 3.0},
        },
        {
            "id": "rail",
            "type": "line",
            "source": "openmaptiles",
            "source-layer": "transportation",
            "filter": ["in", "class", "rail", "transit"],
            "paint": {"line-color": "#9a958c", "line-width": 1.2},
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
            "paint": {"text-color": "#333333", "text-halo-color": "#ffffff", "text-halo-width": 1.5},
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
            "paint": {"text-color": "#333333", "text-halo-color": "#ffffff", "text-halo-width": 1.5},
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
            "paint": {"text-color": "#555555", "text-halo-color": "#ffffff", "text-halo-width": 1},
        },
    ],
}
