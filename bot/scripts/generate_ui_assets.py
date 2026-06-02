#!/usr/bin/env python3
"""Сгенерировать thinking.gif и success.gif для ui_feedback (нужен Pillow)."""

from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError as err:
    raise SystemExit("pip install Pillow") from err

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

BG = (0, 122, 255, 255)
FG = (255, 80, 160, 255)


def _frame(angle: int) -> Image.Image:
    img = Image.new("RGBA", (128, 128), BG)
    layer = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.text((28, 44), "MTL", fill=FG)
    rotated = layer.rotate(angle, resample=Image.Resampling.BICUBIC, center=(64, 64))
    return Image.alpha_composite(img, rotated)


def thinking_gif() -> None:
    frames = [_frame(i * 30) for i in range(12)]
    out = ASSETS / "thinking.gif"
    frames[0].save(
        out,
        save_all=True,
        append_images=frames[1:],
        duration=80,
        loop=0,
        disposal=2,
    )
    print("wrote", out)


def success_gif() -> None:
    frames = []
    for scale in (1.0, 1.08, 1.0, 1.05, 1.0):
        img = Image.new("RGBA", (128, 128), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        size = int(72 * scale)
        x = (128 - size) // 2
        draw.ellipse((x, x, x + size, x + size), fill=(76, 175, 80, 255))
        draw.text((x + size // 3, x + size // 4), "✓", fill=(255, 255, 255, 255))
        frames.append(img)
    out = ASSETS / "success.gif"
    frames[0].save(
        out,
        save_all=True,
        append_images=frames[1:],
        duration=120,
        loop=1,
        disposal=2,
    )
    print("wrote", out)


if __name__ == "__main__":
    thinking_gif()
    success_gif()
