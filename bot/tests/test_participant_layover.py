"""Пересадка в стране ≠ направление поездки; вклад участника не затирает бриф организатора."""

import sys
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import brief_parser  # noqa: E402
import brief_stay_enrich  # noqa: E402


LAYOVER_TEXT = (
    "Хочу чтобы пересадка в Турции была долгой, "
    "чтобы можно было спокойно поспать в отеле около аэропорта"
)

FRANCE_BASE = {
    "adults": 6,
    "kids_count": 1,
    "months": ["июл"],
    "budget_eur_max": 15_000,
    "budget_currency": "EUR",
    "date_range_raw": "в середине июля",
    "trip_duration_days_raw": "10 дней",
    "transfers_allowed": True,
    "flight_preferences": ["эконом"],
    "stay_experience": {"setting": ["Юг Франции", "Франция"], "trip_style": ["пляж"]},
    "activity_preferences": [],
    "trip_title": "Во Францию с семьёй",
}


def test_layover_turkey_not_destination() -> None:
    t = LAYOVER_TEXT.lower()
    assert brief_stay_enrich._country_in_layover_context(t, "турц")
    assert brief_stay_enrich._detect_destinations(t) == []


def test_layover_parsed_as_flight_preference() -> None:
    incoming, _ = brief_parser.parse_message_to_brief(LAYOVER_TEXT, role="participant")
    prefs = incoming.get("activity_preferences") or []
    assert not any("предпочтение по направлению: Турция" in p for p in prefs)
    flight = incoming.get("flight_preferences") or []
    assert any("долгая пересадка" in p for p in flight)
    assert any("аэропорт" in p for p in flight)
    assert incoming.get("trip_title") != "В Турцию" or "турц" not in str(incoming.get("trip_title", "")).lower()


def test_participant_merge_keeps_france_brief() -> None:
    incoming, _ = brief_parser.parse_message_to_brief(LAYOVER_TEXT, role="participant")
    merged = brief_parser.merge_participant_into_brief(
        dict(FRANCE_BASE), incoming, "Aleksandr Nedochetov"
    )
    assert merged.get("trip_title") == "Во Францию с семьёй"
    assert "Франция" in str(merged.get("stay_experience"))
    assert not any(
        str(p).startswith("предпочтение по направлению: Турция")
        for p in (merged.get("activity_preferences") or [])
    )
    group_flight = merged.get("flight_preferences") or []
    assert any("долгая пересадка" in p for p in group_flight)
    part = merged["participant_preferences"]["Aleksandr Nedochetov"]
    assert part.get("flight_preferences")
