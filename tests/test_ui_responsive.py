import unittest
from dataclasses import replace
from unittest import mock


def _load_gtk():
    try:
        import gi

        if not hasattr(gi, "require_version"):
            raise ImportError("PyGObject is not available")
        gi.require_version("Adw", "1")
        gi.require_version("Gtk", "4.0")
        from gi.repository import Adw, Gdk, Gio, GLib, Gtk

        initialized = Gtk.init_check()
        if isinstance(initialized, tuple):
            initialized = initialized[0]
        if not initialized:
            raise RuntimeError("GTK could not initialize; run these tests inside the GNOME SDK with a display socket.")
        if Gdk.Display.get_default() is None:
            raise RuntimeError("No display is available; run these tests inside the GNOME SDK with a display socket.")

        return Adw, Gio, GLib, Gtk, None
    # Treat any optional GTK/display failure as a reason to skip this suite.
    except Exception as error:  # noqa: BLE001
        return None, None, None, None, error


Adw, Gio, GLib, Gtk, GTK_IMPORT_ERROR = _load_gtk()

if Adw is not None:
    from lewisham_walks.discovery import display_title, source_label
    from lewisham_walks.main import LewishamWalksApp
    from lewisham_walks.models import (
        Coordinate,
        Discovery,
        DiscoveryKind,
        RoutePlan,
        RouteRequest,
        RouteStep,
        RouteTheme,
        RouteVisit,
    )
    from lewisham_walks.ui.discovery_browser_window import DiscoveryBrowserWindow
    from lewisham_walks.ui.icons import REQUIRED_ICON_NAMES
    from lewisham_walks.ui.layout import (
        COMPACT_BREAKPOINT,
        CONTROLS_WIDE_MIN_WIDTH,
        MAP_WIDE_MIN_WIDTH,
        SIDEBAR_COMPACT_WIDTH_FRACTION,
        SIDEBAR_WIDE_WIDTH_FRACTION,
        WIDE_LAYOUT_GUTTER,
    )
    from lewisham_walks.ui.main_window import MainWindow


class FakeSettings:
    def __init__(self) -> None:
        self._doubles = {"walking-speed-kmh": 4.8}
        self._string_lists = {"seen-story-ids": []}
        self._strings = {}

    def get_string(self, key: str) -> str:
        return self._strings.get(key, "")

    def set_string(self, key: str, value: str) -> None:
        self._strings[key] = value

    def get_double(self, key: str) -> float:
        return self._doubles.get(key, 0.0)

    def set_double(self, key: str, value: float) -> None:
        self._doubles[key] = value

    def get_strv(self, key: str) -> list[str]:
        return list(self._string_lists.get(key, []))

    def set_strv(self, key: str, value: list[str]) -> None:
        self._string_lists[key] = list(value)


