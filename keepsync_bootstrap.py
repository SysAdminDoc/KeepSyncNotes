"""Command-line bootstrap helpers for KeepSyncNotes."""

from typing import Callable, Sequence


TOKEN_FLAGS = {"--get-token", "-t", "--token"}
HELP_FLAGS = {"--help", "-h"}


def print_help(app_name: str, app_version: str, output: Callable[[str], None] = print) -> None:
    output(f"{app_name} v{app_version}")
    output("")
    output("Usage: python keep_sync_notes.py [OPTIONS]")
    output("")
    output("Options:")
    output("  --get-token, -t  Generate a Google Master Token for Keep sync")
    output("  --help, -h       Show this help message")
    output("")
    output("Run without arguments to start the application.")


def run_bootstrap(
    argv: Sequence[str],
    app_factory: Callable[[], object],
    token_cli: Callable[[], object],
    app_name: str,
    app_version: str,
    set_appearance_mode: Callable[[str], None],
    set_default_color_theme: Callable[[str], None],
    output: Callable[[str], None] = print,
) -> int:
    args = list(argv or [])
    if len(args) > 1:
        option = args[1]
        if option in TOKEN_FLAGS:
            token_cli()
            return 0
        if option in HELP_FLAGS:
            print_help(app_name, app_version, output)
            return 0

    set_appearance_mode("dark")
    set_default_color_theme("blue")

    app = app_factory()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
    return 0
