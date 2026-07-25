#!/usr/bin/env python3
"""Capture the main window from the installed Flatpak for visual review."""

from __future__ import annotations

import sys
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Graphene", "1.0")

from gi.repository import Adw, Gdk, Gio, GLib, Graphene, Gsk, Gtk

from lewisham_walks.main import LewishamWalksApp
from lewisham_walks.models import Coordinate, RouteRequest
from lewisham_walks.planner import RoutePlanner
from lewisham_walks.ui.discovery_browser_window import DiscoveryBrowserWindow
from lewisham_walks.ui.main_window import MainWindow


def main() -> int:
    if len(sys.argv) not in (2, 4, 5):
        raise SystemExit(
            "usage: capture_ui.py OUTPUT.png [WIDTH HEIGHT "
            "[plan|results|route|directions|map|stories|shortcuts]]"
        )
    output = Path(sys.argv[1]).resolve()
    width, height = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) == 4 else (1440, 820)
    if len(sys.argv) == 5:
        width, height = int(sys.argv[2]), int(sys.argv[3])
    page = sys.argv[4] if len(sys.argv) == 5 else "plan"
    if page not in {"plan", "results", "route", "directions", "map", "stories", "shortcuts"}:
        raise SystemExit(
            "page must be 'plan', 'results', 'route', 'directions', 'map', 'stories' or 'shortcuts'"
        )
    Adw.init()
    settings = Gtk.Settings.get_default()
    if settings is not None:
        settings.set_property("gtk-enable-animations", False)
    app = LewishamWalksApp("development")
    # UI review captures must remain isolated from an interactive app or a
    # Builder-launched instance that owns the normal application bus name.
    app.set_flags(app.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
    app._load_styles()
    if not app.register():
        raise RuntimeError("Could not register the capture application")
    window = MainWindow(app)
    if page == "stories":
        target_window = DiscoveryBrowserWindow(
            window,
            [*window.all_discoveries, *window.all_blossom_points],
            lambda _discovery: None,
        )
    else:
        target_window = window
        window._apply_responsive_layout(width, height)
        if page in {"route", "directions"}:
            plan = RoutePlanner(window.all_discoveries).plan(
                RouteRequest(
                    start=Coordinate(51.462, -0.010),
                    duration_minutes=75,
                    max_discoveries=5,
                )
            )
            window._render_plan(plan)
        window._show_controls_page(
            "directions" if page == "directions" else "results" if page in {"results", "route"} else "planner"
        )
        if page == "shortcuts":
            window.present()
            window._show_shortcuts(None)
            target_window = window._shortcuts_window
    target_window.set_default_size(width, height)
    target_window.present()
    loop = GLib.MainLoop.new(None, False)

    def settle_layout() -> bool:
        if page != "stories":
            window._apply_responsive_layout(window.get_width(), window.get_height())
        if page == "map":
            window.sidebar_button.set_active(False)
        return GLib.SOURCE_REMOVE

    def capture() -> bool:
        width = target_window.get_width()
        height = target_window.get_height()
        content = (
            target_window
            if page == "shortcuts"
            else target_window.get_content()
            if hasattr(target_window, "get_content")
            else target_window.get_child()
        )
        if content is None:
            raise RuntimeError("Window did not expose any content to capture")
        paintable = Gtk.WidgetPaintable.new(content)
        snapshot = Gtk.Snapshot.new()
        paintable.snapshot(snapshot, width, height)
        node = snapshot.to_node()
        surface = target_window.get_surface()
        if node is None or surface is None:
            raise RuntimeError("Window did not produce a render node")
        renderer = Gsk.Renderer.new_for_surface(surface)
        bounds = Graphene.Rect().init(0, 0, width, height)
        texture = renderer.render_texture(node, bounds)
        if not isinstance(texture, Gdk.Texture) or not texture.save_to_png(str(output)):
            raise RuntimeError("Could not save the rendered window")
        renderer.unrealize()
        GLib.idle_add(shutdown)
        return GLib.SOURCE_REMOVE

    def shutdown() -> bool:
        # This helper is a short-lived process. Let process teardown release the
        # transient and its parent together so GSK cannot outlive either surface.
        loop.quit()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(750, settle_layout)
    GLib.timeout_add(3000, capture)
    loop.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
