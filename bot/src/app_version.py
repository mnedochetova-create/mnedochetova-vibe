"""Единый источник версии приложения: файл VERSION в корне репозитория."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_FALLBACK = "0.0.0-dev"


def _read_version_file(path: Path) -> Optional[str]:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def resolve_app_version() -> str:
    """
    Версия для логов и build-строки в /start.
    Приоритет: BOT_UI_VERSION (env) → VERSION (файл) → fallback.
    """
    override = os.getenv("BOT_UI_VERSION", "").strip()
    if override:
        return override

    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "VERSION",  # repo root (локально и /app в Docker)
        here.parents[1] / "VERSION",  # bot/VERSION — запасной путь
        Path("/app/VERSION"),
    ]
    for path in candidates:
        value = _read_version_file(path)
        if value:
            return value
    return _FALLBACK
