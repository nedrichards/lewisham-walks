from __future__ import annotations

import tempfile
import threading
from dataclasses import replace
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gio, GLib, Gtk

from .. import APP_ID
from ..discovery import (
    THEME_LABELS,
    discoveries_for_theme,
    display_title,
    featured_discoveries,
    source_label,
)
from ..export import plan_to_gpx
from ..models import (
    Coordinate,
    Discovery,
    DiscoveryKind,
    RouteMode,
    RoutePlan,
    RouteRequest,
    RouteStep,
    RouteTheme,
    RouteVisit,
    StopPreference,
)
from ..planner import MAX_BLOSSOM_ROUTE_POINTS, RoutePlanner, StraightLineRoutingProvider
from ..providers.amenities import OverpassAmenityProvider
from ..providers.geocoding import GeocodingError, PostcodesIoGeocoder, normalise_postcode
from ..providers.location import LocationPortalProvider
from ..providers.routing import OpenStreetMapRoutingProvider, RoutingError
from ..store import load_seed_blossom_discoveries, load_seed_discoveries
from . import icons
from .discovery_browser_window import DiscoveryBrowserWindow
from .layout import (
    COMPACT_BREAKPOINT,
    CONTROLS_WIDE_MAX_WIDTH,
    CONTROLS_WIDE_MIN_WIDTH,
    MAP_COMPACT_MIN_HEIGHT,
    MAP_COMPACT_MIN_WIDTH,
    MAP_WIDE_MIN_HEIGHT,
    MAP_WIDE_MIN_WIDTH,
    SIDEBAR_COMPACT_WIDTH_FRACTION,
    SIDEBAR_WIDE_WIDTH_FRACTION,
)
from .map_widget import create_map_widget
from .preferences_window import PreferencesWindow


