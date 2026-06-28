import tempfile
import unittest
from pathlib import Path

import keepsync_notes as app


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_report_includes_paths_dependencies_and_recent_log(self):
        diagnostics = app.DiagnosticsManager(self.root)
        diagnostics.log_event("info", "unit event")

        report = diagnostics.report(self.root / "notes.db", self.root / "attachments")

        self.assertIn("Database:", report)
        self.assertIn("Attachments:", report)
        self.assertIn("customtkinter:", report)
        self.assertIn("unit event", report)

    def test_exception_logging_tracks_last_exception(self):
        diagnostics = app.DiagnosticsManager(self.root)

        try:
            raise ValueError("boom")
        except ValueError as exc:
            diagnostics.log_exception("unit failure", exc)

        self.assertIn("unit failure", diagnostics.last_exception)
        self.assertIn("boom", diagnostics.recent_log())


if __name__ == "__main__":
    unittest.main()
