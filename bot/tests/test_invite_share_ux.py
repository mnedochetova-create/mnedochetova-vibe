"""Шаг приглашения: одна кнопка share URL и приветствие участника."""

import sys
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import main  # noqa: E402


def test_invite_ready_keyboard_single_share_url_button(monkeypatch) -> None:
    monkeypatch.setattr(main, "BOT_USERNAME", "MyTravelLabBot")
    event = {"invite_link": "https://t.me/MyTravelLabBot?start=join_abc123"}
    kb = main.invite_ready_keyboard(event)
    assert len(kb.inline_keyboard) == 1
    assert len(kb.inline_keyboard[0]) == 1
    btn = kb.inline_keyboard[0][0]
    assert btn.text == "📤 Поделиться приглашением"
    assert btn.url is not None
    assert btn.url.startswith("https://t.me/share/url?")
    assert "join_abc123" in btn.url
    assert btn.callback_data is None


def test_invite_step_message_short() -> None:
    text = main.format_invite_step_message(3)
    assert "Бриф по #3 готов" in text
    assert "Готово — ссылка" not in text
    assert "вручную в чате" not in text


def test_participant_join_keyboard(monkeypatch) -> None:
    monkeypatch.setattr(main, "BOT_USERNAME", "TestBot")
    kb = main.participant_join_keyboard("trip99")
    assert kb is not None
    btn = kb.inline_keyboard[0][0]
    assert "Присоединиться" in btn.text
    assert btn.url == "https://t.me/TestBot?start=join_trip99"


def test_build_invite_share_text_for_contacts() -> None:
    link = "https://t.me/Bot?start=join_x"
    text = main.build_invite_share_text(link, trip_title="Во Францию с семьёй")
    assert "Привет" in text
    assert "Во Францию с семьёй" in text
    assert "в боте" in text.lower()
    assert "посмотри" in text.lower()
    assert "Бюджет:" not in text
    assert link in text
    assert "MyTravel.Lab" in text


def test_invite_share_text_for_event_uses_trip_title() -> None:
    event = {
        "invite_link": "https://t.me/Bot?start=join_abc",
        "brief": {"trip_title": "Во Францию с семьёй"},
    }
    text = main.invite_share_text_for_event(event)
    assert "Во Францию с семьёй" in text
    assert "join_abc" in text
