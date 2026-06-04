"""Тип ввода до парсера брифа: шум, помощь, факты, дополнение."""

from __future__ import annotations

import re
from typing import Literal, Optional

import message_intent

InputKind = Literal[
    "substantive",
    "supplement_request",
    "share_visibility_request",
    "defer",
    "autofill_request",
    "help",
    "ack",
    "noise",
    "media",
    "action_required",
]

_DEFER_HINTS = (
    r"оставь\s+как\s+есть",
    r"пока\s+так",
    r"пока\s+достаточно",
    r"ещ[её]\s+дума",
    r"подума",
    r"не\s+готов",
    r"верн[её]мся\s+позже",
    r"позже\s+допол",
    r"отлож",
    r"не\s+сейчас",
    r"хватит\s+на\s+сейчас",
    r"черновик\s+ок",
    r"пропуст",
    r"без\s+уточнен",
)

_AUTOFILL_HINTS = (
    r"подбери",
    r"заполни\s+сам",
    r"заполни\s+за",
    r"определи\s+сам",
    r"сопостав",
    r"самостоятельно\s+заполни",
    r"сам\s+реши",
    r"выбери\s+за\s+меня",
    r"предложи\s+вариант",
)

_INVITE_WITH_GAPS_HINTS = (
    r"приглас",
    r"участник",
    r"ссылк",
    r"отправ\w+\s+ссыл",
    r"зови",
    r"подключ",
)

_EXTRA_HELP_HINTS = (
    r"что\s+написать",
    r"не\s+знаю",
    r"как\s+начать",
)

_GREETING_ACK_HINTS = (
    r"^привет\b",
    r"^здравств",
    r"^спасибо",
    r"^благодар",
    r"^ок\b",
    r"^окей\b",
    r"^ага\b",
    r"^да\b",
    r"^хорошо\b",
    r"^понятно\b",
    r"^ясно\b",
    r"^лол\b",
    r"^хах",
)


def _normalized(text: str) -> str:
    return (text or "").strip().lower()


def _brief_score(text: str) -> int:
    return message_intent.brief_hint_score(text)


def _conv_score(text: str) -> int:
    return message_intent.conversation_hint_score(text)


def _greeting_score(text: str) -> int:
    n = _normalized(text)
    return sum(1 for pat in _GREETING_ACK_HINTS if re.search(pat, n, flags=re.IGNORECASE))


def _looks_emoji_or_tiny(normalized: str) -> bool:
    if not normalized:
        return True
    if len(normalized) > 16:
        return False
    letters = re.findall(r"[a-zа-яё0-9]{2,}", normalized, flags=re.IGNORECASE)
    return len(letters) == 0


def is_ack_message(text: str) -> bool:
    normalized = _normalized(text)
    if not normalized:
        return True
    if _brief_score(normalized) >= 1:
        return False
    if _greeting_score(normalized) >= 1:
        return True
    if _looks_emoji_or_tiny(normalized):
        return True
    if len(normalized) <= 20 and _conv_score(normalized) >= 1 and _greeting_score(normalized) == 0:
        return False
    return len(normalized) <= 12 and _brief_score(normalized) == 0 and _conv_score(normalized) == 0


def is_help_message(text: str) -> bool:
    normalized = _normalized(text)
    if not normalized or is_ack_message(text):
        return False
    if _brief_score(normalized) >= 1:
        return False
    if message_intent.is_supplement_request(text, brief_complete=True):
        return False
    extra_help = sum(1 for pat in _EXTRA_HELP_HINTS if re.search(pat, normalized, flags=re.IGNORECASE))
    return _conv_score(normalized) >= 1 or extra_help >= 1 or "?" in normalized


def is_share_visibility_request(text: str) -> bool:
    import brief_visibility

    if brief_visibility.parse_visibility_fields_rules(text):
        return True
    normalized = _normalized(text)
    return brief_visibility.mentions_hide_intent(text) and _brief_score(normalized) < 2


def is_defer_message(text: str) -> bool:
    normalized = _normalized(text)
    if not normalized or _brief_score(normalized) >= 2:
        return False
    if any(re.search(pat, normalized, flags=re.IGNORECASE) for pat in _DEFER_HINTS):
        return True
    if defer_requests_invite_with_gaps(text) and re.search(
        r"потом|позже|пока|без|не\s+все|черновик|хватит",
        normalized,
        flags=re.IGNORECASE,
    ):
        return True
    return False


def defer_requests_invite_with_gaps(text: str) -> bool:
    normalized = _normalized(text)
    if not normalized:
        return False
    return any(re.search(pat, normalized, flags=re.IGNORECASE) for pat in _INVITE_WITH_GAPS_HINTS)


def is_autofill_request(text: str) -> bool:
    normalized = _normalized(text)
    if not normalized:
        return False
    if _brief_score(normalized) >= 2:
        return False
    return any(re.search(pat, normalized, flags=re.IGNORECASE) for pat in _AUTOFILL_HINTS)


def is_noise_message(text: str, *, flow_step: str) -> bool:
    normalized = _normalized(text)
    if not normalized or is_ack_message(text) or is_help_message(text):
        return False
    if _brief_score(normalized) >= 1:
        return False
    if len(normalized) > 40:
        return True
    if flow_step in {"organizer_dump", "organizer_clarify"} and len(normalized) > 18:
        return True
    return False


def classify_input_kind(
    text: str,
    *,
    role: str = "organizer",
    flow_step: str = "unknown",
    brief_complete: bool = False,
    forced_kind: Optional[InputKind] = None,
) -> InputKind:
    if forced_kind:
        return forced_kind
    if brief_complete and message_intent.is_supplement_request(text, brief_complete=True):
        return "supplement_request"
    if role == "organizer" and is_share_visibility_request(text):
        return "share_visibility_request"
    if role == "organizer" and is_defer_message(text):
        return "defer"
    if is_autofill_request(text):
        return "autofill_request"
    normalized = _normalized(text)
    if not normalized:
        return "ack"
    if _brief_score(normalized) >= 2 or (len(normalized) > 100 and _brief_score(normalized) >= 1):
        return "substantive"
    if is_ack_message(text):
        return "ack"
    if is_help_message(text):
        return "help"
    if is_noise_message(text, flow_step=flow_step):
        return "noise"
    if _brief_score(normalized) >= 1:
        return "substantive"
    if flow_step in {"organizer_dump", "organizer_clarify", "participant_contribute"}:
        intent = message_intent.classify_message_intent(
            text, role=role, flow_step=flow_step
        )
        if intent in {"brief_input", "mixed"}:
            return "substantive"
        if intent == "conversation":
            return "help"
    if len(normalized) > 25:
        return "noise"
    return "ack"
