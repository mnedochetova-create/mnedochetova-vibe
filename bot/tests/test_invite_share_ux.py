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
    assert len(kb.inline_keyboard) == 2
    assert len(kb.inline_keyboard[0]) == 1
    btn = kb.inline_keyboard[0][0]
    assert btn.text == "📤 Поделиться приглашением"
    assert btn.url is not None
    assert btn.url.startswith("https://t.me/share/url?")
    assert "join_abc123" in btn.url
    assert btn.callback_data is None
    sent_btn = kb.inline_keyboard[1][0]
    assert sent_btn.callback_data == "event:invite_sent"


def test_invite_step_message_short() -> None:
    text = main.format_invite_step_message(3)
    assert "#3" in text
    assert "Поделиться приглашением" in text
    assert "в боте" in text.lower()
    assert "Готово — ссылка" not in text
    assert "вручную в чате" not in text


def test_invite_step_message_includes_trip_title() -> None:
    event = {
        "event_number": 1,
        "brief": {"trip_title": "Во Францию с семьёй"},
    }
    text = main.format_invite_step_message(1, event=event)
    assert "Во Францию с семьёй" in text
    assert "Поделиться приглашением" in text


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
    assert link not in text
    assert "MyTravel.Lab" in text

    with_link = main.build_invite_share_text(
        link, trip_title="Во Францию с семьёй", include_link=True
    )
    assert with_link.endswith(link)


def test_invite_share_text_for_event_uses_trip_title() -> None:
    event = {
        "invite_link": "https://t.me/Bot?start=join_abc",
        "brief": {"trip_title": "Во Францию с семьёй"},
    }
    text = main.invite_share_text_for_event(event)
    assert "Во Францию с семьёй" in text
    assert "join_abc" not in text


def test_telegram_share_url_has_single_link_at_end() -> None:
    from urllib.parse import parse_qs, unquote, urlparse

    link = "https://t.me/MyTravelLabBot?start=join_abc123"
    event = {"invite_link": link, "brief": {"trip_title": "Во Францию с семьёй"}}
    share_url = main.telegram_share_url(link, share_text=main.invite_share_text_for_event(event))
    query = parse_qs(urlparse(share_url).query)
    assert "url" not in query
    text = unquote(query["text"][0])
    assert text.index("Привет") < text.index(link)
    assert text.count(link) == 1
    assert "Во Францию с семьёй" in text
