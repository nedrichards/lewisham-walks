from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gio

from .. import APP_ID


class PreferencesWindow(Adw.PreferencesWindow):
    def __init__(self, parent) -> None:
        super().__init__(transient_for=parent, modal=True, title="Preferences")
        self.settings = Gio.Settings.new(APP_ID)

        page = Adw.PreferencesPage.new()
        self.add(page)

        routing_group = Adw.PreferencesGroup.new()
        routing_group.set_title("Walking")
        routing_group.set_description("Used to estimate how much will fit into a walk.")
        page.add(routing_group)

        speed = Adw.SpinRow.new_with_range(2.0, 7.0, 0.1)
        speed.set_title("Walking Speed")
        speed.set_subtitle("Kilometres per hour")
        speed.set_value(self.settings.get_double("walking-speed-kmh"))
        speed.connect("notify::value", self._on_speed_changed)
        routing_group.add(speed)

    def _on_speed_changed(self, row, _pspec) -> None:
        self.settings.set_double("walking-speed-kmh", row.get_value())
