"""Маршрутизация реплики: ввод в бриф vs живой диалог vs смешанная."""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Literal, Optional

from env_util import env_flag

MessageIntent = Literal["brief_input", "conversation", "mixed"]

_BRIEF_HINTS = (
    r"\d+\s*взросл",
    r"\d+\s*дет",
    r"\d+\s*реб",
    r"бюджет",
    r"\d+\s*к\b",
    r"\d+\s*тыс",
    r"млн",
    r"₽|руб",
    r"перел[её]т",
    r"пересад",
    r"без виз",
    r"\bвиз",
    r"загран",
    r"море",
    r"пляж",
    r"гор[ыи]",
    r"экскурс",
    r"январ",
    r"феврал",
    r"март",
    r"апрел",
    r"\bмай\b",
    r"июн",
    r"июл",
    r"август",
    r"сентябр",
    r"октябр",
    r"ноябр",
    r"декабр",
    r"конец\s+\w+",
    r"начал[оа]\s+\w+",
    r"грец",
    r"турц",
    r"испан",
    r"итали",
    r"кипр",
    r"ази",
    r"европ",
    r"франц",
    r"евро",
    r"€",
    r"семей",
    r"семь[её]",
    r"пляж",
    r"ресторан",
    r"отдых",
    r"\d+\s*час",
    r"дн[ея]й",
    r"ноч",
)

_EXPLORATION_HINTS = (
    r"совмест",
    r"посмотреть\s+максим",
    r"чем\s+можно",
    r"что\s+лучше",
    r"какое\s+направлен",
    r"вариант\w*\s+поездк",
)

_SUPPLEMENT_HINTS = (
    r"дополн",
    r"добав",
    r"исправ",
    r"измен",
    r"уточн",
    r"забыл",
    r"не\s+указал",
    r"ещ[её]\s+одн",
    r"хочу\s+внест",
    r"поправ",
    r"внес[ти]",
    r"обнови\s+бриф",
)

_CONVERSATION_HINTS = (
    r"^что\s+(написать|делать|дальше|отправить)",
    r"^как\s+(это|работает|начать|правильно)",
    r"не\s+понима",
    r"не\s+знаю\s+что",
    r"помоги\b",
    r"подскажи",
    r"объясни",
    r"зачем\b",
    r"можно\s+ли\b",
    r"что\s+такое",
    r"^спасибо\b",
    r"^привет\b",
    r"^здравств",
    r"что\s+имеется\s+в\s+виду",
    r"не\s+получается",
    r"запутал",
    r"устал",
    r"сложно",
    r"не\s+уверен",
    r"боюсь",
    r"страшно",
    r"пережива",
)


def _count_patterns(text: str, patterns: tuple[str, ...]) -> int:
    return sum(1 for pat in patterns if re.search(pat, text, flags=re.IGNORECASE))


def brief_hint_score(text: str) -> int:
    return _count_patterns((text or "").strip().lower(), _BRIEF_HINTS)


def conversation_hint_score(text: str) -> int:
    return _count_patterns((text or "").strip().lower(), _CONVERSATION_HINTS)


def _ends_with_question(text: str) -> bool:
    return bool(re.search(r"\?\s*$", text))


def is_supplement_request(text: str, *, brief_complete: bool) -> bool:
    """
    Просьба дополнить/исправить бриф без новых фактов в том же сообщении.
    Срабатывает только когда бриф уже полный (brief_complete=True).
    """
    if not brief_complete:
        return False
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    if _count_patterns(normalized, _BRIEF_HINTS) >= 1:
        return False
    return _count_patterns(normalized, _SUPPLEMENT_HINTS) >= 1


def classify_message_intent(
    text: str,
    *,
    role: str = "organizer",
    flow_step: str = "unknown",
) -> MessageIntent:
    """
    brief_input — факты/пожелания → парсер + фиксированные экраны.
    conversation — вопросы и помощь с формулировкой → live целиком.
    mixed — и вопрос, и факты → короткий live + бриф в одном ответе.
    """
    normalized = (text or "").strip().lower()
    if not normalized:
        return "conversation"

    brief_score = _count_patterns(normalized, _BRIEF_HINTS)
    conv_score = _count_patterns(normalized, _CONVERSATION_HINTS)
    exploration_score = _count_patterns(normalized, _EXPLORATION_HINTS)
    has_question = "?" in normalized or _ends_with_question(normalized)

    if exploration_score >= 1 and brief_score >= 1 and has_question:
        llm = _classify_with_llm_if_enabled(text, role=role, flow_step=flow_step)
        return llm or "mixed"

    if len(normalized) > 120 and brief_score >= 2:
        return "brief_input"

    if conv_score >= 1 and brief_score >= 1:
        if brief_score >= conv_score + 2:
            return "brief_input"
        if conv_score >= brief_score + 2:
            llm = _classify_with_llm_if_enabled(text, role=role, flow_step=flow_step)
            return llm or "conversation"
        llm = _classify_with_llm_if_enabled(text, role=role, flow_step=flow_step)
        return llm or "mixed"

    if conv_score >= 1 and brief_score == 0:
        return "conversation"

    if brief_score >= 1 and conv_score == 0:
        if has_question and brief_score < 2:
            return "conversation"
        return "brief_input"

    if flow_step in {"organizer_dump", "organizer_clarify", "participant_contribute"}:
        if exploration_score >= 1 and brief_score >= 1 and has_question:
            return "mixed"
        if flow_step == "organizer_clarify" and (brief_score >= 1 or len(normalized) > 15):
            if exploration_score >= 1 and has_question:
                return "mixed"
            return "brief_input"
        if conv_score >= 1 and brief_score == 0:
            return "conversation"
        if brief_score >= 1:
            return "brief_input"
        if len(normalized) > 12:
            if exploration_score >= 1 and has_question:
                return "mixed"
            return "brief_input"

    if conv_score >= 1:
        return "conversation"

    if len(normalized) < 20:
        return "conversation"

    return "brief_input" if brief_score >= 1 else "conversation"


def _classify_with_llm_if_enabled(text: str, *, role: str, flow_step: str) -> Optional[MessageIntent]:
    if not env_flag("USE_LLM_LIVE_RESPONSES"):
        return None
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        return None

    model = os.getenv("LLM_LIVE_MODEL", os.getenv("LLM_PARSER_MODEL", "gpt-4o-mini"))
    system = (
        "Классифицируй реплику пользователя Telegram-бота поездки. "
        "Верни только JSON с ключом intent: "
        "brief_input — факты/пожелания по поездке; "
        "conversation — вопрос/помощь без новых фактов; "
        "mixed — и вопрос/сомнение, и факты в одном сообщении."
    )
    user = f"role={role}\nflow_step={flow_step}\nmessage={text}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    try:
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8")
        content = json.loads(raw)["choices"][0]["message"]["content"]
        parsed = json.loads(content.strip().removeprefix("```json").removesuffix("```"))
        intent = parsed.get("intent")
        if intent in {"brief_input", "conversation", "mixed"}:
            logging.info("Message intent from LLM: %s", intent)
            return intent
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        KeyError,
        ValueError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
    ) as err:
        logging.warning("LLM intent classification failed: %s", err)
    return None


def has_substantive_parsed_fields(parsed: dict) -> bool:
    if not parsed:
        return False
    return any(k != "context_raw" and v not in (None, "", [], {}) for k, v in parsed.items())