@unittest.skipUnless(Adw is not None, f"GTK runtime unavailable: {GTK_IMPORT_ERROR}")
class MainWindowResponsiveTests(unittest.TestCase):
    def setUp(self) -> None:
        Adw.init()
        self._settings_patcher = mock.patch("lewisham_walks.ui.main_window.Gio.Settings.new", return_value=FakeSettings())
        self._settings_patcher.start()
        self.addCleanup(self._settings_patcher.stop)
        self.window = MainWindow(None)
        self.addCleanup(self.window.destroy)

    def _flush(self) -> None:
        context = GLib.MainContext.default()
        for _ in range(8):
            while context.pending():
                context.iteration(False)

    def _size_request(self, widget) -> tuple[int, int]:
        minimum_width, minimum_height = widget.get_size_request()
        return minimum_width, minimum_height

    def test_offline_generation_keeps_a_visible_approximation_warning(self) -> None:
        import requests

        self.window._picked_start = Coordinate(51.462, -0.01)
        with mock.patch("lewisham_walks.ui.main_window.threading.Thread") as thread:
            self.window._generate_walk(None)
        generation_id, inputs = thread.call_args.kwargs["args"]
        with (
            mock.patch("lewisham_walks.providers.routing.requests.Session") as session,
            mock.patch("lewisham_walks.providers.routing.time.sleep"),
        ):
            session.return_value.get.side_effect = requests.ConnectionError("offline")
            self.window._generate_walk_worker(generation_id, inputs)
            self._flush()
        self.assertIsNotNone(self.window.current_plan)
        self.assertFalse(self.window._generating)
        self.assertTrue(self.window.warning_box.get_visible())
        self.assertTrue(any("approximate" in warning for warning in self.window.current_plan.warnings))

    def test_closed_map_disconnects_global_style_notifications(self) -> None:
        from lewisham_walks.ui.map_widget import DiscoveryMapWidget, ShumateDiscoveryMapWidget

        for widget_type in (DiscoveryMapWidget, ShumateDiscoveryMapWidget):
            with self.subTest(widget=widget_type.__name__):
                widget = widget_type([])
                parent = Gtk.Window()
                parent.set_child(widget)
                parent.present()
                self._flush()
                handler = widget._style_handler_id
                self.assertTrue(widget._style_manager.handler_is_connected(handler))
                parent.set_child(None)
                self.assertEqual(0, widget._style_handler_id)
                self.assertFalse(widget._style_manager.handler_is_connected(handler))
                if hasattr(widget, "_discovery_refresh_source_id"):
                    self.assertEqual(0, widget._discovery_refresh_source_id)
                parent.destroy()

    def test_main_window_switches_between_wide_and_compact_layouts(self) -> None:
        self.window.present()
        self.window._apply_responsive_layout(1440, 720)
        self._flush()

        self.assertIs(self.window.toast_overlay.get_child(), self.window.split_view)
        self.assertIs(self.window.split_view.get_sidebar(), self.window.controls_scroller)
        self.assertIs(self.window.split_view.get_content(), self.window.map_pane)
        self.assertFalse(self.window.split_view.get_collapsed())
        self.assertTrue(self.window.split_view.get_pin_sidebar())
        self.assertTrue(self.window.split_view.get_show_sidebar())
        self.assertEqual(self._size_request(self.window.controls_scroller), (-1, -1))
        self.assertTrue(self.window.controls_scroller.get_vexpand())

        self.window._apply_responsive_layout(760, 620)
        self._flush()

        self.assertTrue(self.window.split_view.get_collapsed())
        self.assertFalse(self.window.split_view.get_pin_sidebar())
        self.assertFalse(self.window.split_view.get_show_sidebar())
        self.assertFalse(self.window.sidebar_button.get_active())
        self.assertEqual(self.window.split_view.get_min_sidebar_width(), self.window.MAP_COMPACT_MIN_WIDTH)
        self.assertAlmostEqual(self.window.split_view.get_sidebar_width_fraction(), SIDEBAR_COMPACT_WIDTH_FRACTION)
        self.assertIs(self.window.split_view.get_sidebar(), self.window.controls_scroller)
        self.assertIs(self.window.split_view.get_content(), self.window.map_pane)
        self.assertTrue(self.window.controls_scroller.has_css_class("view"))
        self.assertTrue(self.window.controls_content.has_css_class("view"))
        self.assertEqual(self._size_request(self.window.controls_scroller), (-1, -1))
        self.assertTrue(self.window.controls_scroller.get_vexpand())
        self.assertEqual(self.window.controls_stack.get_visible_child_name(), "planner")
        self.assertIs(self.window.controls_stack.get_visible_child(), self.window.planner_section)
        self.assertIsNotNone(self.window.postcode_entry.get_parent())
        self.assertIsNotNone(self.window.generate_button.get_parent())

    def test_map_picker_temporarily_hides_the_compact_sidebar(self) -> None:
        self.window._apply_responsive_layout(390, 780)
        self.window.split_view.set_show_sidebar(True)

        self.window._begin_pick_start(None)
        self.assertFalse(self.window.split_view.get_show_sidebar())

        self.window._on_map_location_selected(Coordinate(51.462, -0.010))
        self.assertTrue(self.window.split_view.get_show_sidebar())
        self.assertTrue(self.window.postcode_entry.get_text().startswith("Map point "))

    def test_map_opens_on_lewisham_and_filter_changes_preserve_the_viewport(self) -> None:
        map_widget = self.window.map_widget
        if not hasattr(map_widget, "_viewport"):
            self.skipTest("Libshumate viewport is unavailable")

        self.assertAlmostEqual(51.462, map_widget._viewport.get_latitude(), delta=0.02)
        self.assertAlmostEqual(-0.010, map_widget._viewport.get_longitude(), delta=0.02)
        self.assertAlmostEqual(9.0, map_widget._viewport.get_zoom_level())
        map_widget._viewport.set_location(51.475, -0.045)
        map_widget._viewport.set_zoom_level(15.0)

        map_widget.set_discoveries(self.window.discoveries[:4], self.window.all_discoveries)

        self.assertAlmostEqual(51.475, map_widget._viewport.get_latitude())
        self.assertAlmostEqual(-0.045, map_widget._viewport.get_longitude())
        self.assertAlmostEqual(15.0, map_widget._viewport.get_zoom_level())

    def test_completed_map_animation_schedules_a_final_viewport_refresh(self) -> None:
        map_widget = self.window.map_widget
        if not hasattr(map_widget, "_viewport"):
            self.skipTest("Libshumate viewport is unavailable")

        if map_widget._discovery_refresh_source_id:
            GLib.source_remove(map_widget._discovery_refresh_source_id)
            map_widget._discovery_refresh_source_id = 0

        map_widget._on_go_to_completed(map_widget._map)

        self.assertNotEqual(0, map_widget._discovery_refresh_source_id)
        GLib.source_remove(map_widget._discovery_refresh_source_id)
        map_widget._discovery_refresh_source_id = 0

    def test_listed_buildings_are_a_distinct_walk_source(self) -> None:
        self.window.route_source_row.set_selected(5)
        self._flush()

        selected = list(self.window._selected_discoveries())

        self.assertEqual(RouteTheme.LISTED_BUILDINGS, self.window._selected_route_theme())
        self.assertTrue(selected)
        self.assertTrue(all(item.kind is DiscoveryKind.LISTED_BUILDING for item in selected))
        self.assertEqual({"I", "II*"}, {item.attributes["grade"] for item in selected})

    def test_cultural_venues_are_a_distinct_walk_source(self) -> None:
        self.window.route_source_row.set_selected(4)
        self._flush()

        selected = list(self.window._selected_discoveries())

        self.assertEqual(RouteTheme.CULTURE, self.window._selected_route_theme())
        self.assertTrue(selected)
        self.assertTrue(all(item.kind is DiscoveryKind.CULTURAL_VENUE for item in selected))

    def test_current_location_is_shown_as_a_postcode_and_remembered(self) -> None:
        coordinate = Coordinate(51.462, -0.010)

        self.window._finish_reverse_location(coordinate, "SE13 5AF", None, False)

        self.assertEqual("SE13 5AF", self.window.postcode_entry.get_text())
        self.assertEqual(coordinate, self.window._picked_start)
        self.assertEqual("SE13 5AF", self.window.settings.get_string("last-start-postcode"))

    def test_manual_location_keeps_the_planner_open_and_preserves_the_route(self) -> None:
        existing_plan = mock.Mock()
        self.window.current_plan = existing_plan
        self.window.summary.set_text("Existing route summary")
        self.window._show_results_section()
        self.window._show_planner_section()

        with mock.patch.object(self.window.location_provider, "request_location"):
            self.window._request_location_for_start(automatic=False)

        self.assertEqual("planner", self.window.controls_stack.get_visible_child_name())
        self.assertEqual("Existing route summary", self.window.summary.get_text())

        self.window._finish_reverse_location(Coordinate(51.462, -0.010), "SE13 5AF", None, False)

        self.assertEqual("planner", self.window.controls_stack.get_visible_child_name())
        self.assertEqual("Existing route summary", self.window.summary.get_text())
        self.assertIs(existing_plan, self.window.current_plan)

    def test_manual_location_failures_do_not_replace_or_reopen_results(self) -> None:
        existing_plan = mock.Mock()
        self.window.current_plan = existing_plan
        self.window.summary.set_text("Existing route summary")
        self.window._show_planner_section()

        self.window._location_request_is_automatic = False
        self.window._locating_start = True
        self.window._finish_current_location_request_on_main(None, "Location permission denied")
        self.window._finish_reverse_location(
            Coordinate(51.462, -0.010),
            None,
            "Postcode lookup failed",
            False,
        )

        self.assertEqual("planner", self.window.controls_stack.get_visible_child_name())
        self.assertEqual("Existing route summary", self.window.summary.get_text())
        self.assertIs(existing_plan, self.window.current_plan)

    def test_successful_manual_start_postcode_is_remembered(self) -> None:
        plan = mock.Mock()

        with (
            mock.patch.object(self.window, "_render_plan"),
            mock.patch.object(self.window, "_show_results_section"),
        ):
            self.window._finish_generate_walk(self.window._generation_id, plan, None, "SE8 4AG")

        self.assertEqual("SE8 4AG", self.window.settings.get_string("last-start-postcode"))

    def test_map_point_does_not_replace_remembered_postcode(self) -> None:
        self.window.settings.set_string("last-start-postcode", "SE13 5AF")
        self.window._pending_map_pick = "start"

        self.window._on_map_location_selected(Coordinate(51.48, -0.03))

        self.assertEqual("SE13 5AF", self.window.settings.get_string("last-start-postcode"))

    def test_remembered_postcode_is_restored_without_requesting_location(self) -> None:
        self.window.settings.set_string("last-start-postcode", "se8 4ag")
        restored = MainWindow(None)
        self.addCleanup(restored.destroy)

        with mock.patch.object(restored.location_provider, "request_location") as request_location:
            restored.request_initial_start_location()
            restored.request_initial_start_location()

        self.assertEqual("SE8 4AG", restored.postcode_entry.get_text())
        request_location.assert_not_called()

    def test_automatic_location_does_not_replace_an_edited_start(self) -> None:
        self.window.postcode_entry.set_text("SE8 4AG")

        self.window._finish_reverse_location(Coordinate(51.462, -0.010), "SE13 5AF", None, True)

        self.assertEqual("SE8 4AG", self.window.postcode_entry.get_text())
        self.assertIsNone(self.window._picked_start)

    def test_first_run_requests_location_once_and_keeps_default_on_failure(self) -> None:
        with mock.patch.object(self.window.location_provider, "request_location") as request_location:
            self.window.request_initial_start_location()
            self.window.request_initial_start_location()

        request_location.assert_called_once_with("", self.window._finish_current_location_request)
        self.window._finish_current_location_request_on_main(None, "Location unavailable")
        self.assertEqual(self.window.DEFAULT_START_POSTCODE, self.window.postcode_entry.get_text())

    def test_native_breakpoint_enters_compact_mode_on_initial_narrow_allocation(self) -> None:
        self.window.set_default_size(390, 780)
        self.window.present()
        self._flush()

        self.assertIs(self.window.get_current_breakpoint(), self.window.compact_breakpoint)
        self.assertTrue(self.window.split_view.get_collapsed())
        self.assertFalse(self.window.split_view.get_pin_sidebar())
        self.assertFalse(self.window.split_view.get_show_sidebar())
        self.assertEqual(self.window.split_view.get_min_sidebar_width(), self.window.MAP_COMPACT_MIN_WIDTH)

    def test_sidebar_can_be_hidden_and_restored_at_narrow_widths(self) -> None:
        self.window.present()
        self.window._apply_responsive_layout(760, 620)
        self._flush()

        self.assertFalse(self.window.split_view.get_show_sidebar())
        self.assertFalse(self.window.sidebar_button.get_active())
        self.assertEqual(self.window.sidebar_button.get_icon_name(), "sidebar-show-symbolic")

        self.window.sidebar_button.set_active(True)
        self._flush()

        self.assertTrue(self.window.split_view.get_show_sidebar())
        self.assertTrue(self.window.sidebar_button.get_active())
        self.assertEqual(self.window.sidebar_button.get_icon_name(), "sidebar-show-symbolic")

        self.window.sidebar_button.set_active(False)
        self._flush()

        self.assertFalse(self.window.split_view.get_show_sidebar())
        self.assertFalse(self.window.sidebar_button.get_active())

    def test_desktop_sidebar_toggle_creates_a_persistent_map_focus_mode(self) -> None:
        self.window._apply_responsive_layout(1440, 720)
        self.window.sidebar_button.set_active(False)
        self._flush()

        self.assertFalse(self.window.split_view.get_show_sidebar())

        self.window._apply_responsive_layout(760, 720)
        self.window._apply_responsive_layout(1440, 720)
        self._flush()

        self.assertFalse(self.window.split_view.get_show_sidebar())
        self.assertFalse(self.window.sidebar_button.get_active())
        self.assertEqual(self.window.sidebar_button.get_tooltip_text(), "Show walk planner")

    def test_every_application_icon_exists_in_the_runtime_theme(self) -> None:
        icon_theme = Gtk.IconTheme.get_for_display(self.window.get_display())

        for icon_name in REQUIRED_ICON_NAMES:
            with self.subTest(icon_name=icon_name):
                self.assertTrue(icon_theme.has_icon(icon_name))

    def test_plan_and_results_are_full_height_pages_at_every_width(self) -> None:
        self.assertFalse(self.window.results_page.get_visible())
        self.assertFalse(self.window.controls_switcher.get_visible())
        self.assertFalse(self.window.export_button.get_sensitive())
        self.assertFalse(self.window.save_gpx_button.get_visible())
        self.assertFalse(self.window.save_gpx_button.get_sensitive())

        self.window.results_page.set_visible(True)
        self.window.controls_switcher.set_visible(True)
        for width in (1440, 390):
            with self.subTest(width=width):
                self.window._apply_responsive_layout(width, 720)
                self.window._show_results_section()
                self._flush()

                self.assertEqual(self.window.controls_stack.get_visible_child_name(), "results")
                self.assertIs(self.window.controls_stack.get_visible_child(), self.window.results_section)
                self.assertTrue(self.window.split_view.get_show_sidebar())
                self.assertEqual(self._size_request(self.window.controls_scroller), (-1, -1))

                self.window._show_planner_section()
                self._flush()

                self.assertEqual(self.window.controls_stack.get_visible_child_name(), "planner")
                self.assertIs(self.window.controls_stack.get_visible_child(), self.window.planner_section)

    def test_route_results_prioritise_summary_and_stops_over_internal_detail(self) -> None:
        story = Discovery(
            "test-story",
            "A useful local story",
            "A much longer description that belongs in the selected-stop detail rather than every route row.",
            Coordinate(51.462, -0.010),
            address="1 Lewisham Way",
            source_name="Open Plaques",
            source_url="https://example.com/story",
            borough="Lewisham",
            curation_status="in_scope",
        )
        request = RouteRequest(
            start=Coordinate(51.461, -0.011),
            duration_minutes=30,
            route_theme=RouteTheme.PEOPLE,
        )
        visits = [
            RouteVisit(
                kind="plaque",
                title=story.title,
                coordinate=story.coordinate,
                description=story.description,
                address=story.address,
                source_id=story.id,
            ),
            RouteVisit(kind="end", title="Return to start", coordinate=request.start),
        ]
        plan = RoutePlan(
            request=request,
            discoveries=[story],
            amenities=[],
            visits=visits,
            waypoints=[request.start, story.coordinate, request.start],
            geometry=[request.start, story.coordinate, request.start],
            steps=[
                RouteStep("Turn left onto Lewisham Way", 700, 540, leg_index=0),
                RouteStep("Return along Lewisham Way", 500, 360, leg_index=1),
            ],
            distance_m=1200,
            walking_seconds=900,
            dwell_seconds=180,
        )

        self.window._render_plan(plan)

        self.assertTrue(self.window.results_page.get_visible())
        self.assertTrue(self.window.controls_switcher.get_visible())
        self.assertTrue(self.window.export_button.get_sensitive())
        self.assertTrue(self.window.save_gpx_button.get_visible())
        self.assertTrue(self.window.save_gpx_button.get_sensitive())
        self.assertEqual("Save GPX", self.window.save_gpx_button.get_child().get_label())
        self.assertEqual(self.window.summary_title.get_text(), "People & creativity")
        self.assertEqual(self.window.distance_value.get_text(), "1.2 km")
        self.assertEqual(self.window.duration_value.get_text(), "18 min")
        self.assertEqual(self.window.stops_value.get_text(), "1")
        self.assertEqual(self.window.results_list_title.get_text(), "Stops")
        rows = []
        row = self.window.result_list.get_first_child()
        while row is not None:
            rows.append(row)
            row = row.get_next_sibling()
        self.assertEqual(len(rows), len(visits))
        self.assertEqual(rows[0].get_title(), story.title)
        self.assertNotIn(story.description, rows[0].get_subtitle())
        self.assertEqual(rows[1].get_subtitle(), "End of walk")
        self.assertTrue(self.window.directions_page.get_visible())
        self.assertTrue(self.window.directions_button.get_visible())
        self.assertEqual(
            ["To A useful local story", "To Return to start"],
            [group.get_title() for group in self.window.direction_leg_groups],
        )
        self.assertEqual(
            ["Turn left onto Lewisham Way", "Return along Lewisham Way"],
            [row.get_title() for row in self.window.direction_rows],
        )

        self.window._show_directions_section(None)
        self.assertEqual("directions", self.window.controls_stack.get_visible_child_name())

        self.window._show_discovery_details(story)
        detail_children = []
        child = self.window.detail_rows.get_first_child()
        while child is not None:
            detail_children.append(child)
            child = child.get_next_sibling()
        self.assertEqual(len(detail_children), 2)

        plan.warnings.append("Live walking directions were unavailable, so this route is an approximate guide.")
        self.window._render_directions(plan)
        self.assertTrue(self.window.directions_summary.has_css_class("route-warning"))
        self.assertIn("do not follow roads", self.window.directions_summary.get_text())

        plan.discoveries[0] = replace(story, title="Fox & Firkin")
        self.window._render_directions(plan)
        self.assertEqual("To Fox &amp; Firkin", self.window.direction_leg_groups[0].get_title())

    def test_compact_layout_releases_the_desktop_minimum_width(self) -> None:
        for width in (390, 360):
            with self.subTest(width=width):
                self.window._apply_responsive_layout(width, 780)
                self._flush()

                minimum, _natural, _minimum_baseline, _natural_baseline = self.window.measure(
                    Gtk.Orientation.HORIZONTAL,
                    -1,
                )

                self.assertLessEqual(minimum, width)

    def test_wide_layout_can_cross_its_own_compact_breakpoint(self) -> None:
        self.window._apply_responsive_layout(1440, 780)
        self._flush()

        minimum, _natural, _minimum_baseline, _natural_baseline = self.window.measure(
            Gtk.Orientation.HORIZONTAL,
            -1,
        )

        self.assertLess(minimum, COMPACT_BREAKPOINT)

    def test_wide_layout_only_applies_when_controls_and_map_fit(self) -> None:
        self.assertEqual(COMPACT_BREAKPOINT, CONTROLS_WIDE_MIN_WIDTH + MAP_WIDE_MIN_WIDTH + WIDE_LAYOUT_GUTTER)

        self.window._apply_responsive_layout(900, 720)
        self._flush()

        self.assertTrue(self.window.split_view.get_collapsed())

        self.window._apply_responsive_layout(COMPACT_BREAKPOINT - 1, 720)
        self._flush()

        self.assertTrue(self.window.split_view.get_collapsed())

        self.window._apply_responsive_layout(COMPACT_BREAKPOINT, 720)
        self._flush()

        self.assertFalse(self.window.split_view.get_collapsed())
        self.assertGreaterEqual(self.window.split_view.get_min_sidebar_width(), CONTROLS_WIDE_MIN_WIDTH)
        self.assertAlmostEqual(self.window.split_view.get_sidebar_width_fraction(), SIDEBAR_WIDE_WIDTH_FRACTION)

    def test_auxiliary_windows_are_reused(self) -> None:
        with mock.patch("lewisham_walks.ui.main_window.DiscoveryBrowserWindow") as browser_type:
            self.window._show_discovery_browser(None)
            self.window._show_discovery_browser(None)
            browser_type.assert_called_once_with(
                self.window,
                [*self.window.all_discoveries, *self.window.all_blossom_points],
                self.window._show_discovery_on_map,
            )
            self.assertEqual(2, browser_type.return_value.present.call_count)

        with mock.patch("lewisham_walks.ui.main_window.PreferencesDialog") as preferences_type:
            self.window._show_preferences(None)
            self.window._show_preferences(None)
            preferences_type.assert_called_once_with()
            self.assertEqual(
                [mock.call(self.window), mock.call(self.window)],
                preferences_type.return_value.present.call_args_list,
            )

    def test_primary_menu_and_standard_dialogs_use_native_gnome_patterns(self) -> None:
        self.assertEqual(3, self.window.menu_button.get_menu_model().get_n_items())

        self.window._show_shortcuts(None)
        shortcuts_dialog = self.window._shortcuts_dialog
        self.assertIsInstance(shortcuts_dialog, Adw.ShortcutsDialog)
        self.window._show_shortcuts(None)
        self.assertIs(shortcuts_dialog, self.window._shortcuts_dialog)

        self.window._show_preferences(None)
        preferences_dialog = self.window._preferences_dialog
        self.assertIsInstance(preferences_dialog, Adw.PreferencesDialog)

        self.window._show_about(None)
        about_dialog = self.window._about_dialog
        self.assertIsInstance(about_dialog, Adw.AboutDialog)
        self.assertEqual("Lewisham Walks", about_dialog.get_application_name())
        self.assertEqual("com.nedrichards.lewishamwalks", about_dialog.get_application_icon())
        self.assertEqual("Nick Richards", about_dialog.get_developer_name())

        shortcuts_dialog.close()
        preferences_dialog.close()
        about_dialog.close()
        self._flush()
        self.assertIsNone(self.window._shortcuts_dialog)
        self.assertIsNone(self.window._preferences_dialog)
        self.assertIsNone(self.window._about_dialog)

        self.window._show_shortcuts(None)
        self.window._show_preferences(None)
        self.window._show_about(None)
        self.assertIsNot(shortcuts_dialog, self.window._shortcuts_dialog)
        self.assertIsNot(preferences_dialog, self.window._preferences_dialog)
        self.assertIsNot(about_dialog, self.window._about_dialog)
        self.window._shortcuts_dialog.close()
        self.window._preferences_dialog.close()
        self.window._about_dialog.close()

    def test_closed_story_browser_is_released_for_a_fresh_window(self) -> None:
        self.window._show_discovery_browser(None)
        browser = self.window._stories_window
        self.assertIsNotNone(browser)

        browser.close()
        self._flush()

        self.assertIsNone(self.window._stories_window)

    def test_gpx_export_writes_the_selected_gio_file(self) -> None:
        self.window.current_plan = mock.Mock()
        destination = mock.Mock()
        destination.get_basename.return_value = "my-lewisham-walk.gpx"
        destination.get_parent.return_value = mock.Mock()
        dialog = mock.Mock()
        dialog.save_finish.return_value = destination

        with (
            mock.patch("lewisham_walks.ui.main_window.plan_to_gpx", return_value="<gpx />"),
            mock.patch.object(self.window, "_show_export_success") as show_success,
        ):
            self.window._finish_export_gpx(dialog, mock.Mock())

        destination.replace_contents.assert_called_once_with(
            b"<gpx />",
            None,
            False,
            Gio.FileCreateFlags.REPLACE_DESTINATION,
            None,
        )
        show_success.assert_called_once_with(destination)

    def test_gpx_export_adds_a_missing_extension(self) -> None:
        destination = Gio.File.new_for_uri("smb://example.local/walks/lewisham-route")

        result = self.window._ensure_gpx_extension(destination)

        self.assertEqual("smb://example.local/walks/lewisham-route.gpx", result.get_uri())

    def test_story_browser_handoff_focuses_the_map(self) -> None:
        discovery = self.window.all_discoveries[0]
        self.window.split_view.set_show_sidebar(True)

        with mock.patch.object(self.window.map_widget, "focus_discovery") as focus_discovery:
            self.window._show_discovery_on_map(discovery)

        focus_discovery.assert_called_once_with(discovery)
        self.assertFalse(self.window.split_view.get_show_sidebar())
        self.assertTrue(self.window.map_flyout_revealer.get_reveal_child())
        self.assertGreaterEqual(self.window.map_flyout_revealer.get_margin_bottom(), 40)
        self.assertIs(discovery, self.window._map_flyout_discovery)

    def test_map_story_selection_stays_on_the_map_until_full_story_is_requested(self) -> None:
        discovery = self.window.all_discoveries[0]
        self.window.split_view.set_show_sidebar(False)

        self.window._show_map_discovery_flyout(discovery)

        self.assertFalse(self.window.split_view.get_show_sidebar())
        self.assertTrue(self.window.map_flyout_revealer.get_reveal_child())
        self.assertEqual(display_title(discovery), self.window.map_flyout_title.get_text())
        self.assertEqual(source_label(discovery), self.window.map_flyout_kicker.get_text())
        self.assertLessEqual(len(self.window.map_flyout_description.get_text()), 240)

        stories_window = mock.Mock()
        with mock.patch.object(
            self.window,
            "_show_discovery_browser",
            side_effect=lambda _button: setattr(self.window, "_stories_window", stories_window),
        ):
            self.window._open_map_discovery_story(None)

        stories_window.show_discovery.assert_called_once_with(discovery)

        self.window._hide_map_flyout()
        self.assertFalse(self.window.map_flyout_revealer.get_reveal_child())
        self.assertIsNone(self.window._map_flyout_discovery)

    def test_escape_closes_map_flyout_and_returns_focus_to_the_map(self) -> None:
        discovery = self.window.all_discoveries[0]
        self.window._show_map_discovery_flyout(discovery)

        self.assertEqual(Gtk.ShortcutScope.MANAGED, self.window.map_flyout_shortcut_controller.get_scope())
        self.assertEqual("Escape", self.window.map_flyout_escape_shortcut.get_trigger().to_string())
        with mock.patch.object(self.window.map_widget, "grab_focus", return_value=True) as focus_map:
            handled = self.window._dismiss_map_flyout_shortcut()

        self.assertTrue(handled)
        self.assertFalse(self.window.map_flyout_revealer.get_reveal_child())
        focus_map.assert_called_once_with()
        self.assertFalse(self.window._dismiss_map_flyout_shortcut())

    def test_route_map_markers_use_the_same_inline_flyout(self) -> None:
        visit = RouteVisit(
            kind="cafe",
            title="A local cafe",
            coordinate=Coordinate(51.462, -0.010),
            address="Lewisham High Street",
        )

        self.window._show_map_visit_flyout(visit)

        self.assertTrue(self.window.map_flyout_revealer.get_reveal_child())
        self.assertIs(visit, self.window._map_flyout_visit)
        self.assertIsNone(self.window._map_flyout_discovery)
        self.assertEqual("Cafe stop", self.window.map_flyout_kicker.get_text())
        self.assertEqual("A local cafe", self.window.map_flyout_title.get_text())
        self.assertEqual("Cafe stop selected for this walk.", self.window.map_flyout_description.get_text())
        self.assertFalse(self.window.map_flyout_full_story_button.get_visible())

    def test_selectable_map_points_use_the_normal_selection_cursor(self) -> None:
        map_widget = self.window.map_widget
        if not hasattr(map_widget, "_point_marker"):
            self.skipTest("Libshumate map markers are unavailable")

        markers = (
            map_widget._point_marker(self.window.all_discoveries[0]),
            map_widget._label_marker(
                RouteVisit(kind="cafe", title="A cafe", coordinate=Coordinate(51.46, -0.01)),
                "C",
                "A cafe",
            ),
        )

        for marker in markers:
            with self.subTest(marker=marker):
                cursor = marker.get_child().get_cursor()
                self.assertIsNotNone(cursor)
                self.assertEqual("default", cursor.get_name())


