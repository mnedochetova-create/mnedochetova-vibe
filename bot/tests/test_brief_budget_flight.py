import sys
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import brief_parser  # noqa: E402


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


def test_flight_missing_prefers_preferences_when_destination_set() -> None:
    brief = {
        "months": ["июн"],
        "activity_preferences": ["предпочтение по направлению: Турция"],
        "context_raw": "Турция, июнь",
    }
    missing = brief_parser.missing_brief_fields(brief)
    assert any("эконом" in item for item in missing)
    assert not any("до 5 часов" in item for item in missing)
