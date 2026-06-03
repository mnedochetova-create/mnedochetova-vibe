import sys
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import brief_parser  # noqa: E402


def test_usd_budget_not_in_missing() -> None:
    text = "2 взрослых, июль, Турция, бюджет до 5000 долларов, море"
    brief = brief_parser.extract_brief_from_text(text)
    missing = brief_parser.missing_brief_fields(brief)
    assert brief_parser.budget_is_set(brief)
    assert brief.get("budget_currency") == "USD"
    assert not any(m.startswith("Бюджет") for m in missing)


def test_budget_flexible_closes_missing() -> None:
    brief = brief_parser.extract_brief_from_text("Турция, июнь, бюджет гибкий, 2 взрослых")
    assert brief.get("budget_flexible") is True
    missing = brief_parser.missing_brief_fields(brief)
    assert not any("Бюджет" in item for item in missing)


def test_budget_range_400_600k() -> None:
    brief = brief_parser.extract_brief_from_text("бюджет 400-600к, август")
    assert brief.get("budget_rub_min") == 400_000
    assert brief.get("budget_rub_max") == 600_000


def test_flight_preferences_direct_economy() -> None:
    brief = brief_parser.extract_brief_from_text("Турция, прямой перелет, эконом")
    assert brief.get("transfers_allowed") is False
    assert "эконом" in (brief.get("flight_preferences") or [])
    missing = brief_parser.missing_brief_fields(brief)
    assert not any("Перелёт" in item for item in missing)


def test_flight_clarify_moscow_transfer_economy() -> None:
    brief = brief_parser.extract_brief_from_text("перелет из москвы с 1 пересадкой, эконом класс")
    assert brief.get("transfers_allowed") is True
    prefs = brief.get("flight_preferences") or []
    assert "эконом" in prefs
    assert any("Москв" in item for item in prefs)


def test_flight_clarify_does_not_wipe_existing_brief() -> None:
    dump = "семья 2 взрослых и 1 ребенок, июль, бюджет до 300к, юг франции, море"
    base, _ = brief_parser.parse_message_to_brief(dump, role="organizer")
    clarify, _ = brief_parser.parse_message_to_brief(
        "перелет из москвы с 1 пересадкой, эконом класс",
        role="organizer",
    )
    merged = brief_parser.merge_organizer_incoming(
        base,
        clarify,
        flow_step="organizer_clarify",
    )
    assert merged.get("adults") == 2
    assert merged.get("budget_rub_max") == 300_000
    assert "июль" in (merged.get("months") or [])
    assert merged.get("transfers_allowed") is True
    assert "эконом" in (merged.get("flight_preferences") or [])


def test_date_range_closes_dates_missing() -> None:
    brief = brief_parser.extract_brief_from_text("Турция, 13-24 июня, 2 взрослых, бюджет 300к")
    missing = brief_parser.missing_brief_fields(brief)
    assert not any("Окна дат" in item for item in missing)


def test_context_raw_accumulates_on_clarify() -> None:
    base = brief_parser.extract_brief_from_text("Турция Бодрум, 3 взрослых")
    extra = brief_parser.extract_brief_from_text("13-23 июня, бюджет гибкий")
    merged = brief_parser.merge_brief_clarify(base, extra)
    assert "Бодрум" in (merged.get("context_raw") or "")
    assert "июн" in (merged.get("context_raw") or "").lower() or merged.get("months")


def test_passports_ok_phrase() -> None:
    brief = brief_parser.extract_brief_from_text("загранпаспорта ок, Турция")
    assert brief.get("passports_status") == "есть"


def test_party_split_hotels() -> None:
    brief = brief_parser.extract_brief_from_text(
        "3 взрослых, Бодрум, 3-4 дня с мужем в другом отеле"
    )
    assert brief.get("party_preferences")


def test_flight_missing_prefers_preferences_when_destination_set() -> None:
    brief = {
        "months": ["июн"],
        "activity_preferences": ["предпочтение по направлению: Турция"],
        "context_raw": "Турция, июнь",
    }
    missing = brief_parser.missing_brief_fields(brief)
    assert any("эконом" in item for item in missing)
    assert not any("до 5 часов" in item for item in missing)
