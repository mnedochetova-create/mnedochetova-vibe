import sys
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import brief_parser  # noqa: E402
import main  # noqa: E402


def test_resolve_prefers_fsm_event_over_older_complete_brief() -> None:
    chat_id = 900001
    main.EVENTS.clear()
    main.EVENTS["old_trip"] = {
        "code": "old_trip",
        "organizer_chat_id": chat_id,
        "updated_at": 100,
        "created_at": 100,
        "brief": {
            "adults": 2,
            "months": ["август"],
            "budget_rub_max": 300000,
            "flight_hours_max": 5,
            "stay_experience": {"setting": ["Турция"], "trip_style": ["пляж"]},
        },
    }
    main.EVENTS["new_trip"] = {
        "code": "new_trip",
        "organizer_chat_id": chat_id,
        "updated_at": 200,
        "created_at": 200,
        "brief": {},
    }
    assert main.resolve_organizer_event_code(chat_id, "new_trip") == "new_trip"
    assert main.resolve_organizer_event_code(chat_id, None) == "new_trip"


def test_resolve_ignores_foreign_preferred_code() -> None:
    chat_id = 900002
    main.EVENTS.clear()
    main.EVENTS["mine"] = {
        "code": "mine",
        "organizer_chat_id": chat_id,
        "updated_at": 50,
        "created_at": 50,
        "brief": {},
    }
    main.EVENTS["other"] = {
        "code": "other",
        "organizer_chat_id": 999999,
        "updated_at": 500,
        "created_at": 500,
        "brief": {"adults": 4, "months": ["июль"], "budget_rub_max": 100000},
    }
    assert main.resolve_organizer_event_code(chat_id, "other") == "mine"
