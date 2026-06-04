"""Живые ответы на шум/медиа/помощь: контекст поездок, без изменения брифа."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import dialog_context
import live_response
from input_kind import InputKind

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
CORNER_SYSTEM_FILE = PROMPTS_DIR / "corner_guidance_system_prompt.md"
CORNER_USER_TEMPLATE_FILE = PROMPTS_DIR / "corner_guidance_user_prompt_template.md"

_SYSTEM_CACHE: Optional[str] = None
_USER_TEMPLATE_CACHE: Optional[str] = None


def _load_prompt(path: Path, cache: Optional[str], label: str) -> str:
    if cache is not None:
        return cache
    try:
        return path.read_text(encoding="utf-8")
    except OSError as err:
        logging.warning("Failed to load %s prompt: %s", label, err)
        return ""


def get_corner_system_prompt() -> str:
    global _SYSTEM_CACHE
    _SYSTEM_CACHE = _load_prompt(CORNER_SYSTEM_FILE, _SYSTEM_CACHE, "corner system")
    return _SYSTEM_CACHE


def get_corner_user_template() -> str:
    global _USER_TEMPLATE_CACHE
    _USER_TEMPLATE_CACHE = _load_prompt(
        CORNER_USER_TEMPLATE_FILE, _USER_TEMPLATE_CACHE, "corner user"
    )
    return _USER_TEMPLATE_CACHE


def _as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_corner_user_prompt(context: Dict[str, Any]) -> str:
    template = get_corner_user_template()
    if not template:
        return ""
    replacements = {
        "{{input_kind}}": str(context.get("input_kind", "ack")),
        "{{role}}": str(context.get("role", "organizer")),
        "{{flow_step}}": str(context.get("flow_step", "corner")),
        "{{human_status}}": str(context.get("human_status", "")),
        "{{allowed_next_action}}": str(context.get("allowed_next_action", "none")),
        "{{step_context_human}}": str(context.get("step_context_human", "")),
        "{{dialog_summary}}": str(context.get("dialog_summary", "")),
        "{{last_bot_message}}": str(context.get("last_bot_message", "")),
        "{{trips_json}}": _as_json(context.get("trips_json", [])),
        "{{active_trip_json}}": _as_json(context.get("active_trip_json", {})),
        "{{user_message}}": str(context.get("user_message", "")),
    }
    out = template
    for key, value in replacements.items():
        out = out.replace(key, value)
    return out


def _format_trip_line(trip: Dict[str, Any]) -> str:
    num = trip.get("event_number")
    label = f"#{num}" if isinstance(num, int) else "поездка"
    role = "организатор" if trip.get("role") == "organizer" else "участник"
    return (
        f"{label} ({role}): {trip.get('status_short', 'активно')}, "
        f"шаг — {trip.get('action_short', 'открыть')}"
    )


def build_corner_fallback(
    input_kind: InputKind,
    *,
    trips: List[Dict[str, Any]],
    active_trip: Optional[Dict[str, Any]],
    role: str,
    flow_step: str,
    missing: Optional[List[str]] = None,
) -> str:
    trips = trips or []
    active = active_trip or {}
    top_missing = (missing or [])[:3]

    if input_kind == "media":
        lead = (
            "📎 <b>Не могу прочитать фото или файл</b> в этом чате.\n\n"
            "Выпиши <b>текстом</b> главное: даты, состав, бюджет, куда хотите — одним сообщением."
        )
    elif input_kind == "action_required":
        lead = (
            "👆 <b>Сначала кнопка под прошлым сообщением</b> — "
            "так я пойму, что ты подтверждаешь или хочешь дополнить."
        )
    elif input_kind == "help":
        lead = (
            "Поняла, нужна подсказка.\n\n"
            "Можешь начать с трёх строк: кто едет, когда примерно, бюджет «до …» или «гибко»."
        )
    elif input_kind == "noise":
        lead = "Похоже, это сообщение не про вводные по поездке."
    elif input_kind == "defer":
        lead = (
            "✅ <b>Ок, зафиксировала черновик.</b> Не буду давить на все поля сразу.\n\n"
            "Когда созреешь — дополни одним сообщением или открой поездку в "
            "<b>📂 Мои поездки</b>."
        )
        if active.get("invite_with_gaps"):
            lead += "\n\n<i>Можно пригласить участников уже с черновиком — ссылка ниже.</i>"
    elif input_kind == "autofill_request":
        miss_hint = ""
        if top_missing:
            miss_hint = f"\n\n<b>Сейчас главное:</b> {top_missing[0]}."
        lead = (
            "Я не заполняю бриф за тебя без фактов — так честнее для всей группы."
            f"{miss_hint}\n\n"
            "Могу помочь <b>сформулировать</b> одну строку: кто едет, когда, бюджет «до …» "
            "или «гибко» — скопируй и подправь."
        )
    elif input_kind == "share_visibility_request":
        vis = active.get("field_visibility") or {}
        hidden = vis.get("participant") or []
        if hidden:
            lead = (
                f"Для участников уже скрыто: <b>{field_labels_ru(hidden)}</b>. "
                "Напиши, что ещё убрать, например: «участникам не показывай бюджет»."
            )
        else:
            lead = (
                "Могу скрыть поля в брифе для участников и в тексте для семьи.\n\n"
                "Например: «участникам не показывай бюджет» или «без дат в пересылке». "
                "В твоём экране бриф останется полным."
            )
    else:
        lead = "Поняла."

    parts = [lead]

    if active.get("event_number"):
        num = active["event_number"]
        role_ru = "организатор" if active.get("role") == "organizer" else "участник"
        parts.append(
            f"\nСейчас в фокусе поездка <b>#{num}</b> — ты как <b>{role_ru}</b>."
        )
        if (
            top_missing
            and flow_step in {"organizer_dump", "organizer_clarify"}
            and input_kind not in {"defer", "autofill_request"}
        ):
            miss = "\n".join(f"• {m}" for m in top_missing)
            parts.append(f"\n<b>Не хватает:</b>\n{miss}\n\nМожно одним сообщением.")
        elif active.get("action_short"):
            parts.append(f"\n<b>Следующий шаг:</b> {active['action_short']}.")

    if len(trips) > 1:
        lines = [_format_trip_line(t) for t in trips[:4]]
        parts.append("\n<b>Твои поездки:</b>\n" + "\n".join(f"• {line}" for line in lines))
        parts.append("\nОткрой нужную в <b>📂 Мои поездки</b>.")
    elif not trips:
        parts.append(
            "\nЧтобы начать планирование — <b>✨ Новая поездка</b> "
            "или пришли вводные одним сообщением."
        )
    elif not active.get("event_number") and trips:
        parts.append(f"\n{_format_trip_line(trips[0])}")
        parts.append("\nПродолжить — в <b>📂 Мои поездки</b>.")

    return "".join(parts)


def generate_corner_response(
    context: Dict[str, Any],
    fallback_text: str,
) -> Dict[str, Any]:
    if not live_response.live_responses_enabled():
        return {
            "assistant_text": fallback_text,
            "tone": "neutral",
            "confidence": 1.0,
            "source": "fallback_disabled",
        }
    api_key = __import__("os").getenv("LLM_API_KEY", "").strip()
    if not api_key:
        return {
            "assistant_text": fallback_text,
            "tone": "neutral",
            "confidence": 1.0,
            "source": "fallback_no_key",
        }
    system_prompt = get_corner_system_prompt()
    user_prompt = build_corner_user_prompt(context)
    if not system_prompt or not user_prompt:
        return {
            "assistant_text": fallback_text,
            "tone": "neutral",
            "confidence": 1.0,
            "source": "fallback_no_prompt",
        }

    import os
    import urllib.error
    import urllib.request

    model = os.getenv("LLM_LIVE_MODEL", os.getenv("LLM_PARSER_MODEL", "gpt-4o-mini"))
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.5,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8")
        parsed = json.loads(raw)
        content = parsed["choices"][0]["message"]["content"]
        live = live_response._parse_live_response(content, max_chars=1000)  # noqa: SLF001
        if not live:
            return {
                "assistant_text": fallback_text,
                "tone": "neutral",
                "confidence": 1.0,
                "source": "fallback_invalid_json",
            }
        logging.info("Corner guidance from LLM (model=%s)", model)
        return {**live, "source": "llm"}
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        KeyError,
        ValueError,
        TimeoutError,
        OSError,
        IndexError,
        TypeError,
        json.JSONDecodeError,
    ) as err:
        logging.warning("Corner guidance LLM failed: %s", err)
        return {
            "assistant_text": fallback_text,
            "tone": "neutral",
            "confidence": 1.0,
            "source": "fallback_error",
        }


def corner_text_or_fallback(context: Dict[str, Any], fallback_text: str) -> str:
    result = generate_corner_response(context, fallback_text)
    if str(result.get("source")) != "llm":
        logging.info("Corner guidance fallback (source=%s)", result.get("source"))
    return str(result.get("assistant_text") or fallback_text)
