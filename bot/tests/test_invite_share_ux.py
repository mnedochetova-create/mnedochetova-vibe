"""Шаг приглашения: нативный share и deeplink в [кнопка ниже](url)."""

import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import main  # noqa: E402


def test_invite_ready_keyboard_uses_native_share_url(monkeypatch) -> None:
    monkeypatch.setattr(main, "BOT_USERNAME", "MyTravelLabBot")
    event = {"invite_link": "https://t.me/MyTravelLabBot?start=join_abc123"}
    kb = main.invite_ready_keyboard(event)
    assert len(kb.inline_keyboard) == 1
    btn = kb.inline_keyboard[0][0]
    assert btn.text == "📤 Поделиться ↗️"
    assert btn.url is not None
    assert btn.url.startswith("https://t.me/share/url?")
    assert "text=" in btn.url
    assert "url=" not in btn.url
    assert btn.callback_data is None


def test_invite_forward_keyboard_for_organizer_preview() -> None:
    link = "https://t.me/MyTravelLabBot?start=join_abc123"
    kb = main.invite_forward_keyboard(link)
    btn = kb.inline_keyboard[0][0]
    assert btn.text == "✅ Присоединиться к поездке"
    assert btn.url == link


def test_invite_step_message_short() -> None:
    text = main.format_invite_step_message(3)
    assert "#3" in text
    assert "Поделиться ↗️" in text
    assert "контактов" in text
    assert "Переслать" not in text
    assert "пересылки" not in text.lower()


def test_invite_step_message_includes_trip_title() -> None:
    event = {
        "event_number": 1,
        "brief": {"trip_title": "Во Францию с семьёй"},
    }
    text = main.format_invite_step_message(1, event=event)
    assert "Во Францию с семьёй" in text
    assert "Поделиться ↗️" in text


def test_participant_join_keyboard(monkeypatch) -> None:
    monkeypatch.setattr(main, "BOT_USERNAME", "TestBot")
    kb = main.participant_join_keyboard("trip99")
    assert kb is not None
    btn = kb.inline_keyboard[0][0]
    assert "Присоединиться" in btn.text
    assert btn.url == "https://t.me/TestBot?start=join_trip99"


def test_build_invite_share_text_for_contacts(monkeypatch) -> None:
    monkeypatch.setattr(main, "BOT_USERNAME", "MyTravelLabBot")
    link = "https://t.me/MyTravelLabBot?start=join_x"
    text = main.build_invite_share_text(link, trip_title="Во Францию с семьёй")
    assert "Привет" in text
    assert "Во Францию с семьёй" in text
    assert "@MyTravelLabBot" in text
    assert "<code>/start join_x</code>" in text
    assert link not in text
    assert "https://" not in text
    assert "MyTravel.Lab" in text

    with_link = main.build_invite_share_text(
        link, trip_title="Во Францию с семьёй", include_link=True
    )
    assert with_link.endswith(link)


def test_build_invite_share_text_native_markdown_cta(monkeypatch) -> None:
    monkeypatch.setattr(main, "BOT_USERNAME", "MyTravelLabBot")
    link = "https://t.me/MyTravelLabBot?start=join_x"
    text = main.build_invite_share_text(link, for_native_share=True)
    assert "@MyTravelLabBot" in text
    assert main.build_invite_share_cta_markdown(link) in text
    assert "[кнопка ниже]" in text
    assert "tg://resolve?domain=MyTravelLabBot&start=join_x" in text
    assert "https://" not in text


def test_invite_share_text_for_native_share(monkeypatch) -> None:
    monkeypatch.setattr(main, "BOT_USERNAME", "MyTravelLabBot")
    event = {
        "invite_link": "https://t.me/MyTravelLabBot?start=join_abc",
        "brief": {"trip_title": "Во Францию с семьёй"},
    }
    text = main.invite_share_text_for_native_share(event)
    assert "Во Францию с семьёй" in text
    assert "[кнопка ниже]" in text
    assert "tg://resolve" in text
    assert "join_abc" in text


def test_invite_share_text_for_event_uses_trip_title(monkeypatch) -> None:
    monkeypatch.setattr(main, "BOT_USERNAME", "MyTravelLabBot")
    event = {
        "invite_link": "https://t.me/MyTravelLabBot?start=join_abc",
        "brief": {"trip_title": "Во Францию с семьёй"},
    }
    text = main.invite_share_text_for_event(event)
    assert "Во Францию с семьёй" in text
    assert "join_abc" in text
    assert "https://" not in text


def test_invite_join_code_from_link() -> None:
    assert main.invite_join_code_from_link("https://t.me/Bot?start=join_596c75") == "596c75"


def test_telegram_share_url_text_with_markdown_button(monkeypatch) -> None:
    monkeypatch.setattr(main, "BOT_USERNAME", "MyTravelLabBot")
    link = "https://t.me/MyTravelLabBot?start=join_abc123"
    event = {"invite_link": link, "brief": {"trip_title": "Во Францию с семьёй"}}
    share_url = main.telegram_share_url(
        link, share_text=main.invite_share_text_for_native_share(event)
    )
    query = parse_qs(urlparse(share_url).query)
    assert "url" not in query
    text = unquote(query["text"][0])
    assert "Во Францию с семьёй" in text
    assert "[кнопка ниже]" in text
    assert "join_abc123" in text
    assert "@MyTravelLabBot" in text
