import ast
import re
import unittest
from pathlib import Path

from PIL import Image

from keepsync_app_info import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


class BrandingPackagingTests(unittest.TestCase):
    def test_icon_master_is_transparent_and_full_size(self):
        with Image.open(ROOT / "icon.png") as icon:
            self.assertEqual(icon.size, (1024, 1024))
            self.assertEqual(icon.mode, "RGBA")
            self.assertEqual(icon.getpixel((0, 0))[3], 0)

    def test_entry_point_guards_frozen_multiprocessing(self):
        source = (ROOT / "keepsync_notes.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        executable_statements = [
            node for node in tree.body
            if not isinstance(node, (ast.Import, ast.ImportFrom))
            and not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
        ]
        self.assertEqual(ast.unparse(executable_statements[0]), "multiprocessing.freeze_support()")

        hook = (ROOT / "packaging" / "runtime_hook_mp.py").read_text(encoding="utf-8")
        self.assertIn("multiprocessing.freeze_support()", hook)

    def test_release_builder_creates_a_windowed_onefile_app(self):
        script = (ROOT / "packaging" / "build_release.ps1").read_text(encoding="utf-8")
        self.assertIn("--onefile", script)
        self.assertIn("--windowed", script)
        self.assertIn("--icon icon.ico", script)
        self.assertIn("--version-file packaging\\version_info.txt", script)
        self.assertIn("--runtime-hook packaging\\runtime_hook_mp.py", script)

        version_info = (ROOT / "packaging" / "version_info.txt").read_text(encoding="utf-8")
        self.assertIn("FileVersion', '1.56.1'", version_info)
        self.assertIn("ProductVersion', '1.56.1'", version_info)

    def test_public_version_strings_match(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        version_info = (ROOT / "packaging" / "version_info.txt").read_text(encoding="utf-8")
        self.assertIn(f"version-{APP_VERSION}-", readme)
        self.assertIn(f"## [v{APP_VERSION}]", changelog)
        self.assertIn(f"FileVersion', '{APP_VERSION}'", version_info)
        self.assertIn(f"ProductVersion', '{APP_VERSION}'", version_info)

    def test_readme_has_one_evergreen_hero_and_distinct_product_captures(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        hero_reference = "assets/marketing/hero.png"
        self.assertEqual(readme.splitlines()[0],
                         "![KeepSync Notes turns a Google Takeout archive into a private local note library]"
                         f"({hero_reference})")
        self.assertEqual(readme.count(hero_reference), 1)
        self.assertEqual(readme.count("assets/marketing/screenshots/library-and-editor.png"), 1)
        self.assertEqual(readme.count("assets/marketing/screenshots/import-export-and-backup.png"), 1)

        with Image.open(ROOT / hero_reference) as hero:
            self.assertEqual(hero.size, (1600, 900))

        hero_source = (ROOT / "tools" / "build_marketing_assets.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\bv?\d+\.\d+\.\d+\b", hero_source))


if __name__ == "__main__":
    unittest.main()
