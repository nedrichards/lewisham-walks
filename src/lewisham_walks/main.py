from __future__ import annotations

import sys

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import runtime_app_id
from .ui.main_window import MainWindow


class LewishamWalksApp(Adw.Application):
    def __init__(self, version: str) -> None:
        super().__init__(application_id=runtime_app_id(), flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.version = version
        self._main_window: MainWindow | None = None
        self._create_actions()

    def _create_actions(self) -> None:
        window_actions = {
            "preferences": ("_show_preferences", ["<primary>comma"]),
            "shortcuts": ("_show_shortcuts", ["question", "<primary><shift>slash"]),
            "about": ("_show_about", []),
            "stories": ("_show_discovery_browser", ["<primary>l"]),
            "export": ("_export_gpx", ["<primary>e"]),
            "generate": ("_generate_walk", ["<primary>Return"]),
            "toggle-sidebar": ("_toggle_sidebar", ["F9"]),
        }
        for name, (method_name, accelerators) in window_actions.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", self._activate_window_action, method_name)
            self.add_action(action)
            if accelerators:
                self.set_accels_for_action(f"app.{name}", accelerators)

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_args: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<primary>q"])

    def _activate_window_action(self, _action, _parameter, method_name: str) -> None:
        if self._main_window is None:
            self.activate()
        if self._main_window is not None:
            getattr(self._main_window, method_name)(None)

    def do_activate(self) -> None:
        self._load_styles()
        created = self._main_window is None
        if self._main_window is None:
            self._main_window = MainWindow(self)
            self._main_window.connect("close-request", self._on_main_window_close_requested)
        self._main_window.present()
        if created:
            GLib.idle_add(self._main_window.request_initial_start_location)

    def _on_main_window_close_requested(self, window) -> bool:
        if self._main_window is window:
            self._main_window = None
        return False

    def _load_styles(self) -> None:
        if getattr(self, "_styles_loaded", False):
            return
        provider = Gtk.CssProvider.new()
        provider.load_from_string(
            """
            .discovery-hero { padding: 8px 4px 10px 4px; }
            .map-pin { background: #613583; color: white; min-width: 12px; min-height: 12px; padding: 3px; box-shadow: 0 1px 3px alpha(black, .35); }
            .map-pin.local { background: #813d5c; }
            .map-pin.listed { background: #9a6700; }
            .map-pin.culture { background: #007f7f; }
            .route-marker { background: #1c71d8; color: white; font-weight: bold; box-shadow: 0 1px 4px alpha(black, .4); }
            .results-summary { padding: 14px; }
            .route-metrics { margin-top: 4px; }
            .route-metric-value { font-size: 1.18em; font-weight: 700; }
            .results-list-heading { margin: 8px 4px 2px 4px; }
            .route-stop-row { min-height: 58px; }
            .route-badge { background: alpha(@accent_bg_color, .14); color: @accent_color; border-radius: 999px; min-width: 28px; min-height: 28px; margin: 0 4px 0 2px; font-weight: bold; }
            .route-detail { padding: 14px; }
            .route-warning { background: alpha(@warning_bg_color, .14); color: @warning_color; border-radius: 10px; padding: 10px 12px; }
            .story-facts { border-top: 1px solid alpha(currentColor, .14); padding-top: 14px; }
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
