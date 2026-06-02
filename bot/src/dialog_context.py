"""Контекст диалога для live-ответов: история, шаг, инсайт брифа."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

MAX_DIALOG_TURNS = 6

COMPLETE_VARIANTS_ORGANIZER = (
    "Отлично, базовых данных достаточно — переходим к участникам.",
    "Супер, картина по поездке сложилась. Дальше — подключить семью.",
    "Готово: вводных хватает, можно звать участников.",
)
COMPLETE_VARIANTS_ORGANIZER_CLARIFY = (
    "Спасибо, теперь данных достаточно. Переходим к участникам.",
    "Отлично, дополнила бриф — можно приглашать участников.",
    "Всё ключевое на месте. Следующий шаг — участники.",
)

PARTICIPANT_BRIEF_INTRO_VARIANTS = (
    "Спасибо, добавила твои пожелания — организатор увидит их отдельно.",
    "Приняла твой вклад в бриф, организатору будет видно отдельно.",
    "Зафиксировала твои пожелания без смешения с базой организатора.",
)


def trim_dialog_history(history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    cleaned: List[Dict[str, str]] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        text = str(item.get("text") or "").strip()
        if role in {"user", "assistant"} and text:
            cleaned.append({"role": role, "text": text[:500]})
    return cleaned[-MAX_DIALOG_TURNS:]


def append_dialog_turn(
    history: List[Dict[str, str]],
    *,
    role: str,
    text: str,
) -> List[Dict[str, str]]:
    updated = trim_dialog_history(list(history or []))
    normalized = (text or "").strip()
    if not normalized:
        return updated
    updated.append({"role": role, "text": normalized[:500]})
    return updated[-MAX_DIALOG_TURNS:]


def last_bot_message(history: List[Dict[str, str]]) -> str:
    for item in reversed(trim_dialog_history(history)):
        if item.get("role") == "assistant":
            return str(item.get("text") or "")
    return ""


def build_dialog_summary(history: List[Dict[str, str]]) -> str:
    turns = trim_dialog_history(history)
    if not turns:
        return "Диалог только начинается, предыдущих реплик в сессии нет."
    parts: List[str] = []
    for item in turns[-4:]:
        who = "Пользователь" if item["role"] == "user" else "Бот"
        parts.append(f"{who}: {item['text'][:120]}")
    return " | ".join(parts)


def build_step_context_human(
    *,
    role: str,
    flow_step: str,
    missing: List[str],
) -> str:
    role_ru = "организатор" if role == "organizer" else "участник"
    step_map = {
        "organizer_dump": "организатор отправил первый блок вводных",
        "organizer_clarify": "организатор уточняет бриф",
        "participant_contribute": "участник добавляет личные пожелания",
        "conversation": "свободный диалог, без смены шага сценария",
        "mixed": "смешанная реплика: есть и вопрос, и факты — сначала коротко поддержи, факты уйдут в бриф",
    }
    step_line = step_map.get(flow_step, flow_step)
    if missing:
        top = ", ".join(missing[:3])
        extra = ""
        if len(missing) > 3:
            extra = f" (и ещё {len(missing) - 3})"
        missing_line = f"Не хватает в брифе: {top}{extra}."
    else:
        missing_line = "Критичных пробелов в брифе нет."
    return f"Сейчас: {role_ru}, этап — {step_line}. {missing_line}"


_MISSING_PRIORITY = (
    "Кто едет",
    "Окна дат",
    "Бюджет",
    "Перелёт",
    "Сценарий отдыха",
)


def prioritize_missing(missing: List[str], limit: int = 3) -> List[str]:
    if len(missing) <= limit:
        return list(missing)

    def rank(item: str) -> int:
        for idx, prefix in enumerate(_MISSING_PRIORITY):
            if item.startswith(prefix):
                return idx
        return len(_MISSING_PRIORITY)

    ordered = sorted(missing, key=rank)
    return ordered[:limit]


def pick_variant(chat_id: int, variants: tuple[str, ...]) -> str:
    if not variants:
        return ""
    return variants[chat_id % len(variants)]


def brief_insight_line(brief: Dict[str, Any]) -> str:
    if not brief:
        return ""
    parts: List[str] = []
    adults = brief.get("adults")
    kids = brief.get("kids_count") or brief.get("kids")
    if adults is not None:
        if kids:
            parts.append(f"семья {adults}+{kids}")
        else:
            parts.append(f"{adults} взрослых")
    for pref in brief.get("activity_preferences") or []:
        text = str(pref)
        if text.lower().startswith("предпочтение по направлению:"):
            parts.append(text.split(":", 1)[1].strip())
            break
    if not parts:
        se = brief.get("stay_experience")
        if isinstance(se, dict) and se.get("setting"):
            parts.append(str(se["setting"][0]))
    period = brief.get("date_range_raw")
    if not period and brief.get("months"):
        period = ", ".join(str(m) for m in brief["months"][:2])
    if period:
        parts.append(str(period))
    if brief.get("budget_rub_max"):
        if brief.get("budget_rub_min"):
            parts.append(
                f"бюджет {brief['budget_rub_min']:,}–{brief['budget_rub_max']:,} ₽".replace(",", " ")
            )
        else:
            parts.append(f"бюджет до {brief['budget_rub_max']:,} ₽".replace(",", " "))
    elif brief.get("budget_flexible"):
        parts.append("бюджет гибкий")
    if not parts:
        return ""
    deduped: List[str] = []
    for item in parts[:5]:
        if item not in deduped:
            deduped.append(item)
    return "Похоже на поездку: " + ", ".join(deduped) + "."
