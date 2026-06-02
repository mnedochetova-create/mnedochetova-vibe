#!/usr/bin/env python3
"""Опционально: MP4 из logo.png (нужны Pillow + ffmpeg). В проде используем logo.png inline."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    raise SystemExit("pip install Pillow")

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
LOGO = ASSETS / "logo.png"
CANVAS = 512
BG_RGB = (67, 86, 255)


def _square_logo() -> Image.Image:
    logo = Image.open(LOGO).convert("RGBA")
    side = min(logo.size)
    left = (logo.width - side) // 2
    top = (logo.height - side) // 2
    logo = logo.crop((left, top, left + side, top + side))
    fit = int(CANVAS * 0.82)
    return logo.resize((fit, fit), Image.Resampling.LANCZOS)


def _frame(logo: Image.Image, angle: float) -> Image.Image:
    rotated = logo.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
    canvas = Image.new("RGB", (CANVAS, CANVAS), BG_RGB)
    x = (CANVAS - rotated.width) // 2
    y = (CANVAS - rotated.height) // 2
    canvas.paste(rotated, (x, y), rotated)
    return canvas


def thinking_mp4() -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg not found — skip MP4 (runtime uses logo.png)", file=sys.stderr)
        return
    logo = _square_logo()
    frames = [_frame(logo, i * 15) for i in range(24)]
    out = ASSETS / "thinking.mp4"
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        for index, frame in enumerate(frames):
            frame.save(tmp / f"frame_{index:03d}.png")
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-framerate",
                "20",
                "-i",
                str(tmp / "frame_%03d.png"),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-an",
                str(out),
            ],
            check=True,
            capture_output=True,
        )
    print("wrote", out)


if __name__ == "__main__":
    if not LOGO.is_file():
        raise SystemExit(f"Missing {LOGO}")
    thinking_mp4()
