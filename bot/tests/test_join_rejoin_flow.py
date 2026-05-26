import asyncio
import sys
from pathlib import Path
from typing import Optional, Tuple, Dict, Any


BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import main  # noqa: E402


class DummyChat:
    def __init__(self, chat_id: int):
        self.id = chat_id


class DummyUser:
    def __init__(self, full_name: str, username: Optional[str] = None):
        self.full_name = full_name
        self.username = username


class DummyMessage:
    def __init__(self, chat_id: int, full_name: str, username: Optional[str] = None):
        self.chat = DummyChat(chat_id)
        self.from_user = DummyUser(full_name, username)
        self.answers: list[Tuple[str, Optional[object]]] = []
        self.bot = object()

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answers.append((text, reply_markup))


class DummyState:
    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.state = None

    async def update_data(self, **kwargs) -> None:
        self.data.update(kwargs)

    async def set_state(self, state) -> None:
        self.state = state


class DummyCommand:
    def __init__(self, args: str):
        self.args = args


async def _noop_async(*args, **kwargs) -> None:
    return None


def test_start_payload_join_adds_new_participant(monkeypatch) -> None:
    chat_id = 111
    event_code = "abc123"
    monkeypatch.setattr(main, "save_events", lambda: None)
    monkeypatch.setattr(main, "now_ts", lambda: 1700000000)
    monkeypatch.setattr(main, "log_session_action", _noop_async)

    original_events = main.EVENTS
    main.EVENTS = {
        event_code: {
            "code": event_code,
            "event_number": 42,
            "organizer_chat_id": 999,
            "participants": {},
            "brief": {},
        }
    }
    try:
        message = DummyMessage(chat_id=chat_id, full_name="Test User", username="testuser")
        state = DummyState()
        command = DummyCommand(args=f"join_{event_code}")

        asyncio.run(main.start_payload_handler(message, command, state))

        participant = main.EVENTS[event_code]["participants"][str(chat_id)]
        assert participant["role"] == "participant"
        assert participant["name"] == "Test User"
        assert participant["username"] == "testuser"
        assert participant["joined_at"] == 1700000000
        assert participant["updated_at"] == 1700000000
        assert state.state == main.FlowState.participant_contribute
        assert state.data["event_code"] == event_code
        assert state.data["role"] == "participant"
    finally:
        main.EVENTS = original_events


def test_start_payload_rejoin_keeps_confirmed_flags(monkeypatch) -> None:
    chat_id = 222
    event_code = "def456"
    monkeypatch.setattr(main, "save_events", lambda: None)
    monkeypatch.setattr(main, "now_ts", lambda: 1700001111)
    monkeypatch.setattr(main, "log_session_action", _noop_async)

    original_events = main.EVENTS
    main.EVENTS = {
        event_code: {
            "code": event_code,
            "event_number": 7,
            "organizer_chat_id": 999,
            "brief": {},
            "participants": {
                str(chat_id): {
                    "role": "participant",
                    "name": "Old Name",
                    "username": "old_username",
                    "joined_at": 1699999999,
                    "confirmed": True,
                    "confirmed_at": 1699999998,
                }
            },
        }
    }
    try:
        message = DummyMessage(chat_id=chat_id, full_name="New Name", username="new_username")
        state = DummyState()
        command = DummyCommand(args=f"join_{event_code}")

        asyncio.run(main.start_payload_handler(message, command, state))

        participant = main.EVENTS[event_code]["participants"][str(chat_id)]
        assert participant["joined_at"] == 1699999999
        assert participant["confirmed"] is True
        assert participant["confirmed_at"] == 1699999998
        assert participant["name"] == "New Name"
        assert participant["username"] == "new_username"
        assert participant["updated_at"] == 1700001111
    finally:
        main.EVENTS = original_events


def test_start_payload_join_unknown_event_shows_expired_link(monkeypatch) -> None:
    monkeypatch.setattr(main, "save_events", lambda: None)
    monkeypatch.setattr(main, "log_session_action", _noop_async)
    original_events = main.EVENTS
    main.EVENTS = {}
    try:
        message = DummyMessage(chat_id=333, full_name="Ghost")
        state = DummyState()
        command = DummyCommand(args="join_missing")

        asyncio.run(main.start_payload_handler(message, command, state))

        assert message.answers, "Expected at least one response message"
        first_text = message.answers[0][0]
        assert "ссылка устарела" in first_text.lower()
        assert state.state is None
    finally:
        main.EVENTS = original_events
