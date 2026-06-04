"""user_locale: язык из Telegram language_code."""

from types import SimpleNamespace

import user_locale
import voc_feedback


def test_resolve_language_code_ru():
    user = SimpleNamespace(language_code="ru")
    assert user_locale.resolve_language_code(user) == "ru"


def test_resolve_language_code_en_us():
    user = SimpleNamespace(language_code="en-US")
    assert user_locale.resolve_language_code(user) == "en"


def test_resolve_language_code_unknown_latin_defaults_en():
    user = SimpleNamespace(language_code="sv")
    assert user_locale.resolve_language_code(user) == "en"


def test_resolve_language_code_missing_defaults_ru():
    assert user_locale.resolve_language_code(None) == "ru"


def test_llm_locale_instruction_contains_code():
    text = user_locale.llm_locale_instruction("de")
    assert "de" in text
    assert "Deutsch" in text


def test_voc_parse_rating_from_text():
    assert voc_feedback.parse_rating_from_text("4") == 4
    assert voc_feedback.parse_rating_from_text("оценка 5") == 5
    assert voc_feedback.parse_rating_from_text("hello") is None
