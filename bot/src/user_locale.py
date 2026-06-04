"""Язык пользователя из Telegram (language_code)."""

from __future__ import annotations

from typing import Any, Optional

# Telegram language_code → ответ бота
_DEFAULT = "ru"
_SUPPORTED = frozenset({"ru", "en", "uk", "de", "fr", "es", "it", "pt", "tr", "kk"})


def resolve_language_code(user: Any) -> str:
    if user is None:
        return _DEFAULT
    raw = getattr(user, "language_code", None) or ""
    code = str(raw).strip().lower().split("-")[0]
    if not code:
        return _DEFAULT
    if code in _SUPPORTED:
        return code
    return "en" if code.isascii() else _DEFAULT


def language_display_name(code: str) -> str:
    names = {
        "ru": "русский",
        "en": "English",
        "uk": "українська",
        "de": "Deutsch",
        "fr": "français",
        "es": "español",
        "it": "italiano",
        "pt": "português",
        "tr": "Türkçe",
        "kk": "қазақша",
    }
    return names.get(code, code)


def llm_locale_instruction(code: Optional[str] = None) -> str:
    lang = code or _DEFAULT
    name = language_display_name(lang)
    return (
        f"Write every assistant_text in {name} (language_code={lang}). "
        "Match the user's Telegram interface language."
    )


def persist_language_on_event(event: dict, user: Any) -> str:
    code = resolve_language_code(user)
    event["user_language_code"] = code
    return code


def voice_transcribed_prefix(code: str, text: str) -> str:
    if code == "en":
        return f"🎙 <i>Heard:</i> {text}\n\n"
    return f"🎙 <i>Распознала:</i> {text}\n\n"


def voice_failed_message(code: str) -> str:
    if code == "en":
        return (
            "🎙 <b>Couldn't transcribe the voice message.</b>\n\n"
            "Try again or type your trip details in one message."
        )
    return (
        "🎙 <b>Не получилось распознать голосовое.</b>\n\n"
        "Повтори запись или напиши вводные текстом одним сообщением."
    )


def voc_rating_prompt(code: str) -> str:
    if code == "en":
        return (
            "⭐ <b>Quick feedback</b>\n\n"
            "The brief is ready — how was collecting it? "
            "Pick a rating (helps us improve the bot)."
        )
    return (
        "⭐ <b>Короткий отзыв</b>\n\n"
        "Бриф готов — насколько тебе было удобно собирать вводные? "
        "Оцени по шкале (это поможет улучшить бота)."
    )


def voc_feedback_prompt(code: str, rating: int) -> str:
    if code == "en":
        return (
            f"Thanks for <b>{rating}/5</b>.\n\n"
            "What felt off or what should we improve? "
            "A few words or a voice message — I'll save it for the team."
        )
    return (
        f"Спасибо за <b>{rating}/5</b>.\n\n"
        "Что было неудобно или что улучшить? "
        "Напиши пару фраз или отправь голосовое — передам команде."
    )


def voc_thanks(code: str) -> str:
    if code == "en":
        return "🙏 <b>Thanks!</b> Your feedback is saved — we'll use it to improve the bot."
    return "🙏 <b>Спасибо!</b> Записала отзыв — учтём при улучшении бота."


def voc_skip_ack(code: str) -> str:
    if code == "en":
        return "Ok, you can continue with the invite or menu anytime."
    return "Ок, можно продолжать с приглашением или через меню."
