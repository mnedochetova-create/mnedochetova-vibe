"""Гарантия: в рантайме бота нет устаревших текстов шага приглашения."""

from pathlib import Path

MAIN_PY = Path(__file__).resolve().parents[1] / "src" / "main.py"

FORBIDDEN = (
    "Базовый бриф уже собран",
    "Готово — ссылка для участников",
    "Текст для пересылки участникам",
    "Я собираю вводные по нашей поездке",
    "invite_after_share_keyboard",
)


def test_main_py_has_no_legacy_invite_strings() -> None:
    source = MAIN_PY.read_text(encoding="utf-8")
    hits = [needle for needle in FORBIDDEN if needle in source]
    assert not hits, f"Legacy invite copy still in main.py: {hits}"
