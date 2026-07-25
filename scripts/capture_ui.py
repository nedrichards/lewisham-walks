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

from gi.repository import Adw, Gdk, GLib, Graphene, Gsk, Gtk

from lewisham_walks.main import LewishamWalksApp
from lewisham_walks.ui.main_window import MainWindow


def main() -> int:
    if len(sys.argv) not in (2, 4, 5):
        raise SystemExit("usage: capture_ui.py OUTPUT.png [WIDTH HEIGHT [plan|results|map]]")
    output = Path(sys.argv[1]).resolve()
    width, height = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) == 4 else (1440, 820)
    if len(sys.argv) == 5:
        width, height = int(sys.argv[2]), int(sys.argv[3])
    page = sys.argv[4] if len(sys.argv) == 5 else "plan"
    if page not in {"plan", "results", "map"}:
        raise SystemExit("page must be 'plan', 'results' or 'map'")
    Adw.init()
    settings = Gtk.Settings.get_default()
    if settings is not None:
        settings.set_property("gtk-enable-animations", False)
    app = LewishamWalksApp("development")
    app._load_styles()
    # A standalone window avoids taking ownership of the installed app's D-Bus
    # name, which may already belong to an interactive instance during review.
    window = MainWindow(None)
    window.set_default_size(width, height)
    window._apply_responsive_layout(width, height)
    window._show_controls_page("results" if page == "results" else "planner")
    window.present()
    loop = GLib.MainLoop.new(None, False)

    def settle_layout() -> bool:
        window._apply_responsive_layout(window.get_width(), window.get_height())
        if page == "map":
            window.sidebar_button.set_active(False)
        return GLib.SOURCE_REMOVE

    def capture() -> bool:
        width = window.get_width()
        height = window.get_height()
        content = window.get_content()
        paintable = Gtk.WidgetPaintable.new(content)
        snapshot = Gtk.Snapshot.new()
        paintable.snapshot(snapshot, width, height)
        node = snapshot.to_node()
        surface = window.get_surface()
        if node is None or surface is None:
            raise RuntimeError("Window did not produce a render node")
        renderer = Gsk.Renderer.new_for_surface(surface)
        bounds = Graphene.Rect().init(0, 0, width, height)
        texture = renderer.render_texture(node, bounds)
        if not isinstance(texture, Gdk.Texture) or not texture.save_to_png(str(output)):
            raise RuntimeError("Could not save the rendered window")
        renderer.unrealize()
        window.destroy()
        loop.quit()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(750, settle_layout)
    GLib.timeout_add(3000, capture)
    loop.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
