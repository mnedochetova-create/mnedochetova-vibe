"""Видимость полей брифа для участников и текста пересылки."""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Literal, Optional, Set

from env_util import env_flag

Audience = Literal["participant", "share_plain", "organizer"]

FIELD_KEYS = (
    "dates",
    "budget",
    "group",
    "transport",
    "duration",
    "passports",
    "stay",
    "activities",
    "participant_block",
)

FIELD_LABELS_RU: Dict[str, str] = {
    "dates": "даты",
    "budget": "бюджет",
    "group": "состав",
    "transport": "перелёт / транспорт",
    "duration": "длительность",
    "passports": "загранпаспорта / визы",
    "stay": "сценарий и локация",
    "activities": "доп. пожелания",
    "participant_block": "блок вкладов участников",
}

# (паттерны в тексте) -> ключ поля
_VISIBILITY_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    ((r"бюджет", r"₽", r"руб", r"тыс", r"\d+\s*к\b"), "budget"),
    ((r"дат", r"окно", r"период", r"месяц", r"июл", r"август"), "dates"),
    ((r"состав", r"взросл", r"дет", r"реб", r"кто едет", r"групп"), "group"),
    ((r"перел", r"пересад", r"рейс", r"транспорт", r"долет"), "transport"),
    ((r"длительност", r"сколько дней", r"дн[ея]й"), "duration"),
    ((r"загран", r"виз", r"паспорт"), "passports"),
    ((r"сценар", r"локац", r"море", r"пляж", r"гор", r"отель", r"формат"), "stay"),
    ((r"пожелан", r"активност", r"экскурс"), "activities"),
    ((r"вклад участник", r"что добавили участник"), "participant_block"),
)

_HIDE_CUES = (
    r"не\s+показыв",
    r"не\s+видел",
    r"скры",
    r"убери",
    r"без\s+",
    r"исключ",
    r"не\s+надо",
    r"оставлю\s+сам",
    r"только\s+мне",
    r"участник\w*\s+не",
    r"семь[её]\s+без",
)


def _normalized(text: str) -> str:
    return (text or "").strip().lower()


def mentions_hide_intent(text: str) -> bool:
    n = _normalized(text)
    return any(re.search(pat, n, flags=re.IGNORECASE) for pat in _HIDE_CUES)


def parse_visibility_fields_rules(text: str) -> List[str]:
    """Эвристика: какие поля скрыть из реплики организатора."""
    if not mentions_hide_intent(text):
        return []
    n = _normalized(text)
    found: List[str] = []
    for patterns, key in _VISIBILITY_RULES:
        if key in found:
            continue
        if any(re.search(pat, n, flags=re.IGNORECASE) for pat in patterns):
            found.append(key)
    return found


def parse_visibility_fields_llm(text: str) -> Optional[List[str]]:
    if not env_flag("USE_LLM_LIVE_RESPONSES"):
        return None
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.getenv("LLM_LIVE_MODEL", os.getenv("LLM_PARSER_MODEL", "gpt-4o-mini"))
    allowed = ", ".join(FIELD_KEYS)
    system = (
        "Из реплики организатора Telegram-бота поездки извлеки, какие поля брифа "
        f"скрыть для участников и семейной пересылки. Допустимые ключи: {allowed}. "
        'Верни JSON {"hidden_fields": ["budget", ...]} или {"hidden_fields": []} '
        "если запрос не про скрытие полей."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
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
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
        content = json.loads(raw)["choices"][0]["message"]["content"]
        parsed = json.loads(content.strip().removeprefix("```json").removesuffix("```"))
        fields = parsed.get("hidden_fields") or []
        out = [str(f) for f in fields if str(f) in FIELD_KEYS]
        logging.info("Visibility fields from LLM: %s", out)
        return out
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        KeyError,
        ValueError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
    ) as err:
        logging.warning("Visibility LLM parse failed: %s", err)
    return None


def parse_visibility_fields(text: str) -> List[str]:
    llm = parse_visibility_fields_llm(text)
    if llm is not None:
        return llm
    return parse_visibility_fields_rules(text)


def normalize_field_visibility(event: Dict[str, Any]) -> Dict[str, List[str]]:
    raw = event.get("field_visibility")
    if not isinstance(raw, dict):
        raw = {}
    out: Dict[str, List[str]] = {
        "participant": [],
        "share_plain": [],
    }
    for audience in ("participant", "share_plain"):
        items = raw.get(audience) or []
        if isinstance(items, list):
            out[audience] = [str(x) for x in items if str(x) in FIELD_KEYS]
    return out


def get_hidden_fields(event: Optional[Dict[str, Any]], audience: Audience) -> Set[str]:
    if not event or audience == "organizer":
        return set()
    vis = normalize_field_visibility(event)
    return set(vis.get(audience) or [])


def merge_hidden_fields(event: Dict[str, Any], new_fields: List[str]) -> List[str]:
    vis = normalize_field_visibility(event)
    added: List[str] = []
    for key in new_fields:
        if key not in FIELD_KEYS:
            continue
        for aud in ("participant", "share_plain"):
            if key not in vis[aud]:
                vis[aud].append(key)
                added.append(key)
    event["field_visibility"] = vis
    return list(dict.fromkeys(added))


def field_labels_ru(keys: List[str]) -> str:
    labels = [FIELD_LABELS_RU.get(k, k) for k in keys if k in FIELD_KEYS]
    return ", ".join(labels) if labels else "ничего"


def visibility_note_for_event(event: Optional[Dict[str, Any]]) -> str:
    if not event:
        return ""
    hidden = get_hidden_fields(event, "participant")
    if not hidden:
        return ""
    return (
        f"\n\n<i>Для участников скрыто: {field_labels_ru(sorted(hidden))}. "
        "В твоём экране бриф по-прежнему полный.</i>"
    )
