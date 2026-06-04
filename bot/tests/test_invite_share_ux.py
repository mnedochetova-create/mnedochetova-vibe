"""Шаг приглашения: нативный t.me/share и текст с именем организатора."""

import sys
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import main  # noqa: E402


def test_invite_ready_keyboard_uses_native_share_url(monkeypatch) -> None:
    monkeypatch.setattr(main, "BOT_USERNAME", "MyTravelLabBot")
    event = {
        "invite_link": "https://t.me/MyTravelLabBot?start=join_abc123",
        "organizer_name": "Мария",
        "brief": {"trip_title": "Тест"},
    }
    kb = main.invite_ready_keyboard(event)
    assert len(kb.inline_keyboard) == 1
    btn = kb.inline_keyboard[0][0]
    assert btn.text == "📤 Поделиться ↗️"
    assert btn.callback_data is None
    assert btn.url is not None
    from urllib.parse import parse_qs, unquote, urlparse

    assert "t.me/share/url" in btn.url
    query = parse_qs(urlparse(btn.url).query)
    assert "Мария" in unquote(query["text"][0])
    assert "Организатор" in unquote(query["text"][0])


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
    assert "выбери" in text.lower() or "чат" in text
    assert "организатора" in text


def test_resolve_organizer_user_ignores_bot_message_author() -> None:
    class BotUser:
        is_bot = True
        first_name = "MyTravel.Lab"

    class Human:
        is_bot = False
        first_name = "Мария"
        full_name = "Мария Н."
        username = "maria_n"

    class Msg:
        from_user = BotUser()

    assert main.resolve_organizer_user(Msg()) is None
    assert main.resolve_organizer_user(Msg(), from_user=Human()).first_name == "Мария"


def test_organizer_display_name_fallbacks() -> None:
    class U:
        first_name = ""
        full_name = "Maria Nedochetova"
        username = "maria_n"

    assert main.organizer_display_name_from_user(U()) == "Maria Nedochetova"

    class U2:
        first_name = ""
        full_name = ""
        username = "maria_n"

    assert main.organizer_display_name_from_user(U2()) == "@maria_n"


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


def test_build_invite_share_html_has_link_in_button_below(monkeypatch) -> None:
    monkeypatch.setattr(main, "BOT_USERNAME", "MyTravelLabBot")
    event = {
        "invite_link": "https://t.me/MyTravelLabBot?start=join_x",
        "brief": {"trip_title": "Во Францию с семьёй"},
        "organizer_name": "Мария",
    }
    html_text = main.build_invite_share_html_for_event(event)
    assert "Во Францию с семьёй" in html_text
    assert "Организатор <b>Мария</b> собрал" in html_text
    assert '<a href="https://t.me/MyTravelLabBot?start=join_x">кнопка ниже</a>' in html_text
    assert "https://t.me/" not in html_text.replace(
        'href="https://t.me/MyTravelLabBot?start=join_x"', ""
    )


def test_build_invite_share_text_for_contacts(monkeypatch) -> None:
    monkeypatch.setattr(main, "BOT_USERNAME", "MyTravelLabBot")
    link = "https://t.me/MyTravelLabBot?start=join_x"
    text = main.build_invite_share_text(link, trip_title="Во Францию с семьёй")
    assert "Привет" in text
    assert "Во Францию с семьёй" in text
    assert "<code>/start join_x</code>" in text
    assert link not in text


def test_invite_share_text_for_event_uses_trip_title(monkeypatch) -> None:
    monkeypatch.setattr(main, "BOT_USERNAME", "MyTravelLabBot")
    event = {
        "invite_link": "https://t.me/MyTravelLabBot?start=join_abc",
        "brief": {"trip_title": "Во Францию с семьёй"},
    }
    text = main.invite_share_text_for_event(event)
    assert "Во Францию с семьёй" in text
    assert "join_abc" in text


def test_invite_join_code_from_link() -> None:
    assert main.invite_join_code_from_link("https://t.me/Bot?start=join_596c75") == "596c75"


def test_invite_forward_card_already_sent() -> None:
    assert not main.invite_forward_card_already_sent({})
    assert main.invite_forward_card_already_sent({"invite_forward_message_id": 42})


def test_telegram_share_url_includes_deeplink_and_text() -> None:
    from urllib.parse import parse_qs, unquote, urlparse

    link = "https://t.me/MyTravelLabBot?start=join_abc123"
    share_url = main.telegram_share_url(
        link,
        share_text=main.build_invite_share_text(
            link, organizer_name="Мария", for_native_share=True
        ),
    )
    query = parse_qs(urlparse(share_url).query)
    assert query["url"][0] == link
    assert "кнопка ниже" in unquote(query["text"][0])
    assert "Организатор Мария" in unquote(query["text"][0])
