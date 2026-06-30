import tempfile
import unittest
from pathlib import Path

import keepsync_diagnostics as diagnostics_module
import keepsync_notes as app


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_report_includes_paths_dependencies_and_recent_log(self):
        diagnostics = diagnostics_module.DiagnosticsManager(
            self.root,
            app.APP_NAME,
            app.APP_VERSION,
            {
                "keyring_available": app.KEYRING_AVAILABLE,
                "gkeepapi_available": app.GKEEPAPI_AVAILABLE,
                "desktop_notifications_available": app.DESKTOP_NOTIFICATIONS_AVAILABLE,
            },
        )
        diagnostics.log_event("info", "unit event")

        report = diagnostics.report(self.root / "notes.db", self.root / "attachments")

        self.assertIn("Database:", report)
        self.assertIn("Attachments:", report)
        self.assertIn(f"{app.APP_NAME} v{app.APP_VERSION}", report)
        self.assertIn("customtkinter:", report)
        self.assertIn("unit event", report)

    def test_exception_logging_tracks_last_exception(self):
        diagnostics = diagnostics_module.DiagnosticsManager(self.root)

        try:
            raise ValueError("boom")
        except ValueError as exc:
            diagnostics.log_exception("unit failure", exc)

        self.assertIn("unit failure", diagnostics.last_exception)
        self.assertIn("boom", diagnostics.recent_log())

    def test_app_reexports_diagnostics_api_for_compatibility(self):
        self.assertIs(app.DiagnosticsManager, diagnostics_module.DiagnosticsManager)
        self.assertIs(app.log_diagnostic_event, diagnostics_module.log_diagnostic_event)
        self.assertIs(app.log_diagnostic_exception, diagnostics_module.log_diagnostic_exception)


if __name__ == "__main__":
    unittest.main()
