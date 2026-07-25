import unittest

from lewisham_walks.ui.layout import (
    COMPACT_BREAKPOINT,
    CONTROLS_WIDE_MAX_WIDTH,
    CONTROLS_WIDE_MIN_WIDTH,
    MAP_WIDE_MIN_WIDTH,
    SIDEBAR_COMPACT_WIDTH_FRACTION,
    SIDEBAR_WIDE_WIDTH_FRACTION,
    WIDE_LAYOUT_GUTTER,
)


class LayoutBreakpointTests(unittest.TestCase):
    def test_compact_breakpoint_requires_readable_sidebar_and_map(self) -> None:
        self.assertEqual(COMPACT_BREAKPOINT, CONTROLS_WIDE_MIN_WIDTH + MAP_WIDE_MIN_WIDTH + WIDE_LAYOUT_GUTTER)
        self.assertLess(COMPACT_BREAKPOINT, 1280)
        self.assertGreaterEqual(COMPACT_BREAKPOINT, CONTROLS_WIDE_MIN_WIDTH + MAP_WIDE_MIN_WIDTH)

    def test_sidebar_widths_are_readable_and_more_immersive_when_compact(self) -> None:
        self.assertGreater(CONTROLS_WIDE_MAX_WIDTH, CONTROLS_WIDE_MIN_WIDTH)
        self.assertGreater(SIDEBAR_WIDE_WIDTH_FRACTION, 0.3)
        self.assertLess(SIDEBAR_WIDE_WIDTH_FRACTION, 0.5)
        self.assertGreater(SIDEBAR_COMPACT_WIDTH_FRACTION, SIDEBAR_WIDE_WIDTH_FRACTION)
        self.assertLessEqual(SIDEBAR_COMPACT_WIDTH_FRACTION, 1.0)


if __name__ == "__main__":
    unittest.main()
