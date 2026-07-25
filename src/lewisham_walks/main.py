from __future__ import annotations

import sys

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gdk, Gio, Gtk

from . import APP_ID
from .ui.main_window import MainWindow


class LewishamWalksApp(Adw.Application):
    def __init__(self, version: str) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.version = version
        self._main_window: MainWindow | None = None

    def do_activate(self) -> None:
        self._load_styles()
        if self._main_window is None:
            self._main_window = MainWindow(self)
            self._main_window.connect("destroy", self._on_main_window_destroyed)
        self._main_window.present()

    def _on_main_window_destroyed(self, window) -> None:
        if self._main_window is window:
            self._main_window = None

    def _load_styles(self) -> None:
        if getattr(self, "_styles_loaded", False):
            return
        provider = Gtk.CssProvider.new()
        provider.load_from_string(
            """
            .discovery-hero { padding: 8px 4px 10px 4px; }
            .map-pin { background: #613583; color: white; min-width: 12px; min-height: 12px; padding: 3px; box-shadow: 0 1px 3px alpha(black, .35); }
            .map-pin.local { background: #813d5c; }
            .route-marker { background: #1c71d8; color: white; font-weight: bold; box-shadow: 0 1px 4px alpha(black, .4); }
            .route-badge { background: alpha(@accent_bg_color, .14); color: @accent_color; border-radius: 999px; min-width: 28px; min-height: 28px; font-weight: bold; }
            """
        )
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._styles_loaded = True


def main(version: str = "0.1.0") -> int:
    app = LewishamWalksApp(version)
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