class MainWindow(Adw.ApplicationWindow):
    DEFAULT_START_POSTCODE = "SE13 5AF"
    COMPACT_BREAKPOINT = COMPACT_BREAKPOINT
    MAP_WIDE_MIN_WIDTH = MAP_WIDE_MIN_WIDTH
    MAP_WIDE_MIN_HEIGHT = MAP_WIDE_MIN_HEIGHT
    MAP_COMPACT_MIN_WIDTH = MAP_COMPACT_MIN_WIDTH
    MAP_COMPACT_MIN_HEIGHT = MAP_COMPACT_MIN_HEIGHT
    MAP_PICK_ICON = icons.MAP_LOCATION
    ROUTE_SOURCE_OPTIONS = [
        "A bit of everything",
        "People & creativity",
        "Places & change",
        "Lewisham's own plaques",
        "Freddy's Blossom Walk",
    ]

    def __init__(self, app) -> None:
        super().__init__(application=app, title="Lewisham Walks", default_width=1120, default_height=720)
        self.settings = Gio.Settings.new(APP_ID)
        self.geocoder = PostcodesIoGeocoder()
        self.location_provider = LocationPortalProvider()
        self.all_discoveries = load_seed_discoveries()
        self.all_blossom_points = load_seed_blossom_discoveries()
        self.discoveries = featured_discoveries(self.all_discoveries)
        self.current_plan: RoutePlan | None = None
        self._generation_id = 0
        self._compact_layout: bool | None = None
        self._picked_start: Coordinate | None = None
        self._picked_end: Coordinate | None = None
        self._pending_map_pick: str | None = None
        self._updating_location_entry = False
        self._generating = False
        self._locating_start = False
        self._location_request_is_automatic = False
        self._initial_location_requested = False
        self._sidebar_requested_open = True
        self._syncing_sidebar_button = False
        self._preferences_window: PreferencesWindow | None = None
        self._stories_window: DiscoveryBrowserWindow | None = None
        self._shortcuts_window: Gtk.ShortcutsWindow | None = None
        self._about_dialog: Adw.AboutDialog | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView.new()
        header = Adw.HeaderBar.new()
        toolbar.add_top_bar(header)
        self.set_content(toolbar)

        title = Adw.WindowTitle.new("Lewisham Walks", "Local stories on foot")
        header.set_title_widget(title)

        self.split_view = Adw.OverlaySplitView.new()
        self.split_view.set_min_sidebar_width(CONTROLS_WIDE_MIN_WIDTH)
        self.split_view.set_max_sidebar_width(CONTROLS_WIDE_MAX_WIDTH)
        self.split_view.set_sidebar_width_fraction(SIDEBAR_WIDE_WIDTH_FRACTION)
        self.split_view.set_pin_sidebar(True)
        self.split_view.set_show_sidebar(True)
        self.split_view.connect("notify::show-sidebar", self._update_sidebar_button)
        self.split_view.connect("notify::collapsed", self._on_split_view_collapsed)

        compact_condition = Adw.BreakpointCondition.parse(f"max-width: {COMPACT_BREAKPOINT - 1}sp")
        self.compact_breakpoint = Adw.Breakpoint.new(compact_condition)
        self.compact_breakpoint.add_setter(self.split_view, "collapsed", True)
        self.compact_breakpoint.add_setter(self.split_view, "pin-sidebar", False)
        self.compact_breakpoint.add_setter(self.split_view, "min-sidebar-width", MAP_COMPACT_MIN_WIDTH)
        self.compact_breakpoint.add_setter(
            self.split_view,
            "sidebar-width-fraction",
            SIDEBAR_COMPACT_WIDTH_FRACTION,
        )
        self.add_breakpoint(self.compact_breakpoint)

        # GNOME presents sidebar visibility as a persistent toggle. Using the
        # single, runtime-provided icon avoids relying on the unavailable
        # sidebar-hide-symbolic counterpart; the pressed state shows whether
        # the planner is currently visible.
        self.sidebar_button = Gtk.ToggleButton.new()
        self.sidebar_button.set_icon_name(icons.SIDEBAR)
        self.sidebar_button.set_tooltip_text("Hide walk planner")
        self.sidebar_button.connect("toggled", self._toggle_sidebar)
        header.pack_start(self.sidebar_button)
        self._update_sidebar_button()

        self.menu_button = Gtk.MenuButton.new()
        self.menu_button.set_icon_name(icons.MENU)
        self.menu_button.set_tooltip_text("Main Menu")
        self.menu_button.set_menu_model(self._create_primary_menu())
        header.pack_end(self.menu_button)

        export_button = Gtk.Button.new_from_icon_name(icons.EXPORT)
        export_button.set_tooltip_text("Export GPX")
        export_button.connect("clicked", self._export_gpx)
        header.pack_end(export_button)

        data_button = Gtk.Button.new_from_icon_name(icons.STORIES)
        data_button.set_tooltip_text("Browse local stories")
        data_button.connect("clicked", self._show_discovery_browser)
        header.pack_end(data_button)

        self.toast_overlay = Adw.ToastOverlay.new()
        self.toast_overlay.set_child(self.split_view)
        toolbar.set_content(self.toast_overlay)

        self.controls_scroller = Gtk.ScrolledWindow.new()
        self.controls_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.controls_scroller.set_hexpand(True)
        self.controls_scroller.set_vexpand(True)
        self.controls_scroller.add_css_class("view")
        self.split_view.set_sidebar(self.controls_scroller)

        self.controls_content = Gtk.Box.new(Gtk.Orientation.VERTICAL, 12)
        self.controls_content.set_margin_top(16)
        self.controls_content.set_margin_bottom(16)
        self.controls_content.set_margin_start(16)
        self.controls_content.set_margin_end(16)
        self.controls_content.add_css_class("view")
        self.controls_scroller.set_child(self.controls_content)

        self.controls_stack = Adw.ViewStack.new()
        self.controls_stack.set_hexpand(True)
        self.controls_stack.set_vexpand(True)
        self.controls_stack.set_enable_transitions(True)
        self.controls_stack.set_transition_duration(220)
        self.controls_switcher = Adw.ViewSwitcher.new()
        self.controls_switcher.set_stack(self.controls_stack)
        self.controls_switcher.set_halign(Gtk.Align.FILL)
        self.controls_switcher.set_hexpand(True)
        self.controls_switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        self.compact_breakpoint.add_setter(
            self.controls_switcher,
            "policy",
            Adw.ViewSwitcherPolicy.NARROW,
        )
        self.controls_content.append(self.controls_switcher)
        self.controls_content.append(self.controls_stack)

        self.planner_section = Gtk.Box.new(Gtk.Orientation.VERTICAL, 12)
        self.results_section = Gtk.Box.new(Gtk.Orientation.VERTICAL, 10)
        self.results_section.set_margin_top(6)
        self.directions_section = self._create_directions_section()

        intro = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
        intro.set_margin_bottom(6)
        intro.add_css_class("discovery-hero")
        intro_title = Gtk.Label.new("Take the interesting way")
        intro_title.set_xalign(0)
        intro_title.set_wrap(True)
        intro_title.add_css_class("title-2")
        intro.append(intro_title)
        intro_copy = Gtk.Label.new("Make a walk from overlooked stories, people and places in Lewisham and nearby.")
        intro_copy.set_xalign(0)
        intro_copy.set_wrap(True)
        intro_copy.add_css_class("dim-label")
        intro.append(intro_copy)
        self.planner_section.append(intro)

        start_group = Adw.PreferencesGroup.new()
        start_group.set_title("Where from?")
        self.planner_section.append(start_group)

        self.postcode_entry = Adw.EntryRow.new()
        self.postcode_entry.set_title("Postcode or map point")
        saved_postcode = self._saved_start_postcode()
        self._has_saved_start_postcode = saved_postcode is not None
        self.postcode_entry.set_text(saved_postcode or self.DEFAULT_START_POSTCODE)
        self.postcode_entry.connect("notify::text", self._on_start_location_text_changed)

        self.current_location_button = Gtk.Button.new_from_icon_name(icons.CURRENT_LOCATION)
        self.current_location_button.add_css_class("flat")
        self.current_location_button.set_tooltip_text("Use current location")
        self.current_location_button.connect("clicked", self._use_current_location_for_start)
        self.postcode_entry.add_suffix(self.current_location_button)

        self.pick_start_button = Gtk.Button.new_from_icon_name(self.MAP_PICK_ICON)
        self.pick_start_button.add_css_class("flat")
        self.pick_start_button.set_tooltip_text("Pick start on map")
        self.pick_start_button.connect("clicked", self._begin_pick_start)
        self.postcode_entry.add_suffix(self.pick_start_button)
        start_group.add(self.postcode_entry)

        route_group = Adw.PreferencesGroup.new()
        route_group.set_title("Make it yours")
        self.planner_section.append(route_group)

        self.end_postcode_entry = Adw.EntryRow.new()
        self.end_postcode_entry.set_title("End Point")
        self.end_postcode_entry.set_text("")
        self.end_postcode_entry.connect("notify::text", self._on_end_location_text_changed)
        self.end_postcode_entry.set_tooltip_text("Optional. Leave blank to return to the start.")

        self.duration_row = Adw.SpinRow.new_with_range(15, 240, 15)
        self.duration_row.set_title("How long?")
        self.duration_row.set_subtitle("minutes")
        self.duration_row.set_value(60)
        route_group.add(self.duration_row)

        self.route_source_model = Gtk.StringList.new(self.ROUTE_SOURCE_OPTIONS)
        self.route_source_row = Adw.ComboRow.new()
        self.route_source_row.set_title("I'm in the mood for")
        self.route_source_row.set_model(self.route_source_model)
        self.route_source_row.connect("notify::selected", self._on_route_source_changed)
        route_group.add(self.route_source_row)

        self.stop_model = Gtk.StringList.new(["Return to start", "Finish at a cafe", "Finish at a pub", "Cafe on the way", "Pub on the way"])
        self.stop_row = Adw.ComboRow.new()
        self.stop_row.set_title("Finish")
        self.stop_row.set_model(self.stop_model)
        self.stop_row.connect("notify::selected", self._update_end_postcode_state)
        route_group.add(self.stop_row)

        end_group = Adw.PreferencesGroup.new()
        end_group.set_title("End somewhere else")
        end_group.set_description("Optional — enter a postcode or pick a point on the map.")
        self.planner_section.append(end_group)

        self.pick_end_button = Gtk.Button.new_from_icon_name(self.MAP_PICK_ICON)
        self.pick_end_button.set_tooltip_text("Pick end on map")
        self.pick_end_button.connect("clicked", self._begin_pick_end)
        self.pick_end_button.add_css_class("flat")
        self.end_postcode_entry.add_suffix(self.pick_end_button)
        end_group.add(self.end_postcode_entry)

        self.plan_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 10)
        self.plan_box.set_margin_top(6)
        self.planner_section.append(self.plan_box)

        self.generate_button = Gtk.Button.new_with_label("Find Me a Walk")
        self.generate_button.add_css_class("suggested-action")
        self.generate_button.add_css_class("pill")
        self.generate_button.connect("clicked", self._generate_walk)
        self.plan_box.append(self.generate_button)

        self.progress_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
        self.progress_box.set_visible(False)
        self.progress_spinner = Gtk.Spinner.new()
        self.progress_box.append(self.progress_spinner)
        self.progress_label = Gtk.Label.new("")
        self.progress_label.set_xalign(0)
        self.progress_label.add_css_class("dim-label")
        self.progress_box.append(self.progress_label)
        self.results_section.append(self.progress_box)

        self.results_summary_card = Gtk.Box.new(Gtk.Orientation.VERTICAL, 8)
        self.results_summary_card.set_margin_top(2)
        self.results_summary_card.add_css_class("card")
        self.results_summary_card.add_css_class("results-summary")
        self.results_section.append(self.results_summary_card)

        self.summary_title = Gtk.Label.new("")
        self.summary_title.set_xalign(0)
        self.summary_title.set_wrap(True)
        self.summary_title.add_css_class("title-3")
        self.results_summary_card.append(self.summary_title)

        self.summary = Gtk.Label.new("")
        self.summary.set_wrap(True)
        self.summary.set_xalign(0)
        self.summary.add_css_class("dim-label")
        self.results_summary_card.append(self.summary)

        self.metrics_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 12)
        self.metrics_box.set_homogeneous(True)
        self.metrics_box.add_css_class("route-metrics")
        self.metrics_box.set_visible(False)
        self.results_summary_card.append(self.metrics_box)
        self.distance_value = self._append_metric("Distance")
        self.duration_value = self._append_metric("Time")
        self.stops_value = self._append_metric("Discoveries")

        self.results_actions = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
        self.results_actions.set_halign(Gtk.Align.START)
        self.results_actions.set_visible(False)
        self.try_another_button = Gtk.Button.new_with_label("Try Another")
        self.try_another_button.add_css_class("pill")
        self.try_another_button.connect("clicked", self._generate_walk)
        self.results_actions.append(self.try_another_button)
        self.directions_button = Gtk.Button.new_with_label("View Directions")
        self.directions_button.add_css_class("pill")
        self.directions_button.connect("clicked", self._show_directions_section)
        self.directions_button.set_visible(False)
        self.results_actions.append(self.directions_button)
        self.results_section.append(self.results_actions)

        self.detail_revealer = Gtk.Revealer.new()
        self.detail_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.detail_revealer.set_reveal_child(False)
        self.results_section.append(self.detail_revealer)

        self.detail_card = Gtk.Box.new(Gtk.Orientation.VERTICAL, 12)
        self.detail_card.set_margin_top(8)
        self.detail_card.set_margin_bottom(8)
        self.detail_card.set_margin_start(2)
        self.detail_card.set_margin_end(2)
        self.detail_card.add_css_class("card")
        self.detail_card.add_css_class("view")
        self.detail_card.add_css_class("route-detail")
        self.detail_revealer.set_child(self.detail_card)

        detail_header = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 12)
        self.detail_card.append(detail_header)

        detail_title_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 4)
        detail_title_box.set_hexpand(True)
        detail_header.append(detail_title_box)

        self.detail_kicker = Gtk.Label.new("")
        self.detail_kicker.set_xalign(0)
        self.detail_kicker.add_css_class("caption-heading")
        detail_title_box.append(self.detail_kicker)

        self.detail_title = Gtk.Label.new("")
        self.detail_title.set_xalign(0)
        self.detail_title.set_wrap(True)
        self.detail_title.add_css_class("title-4")
        detail_title_box.append(self.detail_title)

        self.detail_subtitle = Gtk.Label.new("")
        self.detail_subtitle.set_xalign(0)
        self.detail_subtitle.set_wrap(True)
        self.detail_subtitle.add_css_class("dim-label")
        detail_title_box.append(self.detail_subtitle)

        close_details_button = Gtk.Button.new_from_icon_name(icons.CLOSE)
        close_details_button.add_css_class("flat")
        close_details_button.set_valign(Gtk.Align.START)
        close_details_button.set_tooltip_text("Close details")
        close_details_button.connect("clicked", self._close_details_panel)
        detail_header.append(close_details_button)

        self.detail_description = Gtk.Label.new("")
        self.detail_description.set_xalign(0)
        self.detail_description.set_wrap(True)
        self.detail_description.add_css_class("dim-label")
        self.detail_card.append(self.detail_description)

        self.detail_rows = Gtk.Box.new(Gtk.Orientation.VERTICAL, 8)
        self.detail_card.append(self.detail_rows)

        self.warning_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 6)
        self.warning_box.set_visible(False)
        self.results_section.append(self.warning_box)

        self.results_list_heading = Gtk.Box.new(Gtk.Orientation.VERTICAL, 2)
        self.results_list_heading.add_css_class("results-list-heading")
        self.results_section.append(self.results_list_heading)

        self.results_list_title = Gtk.Label.new("")
        self.results_list_title.set_xalign(0)
        self.results_list_title.add_css_class("heading")
        self.results_list_heading.append(self.results_list_title)

        self.results_list_description = Gtk.Label.new("")
        self.results_list_description.set_xalign(0)
        self.results_list_description.set_wrap(True)
        self.results_list_description.add_css_class("dim-label")
        self.results_list_heading.append(self.results_list_description)

        self.result_list = Gtk.ListBox.new()
        self.result_list.add_css_class("boxed-list")
        self.result_list.connect("row-activated", self._on_result_row_activated)
        self.results_section.append(self.result_list)

        self.map_pane = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.map_pane.set_hexpand(True)
        self.map_pane.set_vexpand(True)
        self.split_view.set_content(self.map_pane)

        self.map_widget = self._create_map()
        self.map_pane.append(self.map_widget)
        planner_page = self.controls_stack.add_titled(self.planner_section, "planner", "Plan")
        planner_page.set_icon_name(icons.PLAN)
        results_page = self.controls_stack.add_titled(self.results_section, "results", "Results")
        results_page.set_icon_name(icons.RESULTS)
        self.directions_page = self.controls_stack.add_titled(
            self.directions_section,
            "directions",
            "Directions",
        )
        self.directions_page.set_icon_name(icons.NEXT)
        self.directions_page.set_visible(False)
        self.controls_stack.set_visible_child_name("planner")
        self._apply_responsive_layout(self.get_default_size()[0], self.get_default_size()[1])
        self._update_end_postcode_state()
        self._render_initial_results()

    def _create_primary_menu(self) -> Gio.Menu:
        menu = Gio.Menu.new()

        settings_section = Gio.Menu.new()
        settings_section.append("Preferences", "app.preferences")
        menu.append_section(None, settings_section)

        help_section = Gio.Menu.new()
        help_section.append("Keyboard Shortcuts", "app.shortcuts")
        help_section.append("About Lewisham Walks", "app.about")
        menu.append_section(None, help_section)

        quit_section = Gio.Menu.new()
        quit_section.append("Quit", "app.quit")
        menu.append_section(None, quit_section)
        return menu

    def _append_metric(self, label_text: str) -> Gtk.Label:
        metric = Gtk.Box.new(Gtk.Orientation.VERTICAL, 1)
        metric.set_halign(Gtk.Align.START)
        label = Gtk.Label.new(label_text)
        label.set_xalign(0)
        label.add_css_class("caption")
        label.add_css_class("dim-label")
        metric.append(label)
        value = Gtk.Label.new("")
        value.set_xalign(0)
        value.add_css_class("route-metric-value")
        metric.append(value)
        self.metrics_box.append(metric)
        return value

    def _create_directions_section(self) -> Gtk.Box:
        section = Gtk.Box.new(Gtk.Orientation.VERTICAL, 14)
        section.set_margin_top(6)

        heading = Gtk.Label.new("Walking Directions")
        heading.set_xalign(0)
        heading.set_wrap(True)
        heading.add_css_class("title-2")
        section.append(heading)

        self.directions_summary = Gtk.Label.new("")
        self.directions_summary.set_xalign(0)
        self.directions_summary.set_wrap(True)
        self.directions_summary.add_css_class("dim-label")
        section.append(self.directions_summary)

        self.directions_groups = Gtk.Box.new(Gtk.Orientation.VERTICAL, 16)
        section.append(self.directions_groups)
        self.direction_leg_groups: list[Adw.PreferencesGroup] = []
        self.direction_rows: list[Adw.ActionRow] = []
        return section

    def _create_map(self):
        map_widget = create_map_widget(self.discoveries, self.all_discoveries)
        if hasattr(map_widget, "set_location_selected_callback"):
            map_widget.set_location_selected_callback(self._on_map_location_selected)
        if hasattr(map_widget, "set_discovery_selected_callback"):
            map_widget.set_discovery_selected_callback(self._show_discovery_details)
        if hasattr(map_widget, "set_visit_selected_callback"):
            map_widget.set_visit_selected_callback(self._show_route_visit_details)
        return map_widget

    def _apply_responsive_layout(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            return

        compact = width < self.COMPACT_BREAKPOINT
        self._apply_layout_mode(compact)

    def _apply_layout_mode(self, compact: bool) -> None:
        if self._compact_layout == compact:
            return
        self._compact_layout = compact
        self.split_view.set_collapsed(compact)
        self.split_view.set_pin_sidebar(not compact)
        self.split_view.set_min_sidebar_width(MAP_COMPACT_MIN_WIDTH if compact else CONTROLS_WIDE_MIN_WIDTH)
        self.split_view.set_sidebar_width_fraction(
            SIDEBAR_COMPACT_WIDTH_FRACTION if compact else SIDEBAR_WIDE_WIDTH_FRACTION
        )
        self.controls_scroller.set_size_request(-1, -1)
        self.controls_scroller.set_vexpand(True)
        self._update_sidebar_button()

    def _on_split_view_collapsed(self, *_args) -> None:
        self._compact_layout = self.split_view.get_collapsed()
        if self._compact_layout:
            self.split_view.set_show_sidebar(False)
        else:
            self.split_view.set_show_sidebar(self._sidebar_requested_open)

    def _toggle_sidebar(self, button) -> None:
        if self._syncing_sidebar_button:
            return
        show_sidebar = not self.split_view.get_show_sidebar() if button is None else button.get_active()
        self._sidebar_requested_open = show_sidebar
        if self.split_view.get_show_sidebar() != show_sidebar:
            self.split_view.set_show_sidebar(show_sidebar)

    def _update_sidebar_button(self, *_args) -> None:
        show_sidebar = self.split_view.get_show_sidebar()
        if self.sidebar_button.get_active() != show_sidebar:
            self._syncing_sidebar_button = True
            try:
                self.sidebar_button.set_active(show_sidebar)
            finally:
                self._syncing_sidebar_button = False
        self.sidebar_button.set_tooltip_text("Hide walk planner" if show_sidebar else "Show walk planner")

    def _render_initial_results(self) -> None:
        while child := self.result_list.get_first_child():
            self.result_list.remove(child)
        self._hide_detail_panel()
        self.results_actions.set_visible(False)
        self.warning_box.set_visible(False)
        self.metrics_box.set_visible(False)
        self._clear_directions()
        self.summary_title.set_text("Explore nearby")
        self.summary.set_text("A Lewisham-first selection to get you started. Make a walk when you are ready.")
        self.results_list_title.set_text("Local stories")
        self.results_list_description.set_text("Select one to read its story and source.")
        for discovery in self.discoveries[:6]:
            self._append_story_row(discovery)

    def _show_preferences(self, _button) -> None:
        if self._preferences_window is None:
            self._preferences_window = PreferencesWindow(self)
            self._preferences_window.connect("close-request", self._clear_preferences_window)
        self._preferences_window.present()

    def _clear_preferences_window(self, *_args) -> bool:
        self._preferences_window = None
        return False

    def _show_shortcuts(self, _action) -> None:
        if self._shortcuts_window is None:
            resource_path = "/com/nedrichards/lewishamwalks/gtk/shortcuts-window.ui"
            try:
                Gio.resources_lookup_data(resource_path, Gio.ResourceLookupFlags.NONE)
            except GLib.Error:
                builder = Gtk.Builder.new_from_file(str(Path(__file__).with_name("shortcuts-window.ui")))
            else:
                builder = Gtk.Builder.new_from_resource(resource_path)
            shortcuts_window = builder.get_object("shortcuts_window")
            if not isinstance(shortcuts_window, Gtk.ShortcutsWindow):
                raise RuntimeError("Could not load the keyboard shortcuts window")
            shortcuts_window.set_transient_for(self)
            shortcuts_window.connect("close-request", self._clear_shortcuts_window)
            self._shortcuts_window = shortcuts_window
        self._shortcuts_window.present()

    def _clear_shortcuts_window(self, *_args) -> bool:
        self._shortcuts_window = None
        return False

    def _show_about(self, _action) -> None:
        if self._about_dialog is None:
            application = self.get_application()
            dialog = Adw.AboutDialog.new()
            dialog.set_application_name("Lewisham Walks")
            # Flatpak may rename the exported development icon, but the icon
            # theme cache inside the app still indexes the canonical name.
            dialog.set_application_icon(APP_ID)
            dialog.set_developer_name("Nick Richards")
            dialog.set_version(getattr(application, "version", "0.1.0"))
            dialog.set_comments("Find overlooked local stories and turn them into walks around Lewisham.")
            dialog.set_website("https://github.com/nedrichards/lewisham-walks")
            dialog.set_issue_url("https://github.com/nedrichards/lewisham-walks/issues")
            dialog.set_copyright("Copyright © 2026 Nick Richards")
            dialog.set_license_type(Gtk.License.GPL_3_0)
            dialog.add_link(
                "Data Sources and Attribution",
                "https://github.com/nedrichards/lewisham-walks/blob/main/DATA_SOURCES.md",
            )
            dialog.connect("closed", self._clear_about_dialog)
            self._about_dialog = dialog
        self._about_dialog.present(self)

    def _clear_about_dialog(self, *_args) -> None:
        self._about_dialog = None

    def _show_discovery_browser(self, _button) -> None:
        if self._stories_window is None:
            self._stories_window = DiscoveryBrowserWindow(
                self,
                [*self.all_discoveries, *self.all_blossom_points],
                self._show_discovery_on_map,
            )
            self._stories_window.connect("close-request", self._clear_stories_window)
        self._stories_window.present()

    def _clear_stories_window(self, *_args) -> bool:
        self._stories_window = None
        return False

    def _show_discovery_on_map(self, discovery: Discovery) -> None:
        if hasattr(self.map_widget, "focus_discovery"):
            self.map_widget.focus_discovery(discovery)
        self.split_view.set_show_sidebar(False)
        self.toast_overlay.add_toast(Adw.Toast.new(f"Showing {display_title(discovery)} on the map."))

    def _generate_walk(self, _button) -> None:
        if self._generating or self._locating_start:
            return
        self._generation_id += 1
        generation_id = self._generation_id
        try:
            stop_preference = [
                StopPreference.NONE,
                StopPreference.CAFE_END,
                StopPreference.PUB_END,
                StopPreference.CAFE_ALONG,
                StopPreference.PUB_ALONG,
            ][self.stop_row.get_selected()]
            start_postcode = None
            if self._picked_start is None:
                start_postcode = normalise_postcode(self.postcode_entry.get_text())
            inputs = {
                "postcode": start_postcode,
                "end_postcode": self.end_postcode_entry.get_text(),
                "start_coordinate": self._picked_start,
                "end_coordinate": self._picked_end,
                "duration_minutes": int(self.duration_row.get_value()),
                "stop_preference": stop_preference,
                "walking_speed_kmh": self.settings.get_double("walking-speed-kmh"),
                "discoveries": list(self._selected_discoveries()),
                "route_mode": self._selected_route_mode(),
                "route_theme": self._selected_route_theme(),
                "seen_story_ids": tuple(self.settings.get_strv("seen-story-ids")),
                "variation_seed": generation_id,
            }
        except (ValueError, IndexError) as error:
            self._show_error(str(error))
            return

        self._set_generating(True, "Looking up postcodes...")
        thread = threading.Thread(
            target=self._generate_walk_worker,
            args=(generation_id, inputs),
            daemon=True,
            name="walk-generator",
        )
        thread.start()

    def _generate_walk_worker(self, generation_id: int, inputs: dict) -> None:
        try:
            geocoder = PostcodesIoGeocoder()
            start = inputs["start_coordinate"] or geocoder.lookup_postcode(inputs["postcode"])
            end = self._lookup_end_location(geocoder, inputs)
            request = RouteRequest(
                start=start,
                end=end,
                duration_minutes=inputs["duration_minutes"],
                stop_preference=inputs["stop_preference"],
                walking_speed_kmh=inputs["walking_speed_kmh"],
                discovery_dwell_minutes=0.0 if inputs["route_mode"] is RouteMode.BLOSSOM_WALK else 3.0,
                max_discoveries=MAX_BLOSSOM_ROUTE_POINTS if inputs["route_mode"] is RouteMode.BLOSSOM_WALK else 12,
                route_mode=inputs["route_mode"],
                route_theme=inputs["route_theme"],
                seen_story_ids=inputs["seen_story_ids"],
                variation_seed=inputs["variation_seed"],
            )
            try:
                planner = RoutePlanner(
                    inputs["discoveries"],
                    routing_provider=OpenStreetMapRoutingProvider(),
                    amenity_provider=OverpassAmenityProvider(),
                )
                plan = planner.plan(request)
            except RoutingError:
                planner = RoutePlanner(
                    inputs["discoveries"],
                    routing_provider=StraightLineRoutingProvider(),
                    amenity_provider=OverpassAmenityProvider(),
                )
                plan = planner.plan(request)
                plan = replace(
                    plan,
                    warnings=[*plan.warnings, "Live walking directions were unavailable, so this route is an approximate guide."],
                )
            GLib.idle_add(
                self._finish_generate_walk,
                generation_id,
                plan,
                None,
                inputs["postcode"],
            )
        except (GeocodingError, RoutingError, ValueError) as error:
            GLib.idle_add(self._finish_generate_walk, generation_id, None, str(error), None)
        except Exception as error:
            GLib.idle_add(
                self._finish_generate_walk,
                generation_id,
                None,
                f"Could not generate route: {error}",
                None,
            )

    def _finish_generate_walk(
        self,
        generation_id: int,
        plan: RoutePlan | None,
        error_message: str | None,
        start_postcode: str | None = None,
    ) -> bool:
        if generation_id != self._generation_id:
            return False
        self._set_generating(False)
        if error_message:
            self._show_error(error_message)
        elif plan is not None:
            if start_postcode is not None:
                self._remember_start_postcode(start_postcode)
            self.current_plan = plan
            self._render_plan(plan)
            self._show_results_section()
        return False

    def _set_generating(self, generating: bool, message: str = "") -> None:
        self._generating = generating
        self.generate_button.set_sensitive(not generating and not self._locating_start)
        self.postcode_entry.set_sensitive(not generating and not self._locating_start)
        self.current_location_button.set_sensitive(not generating and not self._locating_start)
        self.pick_start_button.set_sensitive(not generating and not self._locating_start)
        if generating:
            self.end_postcode_entry.set_sensitive(False)
            self.pick_end_button.set_sensitive(False)
        else:
            self._update_end_postcode_state()
        self.duration_row.set_sensitive(not generating and not self._locating_start)
        self.route_source_row.set_sensitive(not generating and not self._locating_start)
        self.stop_row.set_sensitive(not generating and not self._locating_start)
        self.try_another_button.set_sensitive(not generating and not self._locating_start)
        self.progress_box.set_visible(generating)
        if generating:
            self.directions_page.set_visible(False)
            self.directions_button.set_visible(False)
            self.progress_spinner.start()
            self.progress_label.set_text(message or "Generating walk...")
            self.summary.set_text("Generating walk...")
            self._show_results_section()
        else:
            self.progress_spinner.stop()
            self.progress_label.set_text("")

    def _lookup_end_location(self, geocoder: PostcodesIoGeocoder, inputs: dict) -> Coordinate | None:
        if inputs["stop_preference"] in (StopPreference.CAFE_END, StopPreference.PUB_END):
            return None
        if inputs["end_coordinate"] is not None:
            return inputs["end_coordinate"]
        end_postcode = inputs["end_postcode"].strip()
        if not end_postcode:
            return None
        try:
            return geocoder.lookup_postcode(end_postcode)
        except GeocodingError as error:
            raise GeocodingError(f"Could not find end postcode: {error}") from error

    def _update_end_postcode_state(self, *_args) -> None:
        stop_preference = [
            StopPreference.NONE,
            StopPreference.CAFE_END,
            StopPreference.PUB_END,
            StopPreference.CAFE_ALONG,
            StopPreference.PUB_ALONG,
        ][self.stop_row.get_selected()]
        end_is_amenity = stop_preference in (StopPreference.CAFE_END, StopPreference.PUB_END)
        self.end_postcode_entry.set_sensitive(not end_is_amenity)
        if hasattr(self, "pick_end_button"):
            self.pick_end_button.set_sensitive(not end_is_amenity)
        if end_is_amenity:
            self.end_postcode_entry.set_tooltip_text("Cafe/pub ending will choose the final stop.")
            if self._picked_end is not None:
                self._picked_end = None
                self._sync_picked_locations_to_map()
        else:
            self.end_postcode_entry.set_tooltip_text("Optional. Leave blank to return to the start.")

    def _begin_pick_start(self, _button) -> None:
        if self._locating_start:
            return
        self._pending_map_pick = "start"
        self._set_map_discovery_selection_enabled(False)
        if self.split_view.get_collapsed():
            self.split_view.set_show_sidebar(False)
        self.toast_overlay.add_toast(Adw.Toast.new("Click the map to set the start."))

    def _begin_pick_end(self, _button) -> None:
        if self._locating_start:
            return
        self._pending_map_pick = "end"
        self._set_map_discovery_selection_enabled(False)
        if self.split_view.get_collapsed():
            self.split_view.set_show_sidebar(False)
        self.toast_overlay.add_toast(Adw.Toast.new("Click the map to set the end."))

    def _use_current_location_for_start(self, _button) -> None:
        self._request_location_for_start(automatic=False)

    def request_initial_start_location(self) -> bool:
        """Derive a postcode on first use, without replacing a remembered start."""
        if not self._initial_location_requested:
            self._initial_location_requested = True
            if not self._has_saved_start_postcode:
                self._request_location_for_start(automatic=True)
        return False

    def _request_location_for_start(self, *, automatic: bool) -> None:
        self._pending_map_pick = None
        self._location_request_is_automatic = automatic
        if automatic:
            self.current_location_button.set_sensitive(False)
        else:
            self._set_locating_start(True)
        self.location_provider.request_location("", self._finish_current_location_request)

    def _finish_current_location_request(self, coordinate: Coordinate | None, error_message: str | None) -> None:
        GLib.idle_add(self._finish_current_location_request_on_main, coordinate, error_message)

    def _finish_current_location_request_on_main(
        self,
        coordinate: Coordinate | None,
        error_message: str | None,
    ) -> bool:
        automatic = self._location_request_is_automatic
        self._location_request_is_automatic = False
        if error_message is not None:
            if automatic:
                self.current_location_button.set_sensitive(not self._generating)
            else:
                self._set_locating_start(False)
                self._show_error(error_message)
            return False
        if coordinate is None:
            if automatic:
                self.current_location_button.set_sensitive(not self._generating)
            else:
                self._set_locating_start(False)
                self._show_error("The location portal did not return coordinates.")
            return False
        if automatic and (
            self._generating
            or self._picked_start is not None
            or self.postcode_entry.get_text() != self.DEFAULT_START_POSTCODE
        ):
            self.current_location_button.set_sensitive(not self._generating)
            return False
        if not automatic:
            self.progress_label.set_text("Finding nearby postcode...")
        thread = threading.Thread(
            target=self._reverse_location_worker,
            args=(coordinate, automatic),
            daemon=True,
            name="postcode-reverse-geocoder",
        )
        thread.start()
        return False

    def _reverse_location_worker(self, coordinate: Coordinate, automatic: bool) -> None:
        try:
            postcode = PostcodesIoGeocoder().reverse_lookup_postcode(coordinate)
            GLib.idle_add(self._finish_reverse_location, coordinate, postcode, None, automatic)
        except (GeocodingError, ValueError) as error:
            GLib.idle_add(self._finish_reverse_location, coordinate, None, str(error), automatic)
        except Exception as error:
            GLib.idle_add(
                self._finish_reverse_location,
                coordinate,
                None,
                f"Could not look up a postcode: {error}",
                automatic,
            )

    def _finish_reverse_location(
        self,
        coordinate: Coordinate,
        postcode: str | None,
        error_message: str | None,
        automatic: bool,
    ) -> bool:
        if automatic:
            self.current_location_button.set_sensitive(not self._generating)
        else:
            self._set_locating_start(False)
        if error_message is not None or postcode is None:
            if not automatic:
                self._show_error(f"{error_message or 'No nearby UK postcode was found.'} Kept the existing start.")
            return False
        if automatic and (
            self._generating
            or self._picked_start is not None
            or self.postcode_entry.get_text() != self.DEFAULT_START_POSTCODE
        ):
            return False

        self._updating_location_entry = True
        try:
            self._picked_start = coordinate
            self.postcode_entry.set_text(postcode)
        finally:
            self._updating_location_entry = False
        self._remember_start_postcode(postcode)
        self._sync_picked_locations_to_map()
        if self.split_view.get_collapsed() and not automatic:
            self._show_planner_section()
        self.toast_overlay.add_toast(
            Adw.Toast.new(f"Start set to {postcode} from current location.")
        )
        return False

    def _saved_start_postcode(self) -> str | None:
        try:
            saved = self.settings.get_string("last-start-postcode")
            return normalise_postcode(saved) if saved else None
        except (ValueError, GLib.Error):
            return None

    def _remember_start_postcode(self, postcode: str) -> None:
        normalised = normalise_postcode(postcode)
        self.settings.set_string("last-start-postcode", normalised)
        self._has_saved_start_postcode = True

    def _set_locating_start(self, locating: bool) -> None:
        self._locating_start = locating
        self.generate_button.set_sensitive(not locating and not self._generating)
        self.postcode_entry.set_sensitive(not locating and not self._generating)
        self.current_location_button.set_sensitive(not locating and not self._generating)
        self.pick_start_button.set_sensitive(not locating and not self._generating)
        self.duration_row.set_sensitive(not locating and not self._generating)
        self.route_source_row.set_sensitive(not locating and not self._generating)
        self.stop_row.set_sensitive(not locating and not self._generating)
        if locating:
            self.end_postcode_entry.set_sensitive(False)
            self.pick_end_button.set_sensitive(False)
            self.progress_spinner.start()
            self.progress_label.set_text("Waiting for current location...")
            self.summary.set_text("Waiting for current location...")
            self._show_results_section()
        elif not self._generating:
            self.progress_spinner.stop()
            self.progress_label.set_text("")
            self._update_end_postcode_state()

    def _on_map_location_selected(self, coordinate: Coordinate) -> None:
        if self._pending_map_pick is None:
            self.toast_overlay.add_toast(Adw.Toast.new("Choose Pick Start or Pick End, then click the map."))
            return

        target = self._pending_map_pick
        self._pending_map_pick = None
        self._set_map_discovery_selection_enabled(True)
        self._updating_location_entry = True
        try:
            label = f"Map point {coordinate.lat:.5f}, {coordinate.lon:.5f}"
            if target == "start":
                self._picked_start = coordinate
                self.postcode_entry.set_text(label)
                self.toast_overlay.add_toast(Adw.Toast.new("Start set from map."))
            else:
                self._picked_end = coordinate
                self.end_postcode_entry.set_text(label)
                self.toast_overlay.add_toast(Adw.Toast.new("End set from map."))
        finally:
            self._updating_location_entry = False
        self._sync_picked_locations_to_map()
        if self.split_view.get_collapsed():
            self._show_planner_section()

    def _on_start_location_text_changed(self, *_args) -> None:
        if self._updating_location_entry:
            return
        if self._picked_start is not None:
            self._picked_start = None
            self._sync_picked_locations_to_map()

    def _on_end_location_text_changed(self, *_args) -> None:
        if self._updating_location_entry:
            return
        if self._picked_end is not None:
            self._picked_end = None
            self._sync_picked_locations_to_map()

    def _sync_picked_locations_to_map(self) -> None:
        if hasattr(self, "map_widget") and hasattr(self.map_widget, "set_picked_locations"):
            self.map_widget.set_picked_locations(self._picked_start, self._picked_end)

    def _set_map_discovery_selection_enabled(self, enabled: bool) -> None:
        if hasattr(self, "map_widget") and hasattr(self.map_widget, "set_discovery_selection_enabled"):
            self.map_widget.set_discovery_selection_enabled(enabled)

    def _render_plan(self, plan: RoutePlan) -> None:
        while child := self.result_list.get_first_child():
            self.result_list.remove(child)
        self._hide_detail_panel()
        self.results_actions.set_visible(True)
        while child := self.warning_box.get_first_child():
            self.warning_box.remove(child)
        stop_label = "blossom stops" if plan.request.route_mode is RouteMode.BLOSSOM_WALK else "stories"
        title = "Freddy's Blossom Walk" if plan.request.route_mode is RouteMode.BLOSSOM_WALK else THEME_LABELS.get(
            plan.request.route_theme,
            "Your walk",
        )
        self.summary_title.set_text(title)
        self.summary.set_text("Your route is ready. Select a stop below for its story, or use the map for the big picture.")
        self.distance_value.set_text(self._format_distance(plan.distance_m))
        self.duration_value.set_text(self._format_duration(plan.total_seconds))
        self.stops_value.set_text(str(len(plan.discoveries)))
        self.metrics_box.set_visible(True)
        self.results_list_title.set_text("Stops")
        self.results_list_description.set_text(f"{len(plan.discoveries)} {stop_label}. Select one for more detail.")
        for warning in plan.warnings:
            warning_label = Gtk.Label.new(warning)
            warning_label.set_xalign(0)
            warning_label.set_wrap(True)
            warning_label.add_css_class("route-warning")
            self.warning_box.append(warning_label)
        self.warning_box.set_visible(bool(plan.warnings))

        for index, visit in enumerate(plan.visits, start=1):
            self._append_visit_row(index, visit, plan)
        self._render_directions(plan)
        self._render_map(plan)

    def _clear_directions(self) -> None:
        while child := self.directions_groups.get_first_child():
            self.directions_groups.remove(child)
        self.direction_leg_groups.clear()
        self.direction_rows.clear()
        self.directions_summary.set_text("")
        self.directions_summary.remove_css_class("route-warning")
        self.directions_page.set_visible(False)
        self.directions_button.set_visible(False)

    def _render_directions(self, plan: RoutePlan) -> None:
        self._clear_directions()
        if not plan.steps:
            return

        approximate = any("approximate guide" in warning.casefold() for warning in plan.warnings)
        if approximate:
            self.directions_summary.set_text(
                "Live walking directions were unavailable. These steps connect the stops directly and do not follow roads."
            )
            self.directions_summary.add_css_class("route-warning")
        else:
            self.directions_summary.set_text(
                "Follow the route between each stop. Check crossings and local conditions as you walk."
            )

        steps_by_leg: dict[int, list[RouteStep]] = {}
        for step in plan.steps:
            steps_by_leg.setdefault(step.leg_index, []).append(step)

        direction_number = 1
        for leg_index, steps in sorted(steps_by_leg.items()):
            group = Adw.PreferencesGroup.new()
            destination = plan.visits[leg_index] if leg_index < len(plan.visits) else None
            group.set_title(f"To {self._visit_title(destination, plan)}" if destination is not None else "Continue")
            leg_distance = sum(step.distance_m for step in steps)
            leg_duration = sum(step.duration_s for step in steps)
            group.set_description(f"{self._format_distance(leg_distance)} · {self._format_duration(leg_duration)}")
            self.directions_groups.append(group)
            self.direction_leg_groups.append(group)

            for step in steps:
                row = Adw.ActionRow.new()
                row.set_use_markup(False)
                row.set_title(step.instruction)
                details = []
                if step.distance_m > 0:
                    details.append(self._format_distance(step.distance_m))
                if step.duration_s > 0:
                    details.append(self._format_duration(step.duration_s))
                if details:
                    row.set_subtitle(" · ".join(details))
                row.set_activatable(False)
                row.set_selectable(False)
                badge = Gtk.Label.new(str(direction_number))
                badge.add_css_class("route-badge")
                badge.set_valign(Gtk.Align.CENTER)
                row.add_prefix(badge)
                group.add(row)
                self.direction_rows.append(row)
                direction_number += 1

        self.directions_page.set_visible(True)
        self.directions_button.set_visible(True)

    def _show_directions_section(self, _button) -> None:
        if self.directions_page.get_visible():
            self._show_controls_page("directions")

    def _show_discovery_details(self, discovery: Discovery) -> None:
        self._show_detail_panel(
            kicker=source_label(discovery),
            title=display_title(discovery),
            subtitle=discovery.address or discovery.coordinate_label,
            description=discovery.description or "There is no fuller description in the source yet.",
        )
        if discovery.source_url:
            self._add_detail_link_row("Open Source", discovery.source_url)
        elif discovery.source_name == "Open Plaques" and discovery.external_id:
            self._add_detail_link_row("Open Plaques", f"https://openplaques.org/plaques/{discovery.external_id}")
        if discovery.image_url:
            self._add_detail_link_row("Image", discovery.image_url)
        self._add_seen_button(discovery.id)

    def _show_route_visit_details(self, visit: RouteVisit) -> None:
        self._show_detail_panel(
            kicker=f"{visit.kind.replace('_', ' ').title()} stop",
            title=visit.title,
            subtitle=visit.address or visit.coordinate_label,
            description=self._route_visit_description(visit),
        )

    def _route_visit_description(self, visit: RouteVisit) -> str:
        if visit.kind == "start":
            return "Starting point for the current walk."
        if visit.kind == "end":
            return "Final point for the current walk."
        if visit.kind == "cafe":
            return "Cafe stop selected for this walk."
        if visit.kind == "pub":
            return "Pub stop selected for this walk."
        return visit.description or visit.title

    def _show_detail_panel(self, kicker: str, title: str, subtitle: str, description: str) -> None:
        while child := self.detail_rows.get_first_child():
            self.detail_rows.remove(child)
        self.detail_kicker.set_text(kicker)
        self.detail_title.set_text(title)
        self.detail_subtitle.set_text(subtitle)
        self.detail_description.set_text(description)
        self.detail_revealer.set_reveal_child(True)
        self._show_results_section()
        vadjustment = self.controls_scroller.get_vadjustment()
        if vadjustment is not None:
            vadjustment.set_value(0.0)

    def _hide_detail_panel(self) -> None:
        while child := self.detail_rows.get_first_child():
            self.detail_rows.remove(child)
        self.detail_revealer.set_reveal_child(False)
        self.detail_kicker.set_text("")
        self.detail_title.set_text("")
        self.detail_subtitle.set_text("")
        self.detail_description.set_text("")

    def _close_details_panel(self, _button) -> None:
        self._hide_detail_panel()

    def _add_detail_link_row(self, title: str, uri: str) -> None:
        button = Gtk.Button.new()
        button.set_halign(Gtk.Align.START)
        button.add_css_class("pill")
        content = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 6)
        content.append(Gtk.Image.new_from_icon_name(icons.EXTERNAL_LINK))
        content.append(Gtk.Label.new(title))
        button.set_child(content)
        button.connect("clicked", lambda _button, link=uri: Gtk.show_uri(self, link, 0))
        self.detail_rows.append(button)

    def _add_seen_button(self, story_id: str) -> None:
        seen = set(self.settings.get_strv("seen-story-ids"))
        button = Gtk.Button.new_with_label("Mark as New Again" if story_id in seen else "Mark as Discovered")
        button.set_halign(Gtk.Align.START)
        button.add_css_class("pill")
        button.connect("clicked", self._toggle_story_seen, story_id, button)
        self.detail_rows.append(button)

    def _toggle_story_seen(self, _button, story_id: str, button: Gtk.Button) -> None:
        seen = set(self.settings.get_strv("seen-story-ids"))
        if story_id in seen:
            seen.remove(story_id)
            button.set_label("Mark as Discovered")
            message = "This story can appear in new walks again."
        else:
            seen.add(story_id)
            button.set_label("Mark as New Again")
            message = "Marked as discovered. New walks will favour other stories."
        self.settings.set_strv("seen-story-ids", sorted(seen))
        self.toast_overlay.add_toast(Adw.Toast.new(message))

    def _append_story_row(self, discovery: Discovery) -> None:
        row = Adw.ActionRow.new()
        row.discovery = discovery
        row.set_use_markup(False)
        row.set_title(display_title(discovery))
        row.set_subtitle(source_label(discovery))
        row.set_subtitle_lines(1)
        row.set_title_lines(2)
        row.set_activatable(True)
        arrow = Gtk.Image.new_from_icon_name(icons.NEXT)
        arrow.add_css_class("dim-label")
        row.add_suffix(arrow)
        self.result_list.append(row)

    def _append_visit_row(self, index: int, visit: RouteVisit, plan: RoutePlan) -> None:
        row = Adw.ActionRow.new()
        row.visit = visit
        row.set_use_markup(False)
        discovery = next((item for item in plan.discoveries if item.id == visit.source_id), None)
        row.set_title(self._visit_title(visit, plan))
        row.set_title_lines(2)
        row.set_subtitle(self._visit_subtitle(visit, discovery, plan))
        row.set_subtitle_lines(2)
        row.set_activatable(True)
        row.add_css_class("route-stop-row")
        badge = Gtk.Label.new(str(index) if visit.kind not in {"end", "cafe", "pub"} else visit.kind[:1].upper())
        badge.add_css_class("route-badge")
        badge.set_valign(Gtk.Align.CENTER)
        row.add_prefix(badge)
        arrow = Gtk.Image.new_from_icon_name(icons.NEXT)
        arrow.add_css_class("dim-label")
        row.add_suffix(arrow)
        if discovery is not None:
            row.discovery = discovery
        self.result_list.append(row)

    def _visit_title(self, visit: RouteVisit, plan: RoutePlan) -> str:
        discovery = next((item for item in plan.discoveries if item.id == visit.source_id), None)
        return display_title(discovery) if discovery is not None else visit.title

    def _on_result_row_activated(self, _list_box, row) -> None:
        if hasattr(row, "discovery"):
            self._show_discovery_details(row.discovery)
        elif hasattr(row, "visit"):
            self._show_route_visit_details(row.visit)

    def _render_map(self, plan: RoutePlan) -> None:
        if hasattr(self.map_widget, "set_plan"):
            self.map_widget.set_plan(plan)

    def _on_route_source_changed(self, *_args) -> None:
        selected = list(self._selected_discoveries())
        self.discoveries = selected if self._selected_route_mode() is RouteMode.BLOSSOM_WALK else featured_discoveries(selected, limit=32)
        self.current_plan = None
        if hasattr(self.map_widget, "set_discoveries"):
            self.map_widget.set_discoveries(self.discoveries, selected)
        self._render_initial_results()
        self._show_planner_section()

    def _selected_discoveries(self):
        route_source = self._selected_route_source()
        route_mode = route_source["mode"]
        blossom_route_points = [
            point for point in self.all_blossom_points
            if point.kind is DiscoveryKind.BLOSSOM and point.collection == "freddys-blossom-walk"
        ]
        if route_mode is RouteMode.BLOSSOM_WALK:
            return blossom_route_points
        return discoveries_for_theme(self.all_discoveries, route_source["theme"])

    def _selected_route_mode(self) -> RouteMode:
        return self._selected_route_source()["mode"]

    def _selected_route_theme(self) -> RouteTheme:
        return self._selected_route_source()["theme"]

    def _selected_route_source(self) -> dict[str, RouteMode | RouteTheme]:
        return [
            {"mode": RouteMode.DISCOVERIES, "theme": RouteTheme.SURPRISE},
            {"mode": RouteMode.DISCOVERIES, "theme": RouteTheme.PEOPLE},
            {"mode": RouteMode.DISCOVERIES, "theme": RouteTheme.PLACES},
            {"mode": RouteMode.DISCOVERIES, "theme": RouteTheme.LEWISHAM},
            {"mode": RouteMode.BLOSSOM_WALK, "theme": RouteTheme.SURPRISE},
        ][self.route_source_row.get_selected()]

    def _visit_subtitle(self, visit: RouteVisit, discovery: Discovery | None, plan: RoutePlan) -> str:
        if discovery is not None:
            if discovery.kind is DiscoveryKind.BLOSSOM:
                details = [source_label(discovery), "Walk past"]
                if visit.address:
                    details.insert(0, visit.address)
                return " · ".join(details)
            dwell = self._format_duration(plan.request.discovery_dwell_minutes * 60)
            details = [source_label(discovery), f"{dwell} stop"]
            if visit.address:
                details.insert(0, visit.address)
            return " · ".join(details)
        if visit.kind == "blossom":
            return f"{visit.address} · Walk past" if visit.address else "Walk past"
        if visit.kind in ("cafe", "pub"):
            return visit.address or f"{visit.kind.title()} stop"
        if visit.kind == "end":
            return "End of walk"
        return visit.address or "Route stop"

    def _format_distance(self, metres: float) -> str:
        if metres >= 1000:
            return f"{metres / 1000:.1f} km"
        return f"{metres:.0f} m"

    def _format_duration(self, seconds: float) -> str:
        minutes = max(1, round(seconds / 60))
        if minutes < 60:
            return f"{minutes} min"
        hours, remainder = divmod(minutes, 60)
        if remainder == 0:
            return f"{hours} hr"
        return f"{hours} hr {remainder} min"

    def _export_gpx(self, _button) -> None:
        if self.current_plan is None:
            self._show_error("Generate a walk before exporting GPX.")
            return
        chooser = Gtk.FileDialog.new()
        chooser.set_initial_name("lewisham-discovery-walk.gpx")
        chooser.save(self, None, self._finish_export_gpx)

    def _finish_export_gpx(self, dialog, result) -> None:
        if self.current_plan is None:
            return
        try:
            file = dialog.save_finish(result)
            if file is None:
                return
            gpx = plan_to_gpx(self.current_plan)
            path = file.get_path()
            if path is None:
                tmp = Path(tempfile.gettempdir()) / "lewisham-discovery-walk.gpx"
                tmp.write_text(gpx, encoding="utf-8")
            else:
                Path(path).write_text(gpx, encoding="utf-8")
            self.toast_overlay.add_toast(Adw.Toast.new("GPX exported"))
        except GLib.Error:
            return
        except Exception as error:
            self._show_error(f"Could not export GPX: {error}")

    def _show_error(self, message: str) -> None:
        self.summary.set_text(message)
        self.toast_overlay.add_toast(Adw.Toast.new(message))
        self._show_results_section()

    def _show_results_section(self) -> None:
        self._show_controls_page("results")

    def _show_planner_section(self) -> None:
        self._show_controls_page("planner")

    def _show_controls_page(self, name: str) -> None:
        self.controls_stack.set_visible_child_name(name)
        self.split_view.set_show_sidebar(True)
        adjustment = self.controls_scroller.get_vadjustment()
        if adjustment is not None:
            adjustment.set_value(adjustment.get_lower())
