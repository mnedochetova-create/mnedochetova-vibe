"""Сравнение направлений (кейс Elena Filipchenkova, organizer)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import brief_parser
import brief_route_combo
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


def test_elena_parse_combo_in_preferences():
    brief = brief_parser.extract_brief_from_text(ELENA_FIRST, role="organizer")
    assert brief.get("adults") == 2
    assert brief.get("route_combo_planning") is True
    combo = brief_route_combo.combo_line_from_brief(brief)
    assert combo.lower().startswith(brief_route_combo.COMBO_LINE_PREFIX)
    assert "Хорватия" in combo
    assert "Италия" in combo
    assert "Франция" in combo
    assert "максимум достопримечательностей" in (brief.get("activity_preferences") or [])
    assert not brief.get("destination_alternatives")
    assert brief.get("climate") != "море/пляж"
    assert "конец сентября" in (brief.get("date_range_raw") or "").lower()
    assert brief.get("trip_title", "").startswith("Комбо")


def test_elena_missing_no_flight_on_first_message():
    brief = brief_parser.extract_brief_from_text(ELENA_FIRST, role="organizer")
    missing = brief_parser.missing_brief_fields(brief)
    assert not any(m.startswith("Перелёт") for m in missing)
    assert not any(m.startswith("Передвижение") for m in missing)
    assert any("дней на комбо" in m.lower() for m in missing)


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
    assert brief_route_combo.is_route_combo_planning(merged)
    assert brief_parser.organizer_core_brief_ok(merged)