@unittest.skipUnless(Adw is not None, f"GTK runtime unavailable: {GTK_IMPORT_ERROR}")
class ApplicationWindowTests(unittest.TestCase):
    def test_application_registers_actions_and_accelerators_once(self) -> None:
        app = LewishamWalksApp("test")
        self.addCleanup(app.quit)
        expected_accelerators = {
            "preferences": "<Control>comma",
            "shortcuts": "question",
            "stories": "<Control>l",
            "export": "<Control>e",
            "generate": "<Control>Return",
            "toggle-sidebar": "F9",
            "quit": "<Control>q",
        }

        for name in (*expected_accelerators, "about"):
            with self.subTest(action=name):
                self.assertIsNotNone(app.lookup_action(name))
        for name, accelerator in expected_accelerators.items():
            with self.subTest(accelerator=name):
                self.assertIn(accelerator, app.get_accels_for_action(f"app.{name}"))

    def test_repeated_activation_reuses_the_primary_window(self) -> None:
        app = LewishamWalksApp("test")
        self.addCleanup(app.quit)

        with (
            mock.patch.object(app, "_load_styles"),
            mock.patch("lewisham_walks.main.MainWindow") as window_type,
            mock.patch("lewisham_walks.main.GLib.idle_add") as idle_add,
        ):
            app.do_activate()
            app.do_activate()

        window_type.assert_called_once_with(app)
        self.assertEqual(2, window_type.return_value.present.call_count)
        idle_add.assert_called_once_with(window_type.return_value.request_initial_start_location)
        self.assertFalse(app.get_flags() & Gio.ApplicationFlags.NON_UNIQUE)


