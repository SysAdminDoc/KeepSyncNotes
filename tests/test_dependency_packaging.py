import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DependencyPackagingTests(unittest.TestCase):
    def test_runtime_installers_are_removed(self):
        source = (ROOT / "keepsync_notes.py").read_text(encoding="utf-8")

        forbidden = [
            "install_dependencies",
            "REQUIRED_PACKAGES",
            "subprocess.run",
            '"pip", "install"',
            "'pip', 'install'",
            "--break-system-packages",
        ]
        for marker in forbidden:
            self.assertNotIn(marker, source)

    def test_requirements_include_direct_runtime_dependencies(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

        expected = [
            "customtkinter==",
            "Pillow==",
            "requests==",
            "gkeepapi==",
            "gpsoauth==",
            "browser-cookie3==",
            "plyer==",
            "keyring==",
            "PyGithub==",
            "google-api-python-client==",
            "google-auth==",
            "google-auth-oauthlib==",
        ]
        for package in expected:
            self.assertIn(package, requirements)


if __name__ == "__main__":
    unittest.main()
