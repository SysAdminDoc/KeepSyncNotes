import unittest

import keepsync_bootstrap as bootstrap
import keepsync_notes as app


class FakeApp:
    def __init__(self):
        self.protocol_calls = []
        self.mainloop_called = False

    def protocol(self, name, callback):
        self.protocol_calls.append((name, callback))

    def on_closing(self):
        pass

    def mainloop(self):
        self.mainloop_called = True


class BootstrapTests(unittest.TestCase):
    def test_help_flag_prints_usage_without_launching_app(self):
        lines = []
        launched = []

        code = bootstrap.run_bootstrap(
            ["keepsync_notes.py", "--help"],
            app_factory=lambda: launched.append(True),
            token_cli=lambda: None,
            app_name="KeepSync",
            app_version="9.9.9",
            set_appearance_mode=lambda value: None,
            set_default_color_theme=lambda value: None,
            output=lines.append,
        )

        self.assertEqual(code, 0)
        self.assertEqual(lines[0], "KeepSync v9.9.9")
        self.assertIn("--get-token", "\n".join(lines))
        self.assertFalse(launched)

    def test_token_flag_runs_token_cli_without_launching_app(self):
        calls = []

        code = bootstrap.run_bootstrap(
            ["keepsync_notes.py", "--get-token"],
            app_factory=lambda: calls.append("app"),
            token_cli=lambda: calls.append("token"),
            app_name="KeepSync",
            app_version="9.9.9",
            set_appearance_mode=lambda value: calls.append(("mode", value)),
            set_default_color_theme=lambda value: calls.append(("theme", value)),
        )

        self.assertEqual(code, 0)
        self.assertEqual(calls, ["token"])

    def test_no_flag_configures_and_launches_app(self):
        calls = []
        fake_app = FakeApp()

        code = bootstrap.run_bootstrap(
            ["keepsync_notes.py"],
            app_factory=lambda: fake_app,
            token_cli=lambda: calls.append("token"),
            app_name="KeepSync",
            app_version="9.9.9",
            set_appearance_mode=lambda value: calls.append(("mode", value)),
            set_default_color_theme=lambda value: calls.append(("theme", value)),
        )

        self.assertEqual(code, 0)
        self.assertEqual(calls, [("mode", "dark"), ("theme", "blue")])
        self.assertEqual(fake_app.protocol_calls[0][0], "WM_DELETE_WINDOW")
        self.assertIs(fake_app.protocol_calls[0][1].__self__, fake_app)
        self.assertIs(fake_app.protocol_calls[0][1].__func__, FakeApp.on_closing)
        self.assertTrue(fake_app.mainloop_called)

    def test_app_reexports_bootstrap_for_compatibility(self):
        self.assertIs(app.run_bootstrap, bootstrap.run_bootstrap)


if __name__ == "__main__":
    unittest.main()
