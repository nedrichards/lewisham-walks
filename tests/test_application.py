import os
import unittest
from unittest.mock import patch

from lewisham_walks import APP_ID, runtime_app_id


class RuntimeApplicationIdTests(unittest.TestCase):
    def test_uses_production_id_outside_flatpak(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(runtime_app_id(), APP_ID)

    def test_uses_development_flatpak_id(self):
        self.assertEqual(runtime_app_id(f"{APP_ID}.Devel"), f"{APP_ID}.Devel")

    def test_uses_production_flatpak_id(self):
        self.assertEqual(runtime_app_id(APP_ID), APP_ID)

    def test_rejects_unexpected_flatpak_id(self):
        self.assertEqual(runtime_app_id("com.example.Unrelated"), APP_ID)


if __name__ == "__main__":
    unittest.main()
