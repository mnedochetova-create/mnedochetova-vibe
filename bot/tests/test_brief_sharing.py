"""Tests for final brief confirm and share helpers."""

from main import (
    build_brief_share_text,
    can_offer_brief_confirm,
    format_brief_plain_for_share,
    participants_all_confirmed,
)

FULL_BRIEF = {
    "months": ["июль 2026"],
    "date_range_raw": "июль 2026",
    "budget_rub_max": 250000,
    "adults": 2,
    "kids_count": 1,
    "flight_hours_max": 5,
    "visa_required": False,
    "climate": "море/пляж",
    "trip_type": "пляжный",
    "context_raw": "семейная поездка",
}


def test_can_confirm_without_participants():
    event = {"brief": dict(FULL_BRIEF), "participants": {}}
    assert can_offer_brief_confirm(event) is True


def test_cannot_confirm_when_already_confirmed():
    event = {
        "brief": dict(FULL_BRIEF),
        "participants": {},
        "organizer_brief_confirmed_at": 1,
    }
    assert can_offer_brief_confirm(event) is False


def test_participants_all_confirmed_requires_everyone():
    event = {
        "participants": {"1": {}, "2": {}},
        "participant_updates": {"1": {"confirmed": True}, "2": {"confirmed": False}},
    }
    assert participants_all_confirmed(event) is False
    event["participant_updates"]["2"]["confirmed"] = True
    assert participants_all_confirmed(event) is True


def test_build_brief_share_text_includes_body():
    plain = format_brief_plain_for_share(FULL_BRIEF, event_number=3)
    text = build_brief_share_text(plain)
    assert "MyTravel.Lab" in text
    assert "июль 2026" in text
    assert "организатору" in text
