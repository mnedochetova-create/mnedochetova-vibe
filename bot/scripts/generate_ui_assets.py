#!/usr/bin/env python3
"""Сгенерировать thinking.mp4 и success.mp4 из bot/assets/logo.png (Pillow + ffmpeg)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError as err:
    raise SystemExit("pip install Pillow") from err

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
LOGO = ASSETS / "logo.png"
CANVAS = 512
BG_RGB = (67, 86, 255)


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg not found — install ffmpeg or build via Dockerfile")
    return ffmpeg


def _square_logo() -> Image.Image:
    if not LOGO.is_file():
        raise SystemExit(f"Missing {LOGO}")
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


def _write_mp4(frames: list[Image.Image], out: Path, *, fps: int = 20) -> None:
    ffmpeg = _require_ffmpeg()
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        for index, frame in enumerate(frames):
            frame.save(tmp / f"frame_{index:03d}.png")
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-framerate",
                str(fps),
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


def thinking_mp4() -> None:
    logo = _square_logo()
    frames = [_frame(logo, i * 15) for i in range(24)]
    out = ASSETS / "thinking.mp4"
    _write_mp4(frames, out)
    print("wrote", out, "size", out.stat().st_size)


def success_mp4() -> None:
    logo = _square_logo()
    frames = []
    for scale in (1.0, 1.06, 1.0, 1.03, 1.0):
        fit = int(CANVAS * 0.82 * scale)
        scaled = logo.resize((fit, fit), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (CANVAS, CANVAS), BG_RGB)
        x = (CANVAS - fit) // 2
        y = (CANVAS - fit) // 2
        canvas.paste(scaled, (x, y), scaled)
        frames.append(canvas)
    out = ASSETS / "success.mp4"
    _write_mp4(frames, out, fps=12)
    print("wrote", out, "size", out.stat().st_size)


if __name__ == "__main__":
    ASSETS.mkdir(parents=True, exist_ok=True)
    thinking_mp4()
    success_mp4()
