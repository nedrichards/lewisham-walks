from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gtk

from ..discovery import display_title, source_label
from ..models import Discovery, DiscoveryKind
from . import icons


class DiscoveryBrowserWindow(Adw.Window):
    COMPACT_BREAKPOINT = 700
    SIDEBAR_MIN_WIDTH = 280
    SIDEBAR_MAX_WIDTH = 380
    FILTER_OPTIONS = ("Plaques", "Blossom Walk", "Everything")

    def __init__(
        self,
        parent,
        discoveries: list[Discovery],
        on_show_on_map: Callable[[Discovery], None] | None = None,
    ) -> None:
        super().__init__(
            transient_for=parent,
            modal=False,
            title="Local Stories",
            default_width=960,
            default_height=680,
        )
        self._all_discoveries = sorted(
            discoveries,
            key=lambda discovery: (
                discovery.borough.casefold() != "lewisham",
                discovery.curation_status != "in_scope",
                display_title(discovery).casefold(),
            ),
        )
        self._visible_discoveries = self._all_discoveries
        self._on_show_on_map = on_show_on_map
        self._settings = getattr(parent, "settings", None)
        self._current_discovery: Discovery | None = None
        self._source_uri = ""
        self._image_uri = ""
        self._syncing_sidebar_button = False
        self._build_ui()
        self._apply_filter()

    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView.new()
        header = Adw.HeaderBar.new()
        header.set_show_end_title_buttons(False)
        header.set_title_widget(Adw.WindowTitle.new("Local Stories", "People, places and blossom around Lewisham"))
        toolbar.add_top_bar(header)
        self.set_content(toolbar)

        self.sidebar_button = Gtk.ToggleButton.new()
        self.sidebar_button.set_icon_name(icons.SIDEBAR)
        self.sidebar_button.set_tooltip_text("Hide story list")
        self.sidebar_button.connect("toggled", self._toggle_sidebar)
        header.pack_start(self.sidebar_button)

        self.close_button = Gtk.Button.new_from_icon_name(icons.CLOSE)
        self.close_button.set_tooltip_text("Close Local Stories")
        self.close_button.connect("clicked", self._close_window)
        header.pack_end(self.close_button)

        self.toast_overlay = Adw.ToastOverlay.new()
        toolbar.set_content(self.toast_overlay)

        self.split_view = Adw.OverlaySplitView.new()
        self.split_view.set_min_sidebar_width(self.SIDEBAR_MIN_WIDTH)
        self.split_view.set_max_sidebar_width(self.SIDEBAR_MAX_WIDTH)
        self.split_view.set_sidebar_width_fraction(0.34)
        self.split_view.set_pin_sidebar(True)
        self.split_view.set_show_sidebar(True)
        self.split_view.connect("notify::show-sidebar", self._update_sidebar_button)
        self.split_view.connect("notify::collapsed", self._on_collapsed_changed)
        self.toast_overlay.set_child(self.split_view)

        compact_condition = Adw.BreakpointCondition.parse(f"max-width: {self.COMPACT_BREAKPOINT - 1}sp")
        self.compact_breakpoint = Adw.Breakpoint.new(compact_condition)
        self.compact_breakpoint.add_setter(self.split_view, "collapsed", True)
        self.compact_breakpoint.add_setter(self.split_view, "pin-sidebar", False)
        self.add_breakpoint(self.compact_breakpoint)

        self._build_sidebar()
        self._build_details()
        self._update_sidebar_button()

    def _build_sidebar(self) -> None:
        sidebar = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        sidebar.add_css_class("view")
        self.split_view.set_sidebar(sidebar)

        controls = Gtk.Box.new(Gtk.Orientation.VERTICAL, 8)
        controls.set_margin_top(12)
        controls.set_margin_bottom(10)
        controls.set_margin_start(12)
        controls.set_margin_end(12)
        sidebar.append(controls)

        self.search_entry = Gtk.SearchEntry.new()
        self.search_entry.set_placeholder_text("Search stories and places")
        self.search_entry.connect("search-changed", self._apply_filter)
        controls.append(self.search_entry)

        filter_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
        filter_label = Gtk.Label.new("Show")
        filter_label.set_xalign(0)
        filter_label.add_css_class("dim-label")
        filter_box.append(filter_label)
        self.filter_dropdown = Gtk.DropDown.new_from_strings(self.FILTER_OPTIONS)
        self.filter_dropdown.set_hexpand(True)
        self.filter_dropdown.connect("notify::selected", self._apply_filter)
        filter_box.append(self.filter_dropdown)
        controls.append(filter_box)

        self.summary_label = Gtk.Label.new("")
        self.summary_label.set_xalign(0)
        self.summary_label.add_css_class("dim-label")
        controls.append(self.summary_label)

        self.list_box = Gtk.ListBox.new()
        self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list_box.add_css_class("boxed-list")
        self.list_box.set_margin_bottom(12)
        self.list_box.set_margin_start(12)
        self.list_box.set_margin_end(12)
        self.list_box.connect("row-selected", self._on_row_selected)
        self.list_box.connect("row-activated", self._on_row_activated)
        list_scroller = Gtk.ScrolledWindow.new()
        list_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        list_scroller.set_child(self.list_box)
        list_scroller.set_vexpand(True)
        sidebar.append(list_scroller)

    def _build_details(self) -> None:
        self.details_scroller = Gtk.ScrolledWindow.new()
        self.details_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.details_scroller.add_css_class("view")
        self.split_view.set_content(self.details_scroller)

        clamp = Adw.Clamp.new()
        clamp.set_maximum_size(720)
        clamp.set_tightening_threshold(520)
        self.details_scroller.set_child(clamp)

        self.detail_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 14)
        self.detail_box.set_margin_top(28)
        self.detail_box.set_margin_bottom(32)
        self.detail_box.set_margin_start(24)
        self.detail_box.set_margin_end(24)
        clamp.set_child(self.detail_box)

        self.detail_kicker = Gtk.Label.new("")
        self.detail_kicker.set_xalign(0)
        self.detail_kicker.add_css_class("caption-heading")
        self.detail_box.append(self.detail_kicker)

        self.detail_title = Gtk.Label.new("")
        self.detail_title.set_xalign(0)
        self.detail_title.set_wrap(True)
        self.detail_title.add_css_class("title-1")
        self.detail_box.append(self.detail_title)

        self.detail_subtitle = Gtk.Label.new("")
        self.detail_subtitle.set_xalign(0)
        self.detail_subtitle.set_wrap(True)
        self.detail_subtitle.add_css_class("dim-label")
        self.detail_box.append(self.detail_subtitle)

        self.detail_description = Gtk.Label.new("")
        self.detail_description.set_xalign(0)
        self.detail_description.set_wrap(True)
        self.detail_description.set_selectable(True)
        self.detail_box.append(self.detail_description)

        self.detail_actions = Adw.WrapBox.new()
        self.detail_actions.set_child_spacing(8)
        self.detail_actions.set_line_spacing(8)
        self.detail_actions.set_margin_top(4)
        self.detail_box.append(self.detail_actions)

        self.show_on_map_button = self._action_button(icons.MAP_LOCATION, "Show on Map")
        self.show_on_map_button.add_css_class("suggested-action")
        self.show_on_map_button.connect("clicked", self._show_on_map)
        self.show_on_map_button.set_visible(self._on_show_on_map is not None)
        self.detail_actions.append(self.show_on_map_button)

        self.source_button = self._action_button(icons.EXTERNAL_LINK, "Open Source")
        self.source_button.remove_css_class("pill")
        self.source_button.add_css_class("flat")
        self.source_button.connect("clicked", self._open_source)
        self.detail_actions.append(self.source_button)

        self.image_button = self._action_button(icons.EXTERNAL_LINK, "Open Image")
        self.image_button.remove_css_class("pill")
        self.image_button.add_css_class("flat")
        self.image_button.connect("clicked", self._open_image)
        self.detail_actions.append(self.image_button)

        self.seen_button = Gtk.Button.new_with_label("Mark as Discovered")
        self.seen_button.set_halign(Gtk.Align.START)
        self.seen_button.add_css_class("flat")
        self.seen_button.connect("clicked", self._toggle_seen)
        self.detail_box.append(self.seen_button)

        facts_title = Gtk.Label.new("About This Story")
        facts_title.set_xalign(0)
        facts_title.set_margin_top(8)
        facts_title.add_css_class("heading")
        self.detail_box.append(facts_title)
        facts_card = Gtk.Box.new(Gtk.Orientation.VERTICAL, 12)
        facts_card.add_css_class("story-facts")
        self.detail_box.append(facts_card)
        self.area_value = self._append_fact(facts_card, "Area")
        self.kind_value = self._append_fact(facts_card, "Kind")
        self.source_value = self._append_fact(facts_card, "Data Source")

    def _action_button(self, icon_name: str, label: str) -> Gtk.Button:
        button = Gtk.Button.new()
        button.add_css_class("pill")
        content = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 6)
        content.append(Gtk.Image.new_from_icon_name(icon_name))
        content.append(Gtk.Label.new(label))
        button.set_child(content)
        return button

    def _append_fact(self, container: Gtk.Box, title: str) -> Gtk.Label:
        fact = Gtk.Box.new(Gtk.Orientation.VERTICAL, 2)
        key = Gtk.Label.new(title)
        key.set_xalign(0)
        key.add_css_class("caption-heading")
        fact.append(key)
        value = Gtk.Label.new("")
        value.set_xalign(0)
        value.set_wrap(True)
        value.add_css_class("dim-label")
        fact.append(value)
        container.append(fact)
        return value

    def _apply_filter(self, *_args) -> None:
        query = self.search_entry.get_text().strip().casefold()
        selected_filter = self.filter_dropdown.get_selected()
        self._visible_discoveries = [
            discovery
            for discovery in self._all_discoveries
            if self._matches_filter(discovery, selected_filter) and self._matches_query(discovery, query)
        ]
        self._populate_rows()

    def _matches_filter(self, discovery: Discovery, selected_filter: int) -> bool:
        if selected_filter == 0:
            return discovery.kind is DiscoveryKind.PLAQUE
        if selected_filter == 1:
            return discovery.kind is DiscoveryKind.BLOSSOM
        return True

    def _matches_query(self, discovery: Discovery, query: str) -> bool:
        if not query:
            return True
        searchable = " ".join(
            (
                discovery.title,
                discovery.description,
                discovery.address,
                discovery.borough,
                discovery.collection,
                discovery.source_name,
            )
        ).casefold()
        return query in searchable

    def _populate_rows(self) -> None:
        previous_id = self._current_discovery.id if self._current_discovery is not None else ""
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)

        count = len(self._visible_discoveries)
        self.summary_label.set_text(f"{count} {'story' if count == 1 else 'stories'}")
        selected_row = None
        for discovery in self._visible_discoveries:
            row = Adw.ActionRow.new()
            row.discovery = discovery
            row.set_use_markup(False)
            row.set_title(display_title(discovery))
            row.set_title_lines(2)
            subtitle = source_label(discovery)
            if discovery.kind is DiscoveryKind.BLOSSOM and discovery.route_order is not None:
                subtitle = f"{subtitle} · Point {discovery.route_order}"
            row.set_subtitle(subtitle)
            row.set_subtitle_lines(1)
            row.set_activatable(True)
            arrow = Gtk.Image.new_from_icon_name(icons.NEXT)
            arrow.add_css_class("dim-label")
            row.add_suffix(arrow)
            self.list_box.append(row)
            if discovery.id == previous_id:
                selected_row = row

        if selected_row is None:
            selected_row = self.list_box.get_first_child()
        if selected_row is not None:
            self.list_box.select_row(selected_row)
            self._show_discovery(selected_row.discovery)
        else:
            self._show_empty_details()

    def _on_row_selected(self, _list_box, row) -> None:
        if row is not None:
            self._show_discovery(row.discovery)

    def _on_row_activated(self, _list_box, row) -> None:
        self._show_discovery(row.discovery)
        if self.split_view.get_collapsed():
            self.split_view.set_show_sidebar(False)

    def _show_discovery(self, discovery: Discovery) -> None:
        self._current_discovery = discovery
        self.detail_kicker.set_text(source_label(discovery))
        self.detail_title.set_text(display_title(discovery))
        self.detail_subtitle.set_text(discovery.address or discovery.borough or "Location supplied by the source")
        self.detail_description.set_text(
            discovery.description or "There is no fuller description in the source yet."
        )
        self.area_value.set_text(discovery.borough or "Near Lewisham")
        self.kind_value.set_text("Blossom walk" if discovery.kind is DiscoveryKind.BLOSSOM else "Plaque")
        self.source_value.set_text(discovery.source_name or "Local open data")

        self._source_uri = discovery.source_url
        if not self._source_uri and discovery.source_name == "Open Plaques" and discovery.external_id:
            self._source_uri = f"https://openplaques.org/plaques/{discovery.external_id}"
        self.source_button.set_visible(bool(self._source_uri))
        self._image_uri = discovery.image_url
        self.image_button.set_visible(bool(self._image_uri))
        self._update_seen_button()

        adjustment = self.details_scroller.get_vadjustment()
        if adjustment is not None:
            adjustment.set_value(0)

    def _show_empty_details(self) -> None:
        self._current_discovery = None
        self.detail_kicker.set_text("No matches")
        self.detail_title.set_text("Try another search")
        self.detail_subtitle.set_text("")
        self.detail_description.set_text("Search by a person, place or neighbourhood, or change the story type.")
        self.detail_actions.set_visible(False)
        self.seen_button.set_visible(False)

    def _update_seen_button(self) -> None:
        self.detail_actions.set_visible(True)
        self.seen_button.set_visible(self._settings is not None)
        if self._settings is None or self._current_discovery is None:
            return
        seen = set(self._settings.get_strv("seen-story-ids"))
        self.seen_button.set_label(
            "Mark as New Again" if self._current_discovery.id in seen else "Mark as Discovered"
        )

    def _toggle_seen(self, _button) -> None:
        if self._settings is None or self._current_discovery is None:
            return
        seen = set(self._settings.get_strv("seen-story-ids"))
        if self._current_discovery.id in seen:
            seen.remove(self._current_discovery.id)
            message = "This story can appear in new walks again."
        else:
            seen.add(self._current_discovery.id)
            message = "Marked as discovered. New walks will favour other stories."
        self._settings.set_strv("seen-story-ids", sorted(seen))
        self._update_seen_button()
        self.toast_overlay.add_toast(Adw.Toast.new(message))

    def _show_on_map(self, _button) -> None:
        if self._current_discovery is None or self._on_show_on_map is None:
            return
        discovery = self._current_discovery
        self.close()
        self._on_show_on_map(discovery)

    def _open_source(self, _button) -> None:
        if self._source_uri:
            Gtk.show_uri(self, self._source_uri, 0)

    def _open_image(self, _button) -> None:
        if self._image_uri:
            Gtk.show_uri(self, self._image_uri, 0)

    def _toggle_sidebar(self, button) -> None:
        if self._syncing_sidebar_button:
            return
        self.split_view.set_show_sidebar(button.get_active())

    def _update_sidebar_button(self, *_args) -> None:
        show_sidebar = self.split_view.get_show_sidebar()
        if self.sidebar_button.get_active() != show_sidebar:
            self._syncing_sidebar_button = True
            try:
                self.sidebar_button.set_active(show_sidebar)
            finally:
                self._syncing_sidebar_button = False
        self.sidebar_button.set_tooltip_text("Hide story list" if show_sidebar else "Show story list")

    def _on_collapsed_changed(self, *_args) -> None:
        self.split_view.set_show_sidebar(True)
        self._update_sidebar_button()

    def _close_window(self, _button) -> None:
        self.close()
