#!/usr/bin/env python3
"""Сгенерировать thinking.gif и success.gif из bot/assets/logo.png (нужен Pillow)."""

from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError as err:
    raise SystemExit("pip install Pillow") from err

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
LOGO = ASSETS / "logo.png"
CANVAS = 512
BG_RGB = (67, 86, 255)


def _square_logo() -> Image.Image:
    if not LOGO.is_file():
        raise SystemExit(f"Missing {LOGO}")
    logo = Image.open(LOGO).convert("RGBA")
    side = min(logo.size)
    left = (logo.width - side) // 2
    top = (logo.height - side) // 2
    logo = logo.crop((left, top, left + side, top + side))
    fit = int(CANVAS * 0.82)
    logo = logo.resize((fit, fit), Image.Resampling.LANCZOS)
    return logo


def _paste_rotated(canvas: Image.Image, logo: Image.Image, angle: float) -> Image.Image:
    rotated = logo.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
    layer = Image.new("RGBA", canvas.size, (*BG_RGB, 255))
    x = (CANVAS - rotated.width) // 2
    y = (CANVAS - rotated.height) // 2
    layer.paste(rotated, (x, y), rotated)
    return layer.convert("RGB")


def _to_gif_palette(frame: Image.Image) -> Image.Image:
    return frame.convert("P", palette=Image.ADAPTIVE, colors=256)


def thinking_gif() -> None:
    logo = _square_logo()
    frames = [_to_gif_palette(_paste_rotated(Image.new("RGB", (CANVAS, CANVAS), BG_RGB), logo, i * 15)) for i in range(24)]
    out = ASSETS / "thinking.gif"
    frames[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=60,
        loop=0,
        disposal=2,
        optimize=False,
    )
    print("wrote", out, "size", out.stat().st_size)


def success_gif() -> None:
    logo = _square_logo()
    frames = []
    for scale in (1.0, 1.06, 1.0, 1.03, 1.0):
        fit = int(CANVAS * 0.82 * scale)
        scaled = logo.resize((fit, fit), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (CANVAS, CANVAS), BG_RGB)
        x = (CANVAS - fit) // 2
        y = (CANVAS - fit) // 2
        canvas.paste(scaled, (x, y), scaled)
        frames.append(_to_gif_palette(canvas))
    out = ASSETS / "success.gif"
    frames[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=140,
        loop=1,
        disposal=2,
        optimize=False,
    )
    print("wrote", out, "size", out.stat().st_size)


if __name__ == "__main__":
    ASSETS.mkdir(parents=True, exist_ok=True)
    thinking_gif()
    success_gif()
