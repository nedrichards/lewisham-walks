import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "src" / "lewishamwalks.in"


class LauncherTests(unittest.TestCase):
    def test_launcher_ignores_modules_beside_the_executable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data"
            repository = data / "gi" / "repository"
            repository.mkdir(parents=True)
            (data / "gi" / "__init__.py").write_text("", encoding="utf-8")
            (repository / "__init__.py").write_text(
                "class Resource:\n"
                "    @classmethod\n"
                "    def load(cls, path): return cls()\n"
                "    def _register(self): pass\n"
                "class Gio:\n"
                "    Resource = Resource\n",
                encoding="utf-8",
            )
            package = data / "lewisham_walks"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "main.py").write_text("def main(version): return 0\n", encoding="utf-8")
            (root / "gi.py").write_text("raise RuntimeError('Untrusted module beside launcher')\n", encoding="utf-8")
            launcher = root / "lewishamwalks"
            launcher.write_text(
                TEMPLATE.read_text(encoding="utf-8")
                .replace("@PYTHON@", sys.executable)
                .replace("@VERSION@", "test")
                .replace("@pkgdatadir@", str(data)),
                encoding="utf-8",
            )
            launcher.chmod(0o755)
            result = subprocess.run(  # noqa: S603 -- generated launcher in an isolated temporary fixture
                [str(launcher)],
                cwd=root,
                env={**os.environ, "PYTHONPATH": ""},
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
