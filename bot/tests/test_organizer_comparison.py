"""Сравнение направлений (кейс Elena Filipchenkova, organizer)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import brief_parser
import message_intent

ELENA_FIRST = (
    "2 взрослых, Хорватия, конец сентября, с чем можно совместить? "
    "италия? франция? чтобы посмотреть максимум"
)


def test_elena_message_intent_mixed():
    assert (
        message_intent.classify_message_intent(
            ELENA_FIRST, role="organizer", flow_step="organizer_dump"
        )
        == "mixed"
    )


def test_elena_parse_primary_and_alternatives():
    brief = brief_parser.extract_brief_from_text(ELENA_FIRST, role="organizer")
    assert brief.get("adults") == 2
    assert brief.get("destination_primary") == "Хорватия"
    alts = brief.get("destination_alternatives") or []
    assert "Италия" in alts
    assert "Франция" in alts
    assert brief.get("months") == ["сентябрь"]
    assert "конец сентября" in (brief.get("date_range_raw") or "").lower()
    assert not any("Франция (Шенген)" in str(n) for n in (brief.get("visa_notes") or []))
    party = (brief.get("party_preferences") or {}).get("организатор") or {}
    assert "Франция" not in (party.get("wants") or [])
    prefs = brief.get("activity_preferences") or []
    direction_prefs = [p for p in prefs if str(p).lower().startswith("предпочтение по направлению:")]
    assert len(direction_prefs) == 1
    assert "Хорватия" in direction_prefs[0]


def test_elena_clarify_second_message_merges():
    first = brief_parser.extract_brief_from_text(ELENA_FIRST, role="organizer")
    second = brief_parser.extract_brief_from_text(
        "бюджет гибкий, перелет с пересадками - оба варианта и эконом и бизнес",
        role="organizer",
    )
    merged = brief_parser.merge_organizer_incoming(
        first, second, flow_step="organizer_clarify", has_prior_dump=True
    )
    assert merged.get("budget_flexible")
    assert merged.get("destination_primary") == "Хорватия"
    assert brief_parser.organizer_core_brief_ok(merged)
