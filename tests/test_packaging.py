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

    def test_sdk_wrapper_uses_development_manifest_dependencies(self):
        wrapper = (REPOSITORY_ROOT / "scripts" / "test_in_gnome_sdk.sh").read_text()

        self.assertIn("com.nedrichards.lewishamwalks.Devel.json", wrapper)
        self.assertIn("--stop-at=lewisham-walks", wrapper)
        self.assertNotIn("HOST_SITE_PACKAGES", wrapper)

    def test_full_colour_and_symbolic_application_icons_are_packaged(self):
        icon_root = REPOSITORY_ROOT / "data" / "icons" / "hicolor"

        self.assertTrue((icon_root / "scalable" / "apps" / f"{APP_ID}.svg").is_file())
        self.assertTrue((icon_root / "symbolic" / "apps" / f"{APP_ID}-symbolic.svg").is_file())

    def test_manifests_pin_the_same_libshumate_release(self):
        manifests = [
            json.loads((REPOSITORY_ROOT / f"{APP_ID}.json").read_text()),
            json.loads((REPOSITORY_ROOT / f"{APP_ID}.Devel.json").read_text()),
        ]

        for manifest in manifests:
            with self.subTest(manifest=manifest["id"]):
                module = next(item for item in manifest["modules"] if item["name"] == "libshumate")
                source = module["sources"][0]
                self.assertTrue(source["url"].endswith("/libshumate-1.6.3.tar.xz"))
                self.assertEqual(
                    "fd15c91396dcd82fce3021648541aa891e71a6bddeffc03d38597580a7da8ca1",
                    source["sha256"],
                )


if __name__ == "__main__":
    unittest.main()
