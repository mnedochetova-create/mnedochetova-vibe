"""Интеграционный ретест карточки брифа (кейс Olga, событие #2)."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import brief_parser
import main

OLGA_FIRST = (
    "2 взрослых, 4 детей, июль, путешествие примерно 2-15 июля, "
    "города центральной России: Ивановская область, Владимирская область, "
    "Нижегородская область. Обязательно к посещению Палех, Гороховец, Дивеево. "
    "Проживание в необычных и уединенных домиках, условия с кухней."
)

def _stale_brief() -> dict:
    return {
        "adults": 2,
        "kids_count": 4,
        "date_range_raw": "примерно 2-15 июля",
        "months": ["июль"],
        "budget_rub_max": 200_000,
        "trip_title": "Во Ивановская область с семьёй",
        "regions": [
            "Ивановская область",
            "Владимирская область",
            "Нижегородская область",
        ],
        "must_visit_places": ["Палех", "Гороховец", "Дивеево"],
        "trip_transport": "ground",
        "stay_experience": {"setting": ["Москва"], "trip_style": ["экскурсии"]},
        "destination_primary": "Москва",
    }


def _card(event: dict) -> str:
    brief = brief_parser.restore_organizer_brief_from_event(event)
    return main.format_brief_update_message(
        brief, event_number=2, missing=[], event=event
    )


def test_olga_card_from_stale_storage_with_dump() -> None:
    event = {"brief": _stale_brief(), "organizer_dump": OLGA_FIRST}
    text = _card(event)
    assert "Автопутешествие" in text
    assert "Во Иванов" not in text
    assert "примерно" not in text
    assert "≈14" in text
    assert "🏡" in text and "Проживание" in text
    assert "домик" in text.lower() or "кухн" in text.lower()
    assert "🗺" not in text or "Регионы:" not in text
    assert "👥" not in text or "Группа:" not in text
    assert "Москва" not in text
    assert event["brief"].get("trip_title", "").startswith("Автопутешествие")


def test_olga_card_without_dump_uses_context_raw() -> None:
    polluted = _stale_brief()
    polluted["context_raw"] = OLGA_FIRST
    event = {"brief": polluted}
    text = _card(event)
    assert "🏡" in text
    assert "Автопутешествие" in text


def test_olga_card_prepare_only_no_dump_no_context() -> None:
    """Без дампа и context — проживание не восстановится (ограничение)."""
    brief = _stale_brief()
    event = {"brief": brief}
    text = main.format_brief_update_message(
        copy.deepcopy(brief), event_number=2, missing=[], event=event
    )
    assert "Автопутешествие" in text
    assert "примерно" not in text
    assert "👥" not in text or "Группа:" not in text
    assert "🏡" not in text
