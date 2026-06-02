import sys
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import brief_display  # noqa: E402
import brief_parser  # noqa: E402
import brief_stay_enrich  # noqa: E402

from tests.test_brief_france_family import FRANCE_FAMILY_TEXT  # noqa: E402


def test_france_trip_title_and_duration() -> None:
    brief = brief_parser.extract_brief_from_text(FRANCE_FAMILY_TEXT)
    assert brief.get("trip_title") == "Во Францию с семьёй"
    assert brief_display.get_trip_title(brief) == "Во Францию с семьёй"
    assert brief_display.normalize_duration_display(brief.get("trip_duration_days_raw")) == "10 дней"
    assert brief_display.format_budget_display(brief) == "до 15 000 €"


def test_stay_prose_not_tag_soup() -> None:
    brief = brief_parser.extract_brief_from_text(FRANCE_FAMILY_TEXT)
    brief_stay_enrich.enrich_stay_from_context(brief)
    text = brief_stay_enrich.format_stay_experience_display(brief)
    assert " · " not in text
    assert "франц" in text.lower()
    assert "пляж" in text.lower() or "море" in text.lower()


def test_flight_pending_hint() -> None:
    brief = brief_parser.extract_brief_from_text(FRANCE_FAMILY_TEXT)
    missing = brief_parser.missing_brief_fields(brief)
    flight = brief_display.format_flight_display(brief, missing=missing)
    assert "нужно указать" in flight.lower()


def test_extra_preferences_deduped_against_scenario() -> None:
    brief = brief_parser.extract_brief_from_text(FRANCE_FAMILY_TEXT)
    extras = brief_display.filter_extra_activity_preferences(
        brief,
        ["рестораны и локальная еда", "нужен трансфер из аэропорта"],
    )
    assert not any("ресторан" in x.lower() for x in extras)
    assert any("трансфер" in x.lower() for x in extras)


def test_party_summary_human() -> None:
    brief = brief_parser.extract_brief_from_text(FRANCE_FAMILY_TEXT)
    summary = brief_display.format_party_group_summary(brief)
    assert "брат_и_жена" not in summary
    assert "семь" in summary.lower() or "6 взрослых" in summary
