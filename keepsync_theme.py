"""Shared color tokens for the KeepSyncNotes UI."""

COLORS_DARK = {
    "bg_darkest": "#020617",
    "bg_dark": "#0f172a",
    "bg_medium": "#1e293b",
    "bg_light": "#334155",
    "bg_hover": "#475569",

    "accent_green": "#22c55e",
    "accent_green_hover": "#16a34a",
    "accent_green_dim": "#166534",

    "accent_blue": "#60a5fa",
    "accent_blue_hover": "#3b82f6",
    "accent_blue_dim": "#1e40af",

    "accent_yellow": "#fbbf24",
    "accent_red": "#ef4444",
    "accent_purple": "#a78bfa",
    "accent_cyan": "#22d3ee",

    "text_primary": "#f8fafc",
    "text_secondary": "#94a3b8",
    "text_muted": "#64748b",
    "text_disabled": "#475569",

    "border": "#334155",
    "border_light": "#475569",
    "divider": "#1e293b",

    "sync_synced": "#22c55e",
    "sync_pending": "#fbbf24",
    "sync_error": "#ef4444",
    "sync_local": "#60a5fa",
}

COLORS_LIGHT = {
    "bg_darkest": "#eff1f5",
    "bg_dark": "#e6e9ef",
    "bg_medium": "#ccd0da",
    "bg_light": "#bcc0cc",
    "bg_hover": "#acb0be",

    "accent_green": "#40a02b",
    "accent_green_hover": "#349023",
    "accent_green_dim": "#a6d189",

    "accent_blue": "#1e66f5",
    "accent_blue_hover": "#1756d9",
    "accent_blue_dim": "#7287fd",

    "accent_yellow": "#df8e1d",
    "accent_red": "#d20f39",
    "accent_purple": "#8839ef",
    "accent_cyan": "#179299",

    "text_primary": "#4c4f69",
    "text_secondary": "#6c6f85",
    "text_muted": "#8c8fa1",
    "text_disabled": "#9ca0b0",

    "border": "#bcc0cc",
    "border_light": "#ccd0da",
    "divider": "#e6e9ef",

    "sync_synced": "#40a02b",
    "sync_pending": "#df8e1d",
    "sync_error": "#d20f39",
    "sync_local": "#1e66f5",
}

COLORS = dict(COLORS_DARK)


def set_theme(theme: str):
    source = COLORS_LIGHT if theme == "light" else COLORS_DARK
    COLORS.clear()
    COLORS.update(source)


def get_theme_name() -> str:
    return "light" if COLORS.get("bg_darkest") == COLORS_LIGHT["bg_darkest"] else "dark"
