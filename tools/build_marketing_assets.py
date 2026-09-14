#!/usr/bin/env python3
"""Build the evergreen README hero from verified product captures."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
MARKETING = ROOT / "assets" / "marketing"
SCREENSHOTS = MARKETING / "screenshots"
WIDTH = 1600
HEIGHT = 900


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(Path("C:/Windows/Fonts") / name), size)


def rounded_image(image: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, image.width - 1, image.height - 1), radius, fill=255)
    result = image.convert("RGBA")
    result.putalpha(mask)
    return result


def draw_pill(draw: ImageDraw.ImageDraw, xy: tuple[int, int], label: str, accent: str) -> int:
    x, y = xy
    label_font = font("segoeuib.ttf", 18)
    bounds = draw.textbbox((0, 0), label, font=label_font)
    width = bounds[2] - bounds[0] + 48
    draw.rounded_rectangle((x, y, x + width, y + 46), 23, fill="#13233b", outline="#284563", width=2)
    draw.ellipse((x + 16, y + 17, x + 28, y + 29), fill=accent)
    draw.text((x + 36, y + 10), label, font=label_font, fill="#e2e8f0")
    return width


def build() -> Path:
    MARKETING.mkdir(parents=True, exist_ok=True)
    screenshot_path = SCREENSHOTS / "library-and-editor.png"
    if not screenshot_path.is_file():
        raise FileNotFoundError(f"Missing verified screenshot: {screenshot_path}")

    canvas = Image.new("RGB", (WIDTH, HEIGHT), "#07111f")
    draw = ImageDraw.Draw(canvas)
    start = (7, 17, 31)
    end = (14, 31, 51)
    for y in range(HEIGHT):
        mix = y / (HEIGHT - 1)
        color = tuple(round(a + (b - a) * mix) for a, b in zip(start, end))
        draw.line((0, y, WIDTH, y), fill=color)

    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((1060, -210, 1760, 490), fill=(37, 99, 235, 78))
    glow_draw.ellipse((930, 500, 1550, 1120), fill=(34, 197, 94, 54))
    glow = glow.filter(ImageFilter.GaussianBlur(105))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), glow)
    draw = ImageDraw.Draw(canvas)

    icon = Image.open(ROOT / "icon.png").convert("RGBA")
    icon.thumbnail((94, 94), Image.Resampling.LANCZOS)
    canvas.alpha_composite(icon, (86, 72))
    draw.text((198, 84), "LOCAL-FIRST DESKTOP NOTES", font=font("segoeuib.ttf", 21), fill="#67e8f9")
    draw.text((198, 118), "KeepSync Notes", font=font("segoeuib.ttf", 31), fill="#f8fafc")

    headline_font = font("segoeuib.ttf", 64)
    draw.text((86, 230), "Your Keep notes,", font=headline_font, fill="#f8fafc")
    draw.text((86, 304), "finally yours.", font=headline_font, fill="#f8fafc")

    body_font = font("segoeui.ttf", 28)
    body_lines = [
        "Import a Google Takeout archive.",
        "Search and organize everything locally.",
        "Export whenever you want.",
    ]
    y = 410
    for line in body_lines:
        draw.text((88, y), line, font=body_font, fill="#b7c6db")
        y += 42

    pill_rows = [
        ((88, 574), "Takeout import", "#60a5fa"),
        ((308, 574), "Full-text search", "#22c55e"),
        ((88, 634), "Encrypted backup", "#a78bfa"),
        ((329, 634), "Portable exports", "#fbbf24"),
    ]
    for position, label, accent in pill_rows:
        draw_pill(draw, position, label, accent)

    draw.text((88, 792), "github.com/SysAdminDoc/KeepSyncNotes", font=font("segoeui.ttf", 20), fill="#7dd3fc")

    frame = (664, 126, 1530, 710)
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle((frame[0] + 12, frame[1] + 20, frame[2] + 12, frame[3] + 20), 30, fill=(0, 0, 0, 118))
    shadow = shadow.filter(ImageFilter.GaussianBlur(28))
    canvas = Image.alpha_composite(canvas, shadow)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(frame, 30, fill="#0b1729", outline="#315274", width=2)

    draw.ellipse((692, 148, 706, 162), fill="#22d3ee")
    draw.ellipse((716, 148, 730, 162), fill="#60a5fa")
    draw.ellipse((740, 148, 754, 162), fill="#334155")
    draw.text((779, 140), "REAL APP  •  SAMPLE WORKSPACE", font=font("segoeuib.ttf", 17), fill="#8fb3d9")

    screenshot = Image.open(screenshot_path).convert("RGB")
    screenshot.thumbnail((826, 510), Image.Resampling.LANCZOS)
    screenshot = rounded_image(screenshot, 18)
    screenshot_x = frame[0] + (frame[2] - frame[0] - screenshot.width) // 2
    screenshot_y = 184
    canvas.alpha_composite(screenshot, (screenshot_x, screenshot_y))

    footer_y = 742
    captions = [
        (690, "Keep the hierarchy"),
        (902, "Find old ideas"),
        (1101, "Back up safely"),
        (1306, "Leave cleanly"),
    ]
    colors = ["#60a5fa", "#22c55e", "#a78bfa", "#fbbf24"]
    for (x, label), accent in zip(captions, colors):
        draw.rounded_rectangle((x, footer_y, x + 182, footer_y + 54), 14, fill="#101f35", outline="#29435f", width=2)
        draw.rectangle((x, footer_y, x + 6, footer_y + 54), fill=accent)
        draw.text((x + 18, footer_y + 15), label, font=font("segoeuib.ttf", 16), fill="#dbeafe")

    output = MARKETING / "hero.png"
    canvas.convert("RGB").save(output, quality=94, optimize=True)
    return output


def write_checksums() -> Path:
    concept = ROOT / "assets" / "concepts" / "2026-09-13-marketing"
    checksum_path = concept / "SHA256SUMS.txt"
    files = [path for path in concept.rglob("*") if path.is_file() and path != checksum_path]
    files.extend(
        path
        for path in MARKETING.rglob("*")
        if path.is_file() and path not in files
    )
    files.extend(path for path in (ROOT / "assets" / "branding").rglob("*") if path.is_file())
    files.extend([ROOT / "icon.svg", ROOT / "icon.png", ROOT / "icon.ico"])
    lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(ROOT).as_posix()}"
        for path in sorted(set(files))
    ]
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return checksum_path


if __name__ == "__main__":
    print(build())
    print(write_checksums())
