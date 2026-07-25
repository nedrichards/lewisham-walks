import unittest
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
    except Exception as error:
        return None, None, None, None, error


Adw, Gio, GLib, Gtk, GTK_IMPORT_ERROR = _load_gtk()

if Adw is not None:
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

    def get_string(self, key: str) -> str:
        return ""

    def set_string(self, key: str, value: str) -> None:
        pass

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

    def test_compact_layout_releases_the_desktop_minimum_width(self) -> None:
        self.window._apply_responsive_layout(390, 780)
        self._flush()

        minimum, _natural, _minimum_baseline, _natural_baseline = self.window.measure(
            Gtk.Orientation.HORIZONTAL,
            -1,
        )

        self.assertLessEqual(minimum, 390)

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

        with mock.patch("lewisham_walks.ui.main_window.PreferencesWindow") as preferences_type:
            self.window._show_preferences(None)
            self.window._show_preferences(None)
            preferences_type.assert_called_once_with(self.window)
            self.assertEqual(2, preferences_type.return_value.present.call_count)

    def test_primary_menu_and_standard_dialogs_use_native_gnome_patterns(self) -> None:
        self.assertEqual(3, self.window.menu_button.get_menu_model().get_n_items())

        self.window._show_shortcuts(None)
        shortcuts_window = self.window._shortcuts_window
        self.assertIsInstance(shortcuts_window, Gtk.ShortcutsWindow)
        self.assertIs(shortcuts_window.get_transient_for(), self.window)
        self.window._show_shortcuts(None)
        self.assertIs(shortcuts_window, self.window._shortcuts_window)

        self.window._show_about(None)
        about_dialog = self.window._about_dialog
        self.assertIsInstance(about_dialog, Adw.AboutDialog)
        self.assertEqual("Lewisham Walks", about_dialog.get_application_name())
        self.assertEqual("Nick Richards", about_dialog.get_developer_name())

        shortcuts_window.close()
        about_dialog.close()
        self._flush()
        self.assertIsNone(self.window._shortcuts_window)
        self.assertIsNone(self.window._about_dialog)

    def test_closed_story_browser_is_released_for_a_fresh_window(self) -> None:
        self.window._show_discovery_browser(None)
        browser = self.window._stories_window
        self.assertIsNotNone(browser)

        browser.close()
        self._flush()

        self.assertIsNone(self.window._stories_window)

    def test_story_browser_handoff_focuses_the_map(self) -> None:
        discovery = self.window.all_discoveries[0]
        self.window.split_view.set_show_sidebar(True)

        with mock.patch.object(self.window.map_widget, "focus_discovery") as focus_discovery:
            self.window._show_discovery_on_map(discovery)

        focus_discovery.assert_called_once_with(discovery)
        self.assertFalse(self.window.split_view.get_show_sidebar())

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
        ):
            app.do_activate()
            app.do_activate()

        window_type.assert_called_once_with(app)
        self.assertEqual(2, window_type.return_value.present.call_count)
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

    def test_explicit_close_action_destroys_the_window(self) -> None:
        close_requests = []
        self.window.connect("close-request", lambda *_args: close_requests.append(True) and False)
        self.window.present()

        self.window.close_button.emit("clicked")
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
        browser = DiscoveryBrowserWindow(self.parent, [plaque, blossom])
        self.addCleanup(browser.destroy)

        self.assertEqual({DiscoveryKind.PLAQUE, DiscoveryKind.BLOSSOM}, {item.kind for item in browser._all_discoveries})
        browser._show_discovery(blossom)
        self.assertEqual("A tree", browser.detail_title.get_text())
        self.assertEqual("Blossom walk", browser.kind_value.get_text())
        self.assertFalse(hasattr(browser, "details_group"))

        browser.filter_dropdown.set_selected(1)
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
