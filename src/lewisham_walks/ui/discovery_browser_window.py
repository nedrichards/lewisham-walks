from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gtk

from ..discovery import display_title, source_label, story_preview
from ..models import Discovery
from . import icons


class DiscoveryBrowserWindow(Adw.Window):
    COMPACT_BREAKPOINT = 880
    SIDEBAR_MIN_WIDTH = 280
    SIDEBAR_MAX_WIDTH = 380

    def __init__(self, parent, discoveries: list[Discovery]) -> None:
        super().__init__(transient_for=parent, modal=False, title="Local Stories", default_width=900, default_height=620)
        self._all_discoveries = sorted(discoveries, key=lambda discovery: (discovery.curation_status != "in_scope", display_title(discovery).lower()))
        self._visible_discoveries = self._all_discoveries
        self._compact_layout: bool | None = None
        self._build_ui()
        self._populate_rows()
        if self._visible_discoveries:
            self._show_discovery(self._visible_discoveries[0])

    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView.new()
        header = Adw.HeaderBar.new()
        header.set_title_widget(Adw.WindowTitle.new("Local Stories", "Open data from around Lewisham"))
        toolbar.add_top_bar(header)
        self.set_content(toolbar)

        self.search_entry = Gtk.SearchEntry.new()
        self.search_entry.set_placeholder_text("Search people, places or neighbourhoods")
        self.search_entry.connect("search-changed", self._on_search_changed)
        header.pack_start(self.search_entry)

        self.root = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        self.root.connect("notify::width", self._on_root_size_changed)
        toolbar.set_content(self.root)

        left = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.left = left
        self.root.set_start_child(left)

        self.summary_label = Gtk.Label.new("")
        self.summary_label.set_xalign(0)
        self.summary_label.set_margin_top(12)
        self.summary_label.set_margin_bottom(12)
        self.summary_label.set_margin_start(12)
        self.summary_label.set_margin_end(12)
        self.summary_label.add_css_class("dim-label")
        left.append(self.summary_label)

        self.list_box = Gtk.ListBox.new()
        self.list_box.add_css_class("boxed-list")
        self.list_box.connect("row-selected", self._on_row_selected)
        list_scroller = Gtk.ScrolledWindow.new()
        list_scroller.set_child(self.list_box)
        list_scroller.set_vexpand(True)
        left.append(list_scroller)

        self.details_scroller = Gtk.ScrolledWindow.new()
        self.details_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.root.set_end_child(self.details_scroller)
        self._apply_responsive_layout(900)

    def _on_root_size_changed(self, widget, _pspec) -> None:
        self._apply_responsive_layout(widget.get_width())

    def _apply_responsive_layout(self, width: int) -> None:
        if width <= 0:
            return

        compact = width < self.COMPACT_BREAKPOINT
        if self._compact_layout != compact:
            self._compact_layout = compact
            self.root.set_orientation(Gtk.Orientation.VERTICAL if compact else Gtk.Orientation.HORIZONTAL)
            self.root.set_resize_start_child(False)
            self.root.set_resize_end_child(True)
            self.root.set_shrink_start_child(True)
            self.root.set_shrink_end_child(True)

        if compact:
            self.left.set_size_request(-1, 220)
        else:
            sidebar_width = max(self.SIDEBAR_MIN_WIDTH, min(int(width * 0.36), self.SIDEBAR_MAX_WIDTH))
            self.left.set_size_request(sidebar_width, -1)

    def _on_search_changed(self, entry) -> None:
        query = entry.get_text().strip().lower()
        if not query:
            self._visible_discoveries = self._all_discoveries
        else:
            self._visible_discoveries = [
                discovery
                for discovery in self._all_discoveries
                if query in discovery.title.lower()
                or query in discovery.description.lower()
                or query in discovery.external_id.lower()
                or query in discovery.curation_status.lower()
                or query in discovery.borough.lower()
                or query in discovery.collection.lower()
                or query in discovery.kind.value
            ]
        self._populate_rows()

    def _populate_rows(self) -> None:
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)

        in_scope = sum(1 for discovery in self._all_discoveries if discovery.curation_status == "in_scope")
        self.summary_label.set_text(f"{len(self._visible_discoveries)} stories · {in_scope} locally curated")

        for discovery in self._visible_discoveries:
            row = Gtk.ListBoxRow.new()
            row.discovery = discovery
            box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 2)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(10)
            box.set_margin_end(10)

            title = Gtk.Label.new(display_title(discovery))
            title.set_xalign(0)
            title.set_wrap(True)
            title.set_max_width_chars(32)
            title.add_css_class("heading")
            box.append(title)

            meta = Gtk.Label.new(f"{story_preview(discovery, 90)}\n{source_label(discovery)}")
            meta.set_xalign(0)
            meta.set_wrap(True)
            meta.set_max_width_chars(40)
            meta.add_css_class("dim-label")
            box.append(meta)

            row.set_child(box)
            self.list_box.append(row)

    def _on_row_selected(self, _list_box, row) -> None:
        if row is not None:
            self._show_discovery(row.discovery)

    def _show_discovery(self, discovery: Discovery) -> None:
        self.details_group = Adw.PreferencesGroup.new()
        self.details_scroller.set_child(self.details_group)
        self.details_group.set_title(display_title(discovery))
        self.details_group.set_description(discovery.description)
        self._add_detail("Curation Status", discovery.curation_status)
        self._add_detail("Curation Note", discovery.curation_note or "No note yet.")
        self._add_detail("Type", discovery.kind.value.title())
        self._add_detail("Borough", discovery.borough or "Unknown")
        self._add_detail("Collection", discovery.collection.replace("-", " ") or "Independent")
        self._add_detail("Source", discovery.source_name or "Unknown")
        if discovery.external_id:
            self._add_detail("Source ID", discovery.external_id)
        self._add_detail("Coordinates", discovery.coordinate_label)
        self._add_detail("Coordinate Accuracy", "Marked accurate" if discovery.is_accurate else "Needs checking")
        self._add_detail("Address", discovery.address or "No address supplied")
        for name, value in sorted(discovery.attributes.items()):
            self._add_detail(name.replace("_", " ").title(), value)

        if discovery.source_url:
            link = Adw.ActionRow.new()
            link.set_title("Source")
            link.set_subtitle(discovery.source_url)
            button = Gtk.Button.new_from_icon_name(icons.EXTERNAL_LINK)
            button.set_valign(Gtk.Align.CENTER)
            button.connect("clicked", lambda _button: Gtk.show_uri(self, discovery.source_url, 0))
            link.add_suffix(button)
            self.details_group.add(link)

    def _add_detail(self, title: str, value: str) -> None:
        row = Adw.ActionRow.new()
        row.set_title(title)
        row.set_subtitle(value)
        self.details_group.add(row)
