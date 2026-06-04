"""trip_from_brief: recommendation_ready, readiness, draft proposals."""

import sys
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import trip_from_brief  # noqa: E402


def _ready_brief() -> dict:
    return {
        "trip_title": "В Турцию с семьёй",
        "destination_primary": "Анталья",
        "months": ["июль"],
        "budget_rub_max": 300_000,
        "adults": 2,
        "kids_count": 1,
        "flight_hours_max": 4,
        "transfers_allowed": True,
    }


def _ready_event() -> dict:
    return {
        "code": "evt01",
        "organizer_brief_confirmed_at": 1_700_000_000,
        "brief": _ready_brief(),
    }


def test_build_recommendation_ready_schema() -> None:
    ready = trip_from_brief.build_recommendation_ready(_ready_event())
    assert ready["schema_version"] == "1"
    assert ready["event_code"] == "evt01"
    assert ready["trip_mode"] == "single_destination"
    assert ready["destinations"]["primary"] == "Анталья"
    assert ready["dates"]["months"] == ["июль"]
    assert ready["budget"]["rub_max"] == 300_000
    assert ready["transport"]["mode"] == "flight"


def test_assess_ready_when_confirmed() -> None:
    event = _ready_event()
    ready = trip_from_brief.build_recommendation_ready(event)
    readiness = trip_from_brief.assess_trip_readiness(event, recommendation_ready=ready)
    assert readiness["ready"] is True
    assert readiness["blockers"] == []


def test_assess_blocked_without_confirm() -> None:
    event = _ready_event()
    event.pop("organizer_brief_confirmed_at")
    readiness = trip_from_brief.assess_trip_readiness(event)
    assert readiness["ready"] is False
    assert trip_from_brief.BLOCKER_BRIEF_NOT_CONFIRMED in readiness["blockers"]


def test_assess_blocked_missing_flight() -> None:
    event = _ready_event()
    event["brief"].pop("flight_hours_max")
    event["brief"].pop("transfers_allowed")
    readiness = trip_from_brief.assess_trip_readiness(event)
    assert trip_from_brief.BLOCKER_MISSING_TRANSPORT in readiness["blockers"]


def test_generate_draft_proposals() -> None:
    event = _ready_event()
    proposals, readiness = trip_from_brief.generate_draft_proposals(event)
    assert readiness["ready"] is True
    assert 1 <= len(proposals) <= 3
    assert proposals[0]["status"] == "draft"
    assert proposals[0]["proposal_id"] == "p1"
    assert "черновик" in " ".join(proposals[0].get("tradeoffs") or []).lower()


def test_prepare_trip_proposals_writes_event() -> None:
    event = _ready_event()
    trip_from_brief.prepare_trip_proposals_for_event(event)
    assert event["recommendation_ready"]["event_code"] == "evt01"
    assert event["trip_proposals_status"] == "draft"
    assert len(event["trip_proposals"]) >= 1


def test_combo_route_templates() -> None:
    event = {
        "code": "combo1",
        "organizer_brief_confirmed_at": 1,
        "brief": {
            "months": ["август"],
            "budget_rub_max": 500_000,
            "activity_preferences": [
                "собрать комбинацию стран: Турция, Греция",
            ],
            "flight_hours_max": 5,
            "transfers_allowed": False,
        },
    }
    ready = trip_from_brief.build_recommendation_ready(event)
    assert ready["trip_mode"] == "combo_route"
    proposals, readiness = trip_from_brief.generate_draft_proposals(event, recommendation_ready=ready)
    assert readiness["ready"] is True
    assert "комбо" in proposals[0]["title"].lower() or "комбо" in str(proposals[0].get("tags"))


def test_format_proposals_html_escapes() -> None:
    proposals = [
        {
            "proposal_id": "p1",
            "title": "Test <b>",
            "destination_label": "X & Y",
            "why_fit": ["a <b>"],
            "tradeoffs": [],
        }
    ]
    html = trip_from_brief.format_proposals_html(proposals)
    assert "&lt;b&gt;" in html
    assert "<b>Test" not in html
