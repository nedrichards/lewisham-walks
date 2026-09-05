#!/usr/bin/env python3
"""Capture the main window from the installed Flatpak for visual review."""

from __future__ import annotations

import os
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
            "[plan|results|route|directions|map|map-story|stories|story|shortcuts|about]]"
        )
    output = Path(sys.argv[1]).resolve()
    width, height = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) == 4 else (1440, 820)
    if len(sys.argv) == 5:
        width, height = int(sys.argv[2]), int(sys.argv[3])
    page = sys.argv[4] if len(sys.argv) == 5 else "plan"
    if page not in {
        "plan",
        "results",
        "route",
        "directions",
        "map",
        "map-story",
        "stories",
        "story",
        "shortcuts",
        "about",
    }:
        raise SystemExit(
            "page must be 'plan', 'results', 'route', 'directions', 'map', 'map-story', "
            "'stories', 'story', 'shortcuts' or 'about'"
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
    if page in {"stories", "story"}:
        target_window = DiscoveryBrowserWindow(
            window,
            [*window.all_discoveries, *window.all_blossom_points],
            lambda _discovery: None,
        )
    else:
        target_window = window
        window._apply_responsive_layout(width, height)
        if page in {"results", "route", "directions"}:
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
        elif page == "about":
            window.present()
            window._show_about(None)
    target_window.set_default_size(width, height)
    target_window.present()
    loop = GLib.MainLoop.new(None, False)
    capture_attempts = 0
    capture_errors: list[Exception] = []

    def settle_layout() -> bool:
        if page not in {"stories", "story"}:
            window._apply_responsive_layout(window.get_width(), window.get_height())
        if page == "map":
            window.sidebar_button.set_active(False)
        if page == "map-story":
            window.sidebar_button.set_active(False)
            window._show_map_discovery_flyout(window.all_discoveries[0])
        if page == "story":
            row = target_window.list_box.get_first_child()
            if row is not None:
                target_window.list_box.emit("row-activated", row)
        return GLib.SOURCE_REMOVE

    def capture() -> bool:
        nonlocal capture_attempts
        try:
            width = target_window.get_width()
            height = target_window.get_height()
            # Include the window background and header in review captures.
            # Snapshotting only its child leaves transparent areas black in viewers.
            paintable = Gtk.WidgetPaintable.new(target_window)
            snapshot = Gtk.Snapshot.new()
            paintable.snapshot(snapshot, width, height)
            node = snapshot.to_node()
            surface = target_window.get_surface()
            if node is None or surface is None:
                capture_attempts += 1
                if capture_attempts < 3:
                    GLib.timeout_add(500, capture)
                    return GLib.SOURCE_REMOVE
                raise RuntimeError("Window did not produce a render node")
            renderer = Gsk.Renderer.new_for_surface(surface)
            bounds = Graphene.Rect().init(0, 0, width, height)
            texture = renderer.render_texture(node, bounds)
            if not isinstance(texture, Gdk.Texture) or not texture.save_to_png(str(output)):
                raise RuntimeError("Could not save the rendered window")
            renderer.unrealize()
        # This idle callback must report renderer failures to the calling thread.
        except Exception as error:  # noqa: BLE001
            capture_errors.append(error)
        GLib.idle_add(shutdown)
        return GLib.SOURCE_REMOVE

    def shutdown() -> bool:
        if page == "about" and window._about_dialog is not None:
            window._about_dialog.close()
        if target_window is not window:
            target_window.close()
        window.close()
        app.quit()
        loop.quit()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(750, settle_layout)
    GLib.timeout_add(max(3000, int(os.environ.get("LEWISHAM_WALKS_CAPTURE_DELAY_MS", "3000"))), capture)
    loop.run()
    if capture_errors:
        raise capture_errors[0]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