@unittest.skipUnless(Adw is not None, f"GTK runtime unavailable: {GTK_IMPORT_ERROR}")
class PlaqueBrowserResponsiveTests(unittest.TestCase):
    def setUp(self) -> None:
        Adw.init()
        self.parent = Adw.Window()
        self.addCleanup(self.parent.destroy)
        self.window = DiscoveryBrowserWindow(self.parent, [])
        self.addCleanup(self.window.destroy)

    def _flush(self) -> None:
        context = GLib.MainContext.default()
        for _ in range(8):
            while context.pending():
                context.iteration(False)

    def test_browser_uses_an_overlay_list_in_compact_layout(self) -> None:
        self.window.set_default_size(390, 720)
        self.window.present()
        self._flush()

        self.assertIs(self.window.get_current_breakpoint(), self.window.compact_breakpoint)
        self.assertTrue(self.window.split_view.get_collapsed())
        self.assertFalse(self.window.split_view.get_pin_sidebar())
        self.assertTrue(self.window.split_view.get_show_sidebar())

    def test_browser_pins_the_list_beside_details_on_desktop(self) -> None:
        self.window.set_default_size(960, 680)
        self.window.present()
        self._flush()

        self.assertFalse(self.window.split_view.get_collapsed())
        self.assertTrue(self.window.split_view.get_pin_sidebar())
        self.assertTrue(self.window.split_view.get_show_sidebar())

    def test_browser_uses_the_native_close_control(self) -> None:
        close_requests = []
        self.window.connect("close-request", lambda *_args: close_requests.append(True) and False)
        self.window.present()

        self.assertTrue(self.window.header.get_show_end_title_buttons())
        self.window.close()
        self._flush()

        self.assertEqual(close_requests, [True])

    def test_browser_presents_different_discovery_kinds(self) -> None:
        plaque = Discovery(
            "plaque", "A plaque", "A local plaque", Coordinate(51.46, -0.01),
            source_name="Open Plaques", external_id="1", attributes={"colour": "brown"},
        )
        blossom = Discovery(
            "blossom", "A tree", "A blossom tree", Coordinate(51.461, -0.011),
            kind=DiscoveryKind.BLOSSOM, collection="freddys-blossom-walk",
            source_name="Freddy's Blossom Walk", attributes={"species": "Prunus"},
        )
        listed = Discovery(
            "listed", "A listed church", "An exceptional building", Coordinate(51.462, -0.012),
            kind=DiscoveryKind.LISTED_BUILDING, collection="historic-england-listed-buildings",
            source_name="Historic England", borough="Lewisham", attributes={"grade": "I"},
        )
        culture = Discovery(
            "culture", "An arts centre", "A public cultural venue", Coordinate(51.463, -0.013),
            kind=DiscoveryKind.CULTURAL_VENUE, collection="gla-cultural-infrastructure",
            source_name="GLA Cultural Infrastructure Map", borough="Lewisham",
            attributes={"category": "Arts centre"},
        )
        browser = DiscoveryBrowserWindow(self.parent, [plaque, listed, culture, blossom])
        self.addCleanup(browser.destroy)

        self.assertEqual(
            {
                DiscoveryKind.PLAQUE,
                DiscoveryKind.LISTED_BUILDING,
                DiscoveryKind.CULTURAL_VENUE,
                DiscoveryKind.BLOSSOM,
            },
            {item.kind for item in browser._all_discoveries},
        )
        self.assertEqual("Highlights", browser.filter_dropdown.get_selected_item().get_string())
        browser._show_discovery(listed)
        self.assertEqual("Grade I listed building", browser.kind_value.get_subtitle())
        self.assertEqual("Historic England", browser.source_value.get_subtitle())
        self.assertTrue(browser.map_preview_frame.get_visible())
        browser._show_discovery(blossom)
        self.assertEqual("A tree", browser.detail_title.get_text())
        self.assertEqual("Blossom walk", browser.kind_value.get_subtitle())
        self.assertFalse(hasattr(browser, "details_group"))

        browser.filter_dropdown.set_selected(3)
        self._flush()
        self.assertEqual([culture], browser._visible_discoveries)

        browser.filter_dropdown.set_selected(4)
        self._flush()
        self.assertEqual([blossom], browser._visible_discoveries)

        browser.search_entry.set_text("missing place")
        browser._apply_filter()
        self._flush()
        self.assertEqual([], browser._visible_discoveries)
        self.assertEqual("Try another search", browser.detail_title.get_text())

    def test_compact_story_activation_reveals_details(self) -> None:
        discovery = Discovery("story", "A story", "Details", Coordinate(51.46, -0.01))
        browser = DiscoveryBrowserWindow(self.parent, [discovery])
        self.addCleanup(browser.destroy)
        browser.split_view.set_collapsed(True)
        browser.split_view.set_show_sidebar(True)

        browser.list_box.emit("row-activated", browser.list_box.get_first_child())

        self.assertFalse(browser.split_view.get_show_sidebar())
        self.assertEqual("A story", browser.detail_title.get_text())

    def test_show_on_map_hands_the_selected_story_back_and_closes(self) -> None:
        discovery = Discovery("story", "A story", "Details", Coordinate(51.46, -0.01))
        on_show_on_map = mock.Mock()
        browser = DiscoveryBrowserWindow(self.parent, [discovery], on_show_on_map)
        close_requests = []
        browser.connect("close-request", lambda *_args: close_requests.append(True) and False)
        browser.present()

        browser.show_on_map_button.emit("clicked")
        self._flush()

        on_show_on_map.assert_called_once_with(discovery)
        self.assertEqual(close_requests, [True])


if __name__ == "__main__":
    unittest.main()
