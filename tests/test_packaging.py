import json
import unittest
from pathlib import Path

from lewisham_walks import APP_ID

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class DevelopmentManifestTests(unittest.TestCase):
    def test_development_identity_and_local_build_contract(self):
        manifest = json.loads(
            (REPOSITORY_ROOT / "com.nedrichards.lewishamwalks.Devel.json").read_text()
        )

        self.assertEqual(f"{APP_ID}.Devel", manifest["id"])
        self.assertEqual(" (Development)", manifest["desktop-file-name-suffix"])
        self.assertEqual(f"{APP_ID}.desktop", manifest["rename-desktop-file"])
        self.assertEqual(f"{APP_ID}.metainfo.xml", manifest["rename-appdata-file"])
        self.assertEqual(APP_ID, manifest["rename-icon"])
        self.assertTrue(manifest["copy-icon"])

        app_module = manifest["modules"][-1]
        self.assertTrue(app_module["run-tests"])
        self.assertEqual({"type": "dir", "path": "."}, app_module["sources"][0])


if __name__ == "__main__":
    unittest.main()
