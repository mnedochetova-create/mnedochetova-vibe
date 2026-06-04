"""Новая поездка: вводные не теряются после load_events."""

import sys
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import main  # noqa: E402


def test_load_events_merge_keeps_unsaved_new_trip() -> None:
    main.EVENTS.clear()
    main.EVENTS["fresh_trip"] = {
        "code": "fresh_trip",
        "organizer_chat_id": 42,
        "updated_at": 9999,
        "brief": {},
    }
    main.load_events(merge=True)
    assert "fresh_trip" in main.EVENTS
    assert main.EVENTS["fresh_trip"]["updated_at"] == 9999


def test_hydrate_from_fsm_recreates_missing_event(monkeypatch) -> None:
    monkeypatch.setattr(main, "BOT_USERNAME", "TestBot")
    main.EVENTS.clear()
    data = {
        "role": "organizer",
        "organizer_chat_id": 42,
        "event_code": "abc123",
        "event_number": 7,
        "brief": {},
    }
    code = main._hydrate_organizer_event_from_fsm(42, "abc123", data)
    assert code == "abc123"
    assert main.EVENTS["abc123"]["event_number"] == 7
    assert "join_abc123" in (main.EVENTS["abc123"].get("invite_link") or "")


def test_resolve_prefers_fsm_new_trip_over_old() -> None:
    chat_id = 9001
    main.EVENTS.clear()
    main.EVENTS["trip_old"] = {
        "code": "trip_old",
        "organizer_chat_id": chat_id,
        "updated_at": 5000,
        "brief": {"adults": 2, "months": ["июль"], "budget_rub_max": 100_000},
    }
    main.EVENTS["trip_new"] = {
        "code": "trip_new",
        "organizer_chat_id": chat_id,
        "updated_at": 6000,
        "brief": {},
    }
    code = main.resolve_organizer_event_code(chat_id, "trip_new")
    assert code == "trip_new"


def test_create_event_text_normalized() -> None:
    assert main.is_create_event_text("✨ Новая поездка")
    assert main.is_create_event_text("новая поездка")
