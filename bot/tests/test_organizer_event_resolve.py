"""Восстановление поездки организатора без FSM (callback после другого инстанса)."""

import asyncio
import sys
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import main  # noqa: E402
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey


def test_organizer_event_from_state_falls_back_to_chat_id(monkeypatch) -> None:
    monkeypatch.setattr(main, "load_events", lambda *, merge=False: None)
    main.EVENTS.clear()
    main.EVENTS["trip99"] = {
        "code": "trip99",
        "organizer_chat_id": 424242,
        "updated_at": 999,
        "brief": {"trip_title": "Тест"},
    }
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=424242, user_id=424242)
    state = FSMContext(storage=storage, key=key)

    async def _run() -> None:
        code, event = await main._organizer_event_from_state(state, chat_id=424242)
        assert code == "trip99"
        assert event is not None
        data = await state.get_data()
        assert data.get("event_code") == "trip99"

    asyncio.run(_run())
