import asyncio
import html
import logging
import os
import secrets
import time
from typing import Optional, Dict, Any, List

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    BotCommand,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from dotenv import load_dotenv

import brief_parser
import brief_pipeline
import live_response
from interaction_log import flush_session_milestone, log_parse_result, log_session_action
from storage import load_events_from_file, save_events_to_file


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


class FlowState(StatesGroup):
    organizer_dump = State()
    organizer_clarify = State()
    participant_contribute = State()
    participant_confirm = State()

BOT_USERNAME: Optional[str] = None

# Runtime storage (persisted to file).
# event_code -> event dict
EVENTS: Dict[str, Dict[str, Any]] = {}


def new_event_code() -> str:
    # Short human-friendly code
    return secrets.token_hex(3)


def now_ts() -> int:
    return int(time.time())


def chat_key(chat_id: Any) -> str:
    return str(chat_id)


def next_event_number() -> int:
    max_number = 0
    for event in EVENTS.values():
        value = event.get("event_number")
        if isinstance(value, int) and value > max_number:
            max_number = value
    return max_number + 1


def touch_event(event: Dict[str, Any]) -> None:
    event["updated_at"] = now_ts()


def get_brief_parser_prompt() -> str:
    return brief_parser.get_brief_parser_prompt()


def parse_brief_with_llm(text: str) -> Dict[str, Any]:
    return brief_parser.parse_brief_with_llm(text)


def load_events() -> None:
    global EVENTS
    EVENTS = load_events_from_file()


def save_events() -> None:
    save_events_to_file(EVENTS)


def normalize_text(value: str) -> str:
    text = (value or "").strip().lower()
    for token in ["ℹ️", "ℹ", "🆘", "➕", "✨", "📂", "🧭", "📤", "🔗", "✉️"]:
        text = text.replace(token, "")
    return " ".join(text.split())


def is_capabilities_text(value: str) -> bool:
    normalized = normalize_text(value)
    return normalized in {"как работает", "что умеет бот", "как это работает"}


def is_help_text(value: str) -> bool:
    return normalize_text(value) == "помощь"


def is_create_event_text(value: str) -> bool:
    normalized = normalize_text(value)
    return normalized in {"новая поездка", "создать поездку", "создать событие"}


def is_my_events_text(value: str) -> bool:
    normalized = normalize_text(value)
    return normalized in {"мои поездки", "мои события"}


def is_current_trip_text(value: str) -> bool:
    return normalize_text(value) == "текущая поездка"


def build_invite_share_text(invite_link: str) -> str:
    return (
        "Привет! Я собираю вводные по нашей поездке.\n"
        "Перейди по ссылке и напиши, что тебе важно: даты, бюджет, перелёт, отель, климат, "
        "активности или ограничения.\n"
        "Бот добавит твои пожелания в общий бриф:\n"
        f"{invite_link}"
    )


def build_brief_share_text(brief_plain: str) -> str:
    body = brief_plain.strip() or "— сводка уточняется —"
    return (
        "Привет! Вот сводка по нашей поездке — собрали в MyTravel.Lab.\n\n"
        f"{body}\n\n"
        "Если что-то нужно уточнить — напиши мне (организатору)."
    )


def participants_all_confirmed(event: Dict[str, Any]) -> bool:
    participants = event.get("participants") or {}
    if not participants:
        return False
    updates = event.get("participant_updates") or {}
    for participant_id in participants:
        row = updates.get(participant_id) or participants.get(participant_id) or {}
        if not row.get("confirmed"):
            return False
    return True


def can_offer_brief_confirm(event: Dict[str, Any]) -> bool:
    if event.get("organizer_brief_confirmed_at"):
        return False
    brief = event.get("brief") or {}
    if missing_brief_fields(brief):
        return False
    participants = event.get("participants") or {}
    if not participants:
        return True
    return participants_all_confirmed(event)


def format_brief_plain_for_share(brief: Dict[str, Any], event_number: Optional[int] = None) -> str:
    lines: List[str] = []
    label = f"Поездка #{event_number}" if isinstance(event_number, int) else "Поездка"
    lines.append(label)

    if brief.get("date_range_raw"):
        lines.append(f"Даты: {brief['date_range_raw']}")
    elif brief.get("months"):
        lines.append("Даты: " + ", ".join(str(m) for m in brief["months"]))

    if brief.get("budget_rub_max"):
        lines.append(f"Бюджет: до {brief['budget_rub_max']:,} ₽".replace(",", " "))

    group_parts: List[str] = []
    if brief.get("adults"):
        group_parts.append(f"{brief['adults']} взрослых")
    if brief.get("kids_count"):
        group_parts.append(f"{brief['kids_count']} детей")
    if group_parts:
        lines.append("Состав: " + ", ".join(group_parts))

    if brief.get("flight_hours_max"):
        lines.append(f"Перелёт: до {brief['flight_hours_max']} ч.")
    elif brief.get("flight_hours_unrestricted"):
        lines.append("Перелёт: без ограничений по длительности")
    elif brief.get("transfers_allowed") is True:
        lines.append("Перелёт: пересадки допустимы")
    elif brief.get("transfers_allowed") is False:
        lines.append("Перелёт: желательно без пересадок")

    if brief.get("trip_duration_days_raw"):
        lines.append(f"Длительность: {brief['trip_duration_days_raw']}")

    if "visa_required" in brief:
        lines.append("Визы: " + ("нужна" if brief["visa_required"] else "без визы"))

    if brief.get("passports_status"):
        lines.append(f"Загранпаспорта: {brief['passports_status']}")

    if brief.get("climate"):
        lines.append(f"Климат: {brief['climate']}")

    if brief.get("trip_type"):
        lines.append(f"Формат: {brief['trip_type']}")

    activity = brief.get("activity_preferences") or []
    if activity:
        lines.append("Пожелания: " + "; ".join(str(a) for a in activity))

    participant_preferences = brief.get("participant_preferences") or {}
    if participant_preferences:
        lines.append("")
        lines.append("Участники:")
        for name, prefs in participant_preferences.items():
            chunk: List[str] = []
            if prefs.get("budget_rub_max"):
                chunk.append(f"бюджет до {prefs['budget_rub_max']:,} ₽".replace(",", " "))
            if prefs.get("date_range_raw"):
                chunk.append(f"даты {prefs['date_range_raw']}")
            if prefs.get("climate"):
                chunk.append(str(prefs["climate"]))
            if prefs.get("context_raw") and not chunk:
                chunk.append(str(prefs["context_raw"])[:200])
            if chunk:
                lines.append(f"— {name}: " + ", ".join(chunk))

    return "\n".join(lines)


BRIEF_READY_TO_CONFIRM_TEXT = (
    "✅ <b>Бриф выглядит достаточно полным</b>\n\n"
    "Проверь, что всё верно: состав, даты, бюджет, пожелания участников и ограничения.\n\n"
    "Если всё ок — подтверди бриф. После этого его удобно переслать семье, турагенту или партнёру."
)

BRIEF_CONFIRMED_TEXT = (
    "🎉 <b>Готово — бриф поездки собран</b>\n\n"
    "Теперь у тебя единая картина: кто едет, когда, какой бюджет, что важно участникам "
    "и какие ограничения учесть.\n\n"
    "Можешь переслать бриф в чат, отправить турагенту или использовать как основу для подбора вариантов."
)

BRIEF_SHARE_INTRO_TEXT = (
    "📤 <b>Поделиться брифом</b>\n\n"
    "Я подготовила текст, который удобно переслать в общий чат или личку — со всей сводкой по поездке."
)

BRIEF_SHARE_DONE_TEXT = (
    "Отлично. Если появятся новые пожелания — открой поездку через "
    "<b>🧭 Текущая поездка</b> или создай новую."
)

PARTICIPANT_THANKS_TEXT = (
    "✅ <b>Спасибо, я зафиксировала твои пожелания</b>\n\n"
    "Организатор увидит их в общем брифе. Если захочешь что-то добавить — "
    "напиши одним сообщением в этот чат."
)


def get_latest_event_for_chat(chat_id: int) -> Optional[tuple[str, Dict[str, Any], str]]:
    organizer_hits: list[tuple[str, Dict[str, Any]]] = []
    participant_hits: list[tuple[str, Dict[str, Any]]] = []
    for code, event in EVENTS.items():
        if event.get("organizer_chat_id") == chat_id:
            organizer_hits.append((code, event))
            continue
        participants = event.get("participants") or {}
        if str(chat_id) in participants:
            participant_hits.append((code, event))

    def pick_latest(items: list[tuple[str, Dict[str, Any]]]) -> Optional[tuple[str, Dict[str, Any]]]:
        if not items:
            return None
        items.sort(key=lambda x: x[1].get("created_at", 0), reverse=True)
        return items[0]

    latest_organizer = pick_latest(organizer_hits)
    if latest_organizer:
        code, event = latest_organizer
        return code, event, "organizer"

    latest_participant = pick_latest(participant_hits)
    if latest_participant:
        code, event = latest_participant
        return code, event, "participant"

    return None


async def handle_menu_shortcuts(message: Message) -> bool:
    if is_current_trip_text(message.text or ""):
        await current_trip_handler(message, None)
        return True
    if is_my_events_text(message.text or ""):
        await my_events_handler(message, None)
        return True
    if is_capabilities_text(message.text or ""):
        await capabilities_handler(message)
        return True
    if is_help_text(message.text or ""):
        await help_handler(message)
        return True
    return False


def extract_brief_rule_based(text: str) -> Dict[str, Any]:
    return brief_parser.extract_brief_rule_based(text)


def extract_brief_from_text(text: str) -> Dict[str, Any]:
    return brief_parser.extract_brief_from_text(text)


async def emit_parse_log(
    bot: Bot,
    message: Message,
    *,
    role: str,
    event_number: Optional[int],
    step_label: str,
    user_text: str,
    brief: Dict[str, Any],
    missing: List[str],
    brief_html: str,
) -> None:
    await log_parse_result(
        bot,
        message,
        role=role,
        event_number=event_number,
        step_label=step_label,
        user_text=user_text,
        brief_html=brief_html,
        missing=missing,
        merged_brief=brief,
        parser_mode=brief_parser.get_last_parser_mode(),
    )


def merge_brief(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    return brief_parser.merge_brief(base, incoming)


def merge_participant_into_brief(
    base: Dict[str, Any],
    incoming: Dict[str, Any],
    participant_name: str,
) -> Dict[str, Any]:
    return brief_parser.merge_participant_into_brief(base, incoming, participant_name)


def missing_brief_fields(brief: Dict[str, Any]) -> list[str]:
    return brief_parser.missing_brief_fields(brief)


def parser_confidence_hint() -> float:
    mode = brief_parser.get_last_parser_mode()
    if mode == "llm+rules":
        return 0.86
    if mode == "llm_fallback":
        return 0.68
    return 0.72


def build_live_prompt_context(
    *,
    role: str,
    flow_step: str,
    human_status: str,
    allowed_next_action: str,
    last_system_action: str,
    brief: Dict[str, Any],
    missing: List[str],
    parser_result: Dict[str, Any],
    conflicts: List[str],
    user_message: str,
) -> Dict[str, Any]:
    return {
        "role": role,
        "flow_step": flow_step,
        "human_status": human_status,
        "allowed_next_action": allowed_next_action,
        "last_system_action": last_system_action,
        "brief_json": brief,
        "missing_fields_json": missing,
        "parser_result_json": parser_result,
        "conflicts_json": conflicts,
        "recent_messages_json": [{"role": "user", "text": user_message}],
        "user_message": user_message,
    }


def live_text_or_fallback(context: Dict[str, Any], fallback_text: str) -> str:
    result = live_response.generate_live_response(context, fallback_text)
    return str(result.get("assistant_text") or fallback_text)


def format_brief_unified(
    brief: Dict[str, Any],
    event_number: Optional[int],
    title: str,
    subtitle: str,
) -> str:
    def esc(value: Any) -> str:
        return html.escape(str(value))

    def humanize_climate(value: str) -> str:
        mapping = {
            "море/пляж": "морское направление и пляжный отдых",
            "горы": "горное направление",
        }
        return mapping.get(value, value)

    def split_activity_preferences(items: List[str]) -> tuple[List[str], List[str]]:
        directions: List[str] = []
        other: List[str] = []
        for raw in items:
            text = str(raw).strip()
            low = text.lower()
            if low.startswith("предпочтение по направлению:"):
                directions.append(text.split(":", 1)[1].strip())
            else:
                other.append(text)
        return directions, other

    lines: list[str] = []
    lines.append(title)
    event_label = f"#{event_number}" if isinstance(event_number, int) else "без номера"
    lines.append(f"Событие: <b>{event_label}</b>")
    lines.append(subtitle)

    def format_kids(count: int) -> str:
        # 1 ребенок, 2 ребенка, 5 детей
        n = abs(count) % 100
        n1 = n % 10
        if 11 <= n <= 14:
            word = "детей"
        elif n1 == 1:
            word = "ребенок"
        elif 2 <= n1 <= 4:
            word = "ребенка"
        else:
            word = "детей"
        return f"{count} {word}"

    core_facts: List[str] = []
    style_facts: List[str] = []
    if brief.get("date_range_raw"):
        dates_value = f"<code>{esc(brief['date_range_raw'])}</code>"
    elif brief.get("months"):
        dates_value = ", ".join(esc(item) for item in brief["months"])
    else:
        dates_value = "—"
    core_facts.append(f"📅 <b>Даты:</b> {dates_value}")

    budget_value = (
        f"до {brief['budget_rub_max']:,} ₽".replace(",", " ")
        if brief.get("budget_rub_max")
        else "—"
    )
    core_facts.append(f"💰 <b>Бюджет:</b> {budget_value}")

    if brief.get("adults") or brief.get("kids_count"):
        parts: list[str] = []
        if brief.get("adults"):
            parts.append(f"{brief['adults']} взрослых")
        if brief.get("kids_count"):
            parts.append(format_kids(int(brief["kids_count"])))
        group_value = ", ".join(parts)
    else:
        group_value = "—"
    core_facts.append("👨‍👩‍👧‍👦 <b>Состав:</b> " + group_value)

    if brief.get("flight_hours_max"):
        flight_value = f"до {esc(brief['flight_hours_max'])} ч."
    elif brief.get("flight_hours_unrestricted"):
        flight_value = "ограничений по длительности перелёта нет"
    elif brief.get("transfers_allowed") is True:
        flight_value = "пересадки допустимы"
    elif brief.get("transfers_allowed") is False:
        flight_value = "желательно без пересадок"
    else:
        flight_value = "—"
    core_facts.append(f"✈️ <b>Перелёт:</b> {flight_value}")
    duration_value = esc(brief["trip_duration_days_raw"]) if brief.get("trip_duration_days_raw") else "—"
    core_facts.append(f"⏳ <b>Длительность:</b> {duration_value}")

    if "visa_required" in brief:
        visa_value = "нужна" if brief["visa_required"] else "без визы"
    else:
        visa_value = "—"
    core_facts.append(f"🛂 <b>Визы:</b> {visa_value}")

    passports_value = esc(brief["passports_status"]) if brief.get("passports_status") else "—"
    core_facts.append(f"🛃 <b>Загранпаспорта:</b> {passports_value}")

    climate_value = esc(humanize_climate(brief["climate"])) if brief.get("climate") else "—"
    style_facts.append(f"🌤 <b>Климат и локация:</b> {climate_value}")

    trip_type_value = esc(brief["trip_type"]) if brief.get("trip_type") else "—"
    style_facts.append(f"🏝 <b>Формат отдыха:</b> {trip_type_value}")

    directions, extra_activity = split_activity_preferences(brief.get("activity_preferences") or [])
    direction_value = ", ".join(esc(item) for item in directions) if directions else "—"
    style_facts.append(f"🧭 <b>Предпочтение по направлению:</b> {direction_value}")

    extra_value = ", ".join(esc(item) for item in extra_activity) if extra_activity else "—"
    style_facts.append(f"🧩 <b>Дополнительные пожелания:</b> {extra_value}")

    lines.append("\n🧱 <b>Базовые параметры поездки</b>")
    lines.extend([f"• {f}" for f in core_facts])
    lines.append("\n🎯 <b>Пожелания по формату поездки</b>")
    lines.extend([f"• {f}" for f in style_facts])

    participant_preferences = brief.get("participant_preferences") or {}
    if participant_preferences:
        lines.append("\n👤 <b>Что добавили участники</b>")
        for name, prefs in participant_preferences.items():
            row: list[str] = []
            if prefs.get("budget_rub_max"):
                row.append(f"бюджет: до {prefs['budget_rub_max']:,} ₽".replace(",", " "))
            if prefs.get("date_range_raw"):
                row.append(f"даты: {esc(prefs['date_range_raw'])}")
            elif prefs.get("months"):
                row.append("даты: " + ", ".join(esc(item) for item in prefs["months"]))
            if prefs.get("flight_hours_max"):
                row.append(f"перелёт: до {esc(prefs['flight_hours_max'])} ч.")
            elif prefs.get("flight_hours_unrestricted"):
                row.append("перелёт: ограничений по длительности нет")
            elif prefs.get("transfers_allowed") is True:
                row.append("перелёт: пересадки допустимы")
            elif prefs.get("transfers_allowed") is False:
                row.append("перелёт: без пересадок")
            if "visa_required" in prefs:
                row.append("визы: " + ("нужна" if prefs["visa_required"] else "без визы"))
            if prefs.get("passports_status"):
                row.append("загранпаспорта: " + esc(prefs["passports_status"]))
            if prefs.get("climate"):
                row.append("климат и локация: " + esc(humanize_climate(prefs["climate"])))
            if prefs.get("trip_type"):
                row.append("формат отдыха: " + esc(prefs["trip_type"]))
            if prefs.get("activity_preferences"):
                row.append("доп. пожелания: " + ", ".join(esc(item) for item in prefs["activity_preferences"]))
            if prefs.get("constraints_notes"):
                row.append("ограничения: " + ", ".join(esc(item) for item in prefs["constraints_notes"]))
            if not row and prefs.get("context_raw"):
                row.append("свободное описание: " + esc(prefs["context_raw"]))
            if row:
                lines.append(f"• <b>{esc(name)}</b>: " + " · ".join(row))

    return "\n".join(lines)


def format_brief_update_message(brief: Dict[str, Any], event_number: Optional[int] = None) -> str:
    return format_brief_unified(
        brief=brief,
        event_number=event_number,
        title="✨ <b>Бриф поездки обновлён</b>",
        subtitle="Собрала актуальную картину по событию.",
    )


def format_brief_for_participant(brief: Dict[str, Any], event_number: Optional[int] = None) -> str:
    return format_brief_unified(
        brief=brief,
        event_number=event_number,
        title="📌 <b>Актуальный бриф события</b>",
        subtitle="Вот что уже согласовано на данный момент.",
    )


def participant_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить бриф", callback_data="participant:confirm")],
            [InlineKeyboardButton(text="✏️ Дополнить ещё", callback_data="participant:edit")],
        ]
    )


def welcome_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✨ Создать поездку", callback_data="event:create")],
            [InlineKeyboardButton(text="ℹ️ Как это работает", callback_data="event:how")],
        ]
    )


def organizer_next_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✨ Создать поездку", callback_data="event:create")],
        ]
    )


def invite_ready_keyboard(event: Optional[Dict[str, Any]] = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📤 Поделиться приглашением", callback_data="event:invite_share")],
        [InlineKeyboardButton(text="🔗 Показать ссылку", callback_data="event:invite_link")],
        [InlineKeyboardButton(text="✅ Я отправила ссылку", callback_data="event:invite_sent")],
    ]
    if event and can_offer_brief_confirm(event):
        rows.append(
            [InlineKeyboardButton(text="✅ Подтвердить бриф", callback_data="brief:confirm_prep")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def brief_ready_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить бриф", callback_data="brief:confirm")],
            [InlineKeyboardButton(text="✏️ Дополнить ещё", callback_data="brief:edit")],
            [InlineKeyboardButton(text="📌 Показать бриф", callback_data="event:show_brief")],
        ]
    )


def brief_confirmed_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться брифом", callback_data="brief:share")],
            [InlineKeyboardButton(text="📋 Текст для пересылки", callback_data="brief:share_text")],
            [InlineKeyboardButton(text="📌 Посмотреть бриф", callback_data="event:show_brief")],
            [InlineKeyboardButton(text="✨ Новая поездка", callback_data="event:create")],
        ]
    )


def brief_share_intro_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Показать текст для пересылки", callback_data="brief:share_text")],
            [InlineKeyboardButton(text="📌 Вернуться к брифу", callback_data="event:show_brief")],
        ]
    )


def brief_after_share_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я отправила бриф", callback_data="brief:share_done")],
            [InlineKeyboardButton(text="📌 Вернуться к брифу", callback_data="event:show_brief")],
        ]
    )


def brief_share_done_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📌 Посмотреть бриф", callback_data="event:show_brief")],
            [InlineKeyboardButton(text="✨ Новая поездка", callback_data="event:create")],
        ]
    )


def invite_after_share_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я отправила участникам", callback_data="event:invite_done")],
            [InlineKeyboardButton(text="📌 Вернуться к брифу", callback_data="event:show_brief")],
        ]
    )


def invite_waiting_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📌 Показать бриф", callback_data="event:show_brief")],
            [InlineKeyboardButton(text="📤 Отправить ссылку ещё раз", callback_data="event:invite_share")],
        ]
    )


def my_events_keyboard(events: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = []
    for item in events[:10]:
        role_icon = "👑" if item["role"] == "organizer" else "👤"
        event_num = item.get("event_number", "—")
        status_icon = item.get("status_icon", "•")
        status_short = item.get("status_short", "событие")
        action_short = item.get("action_short", "открыть")
        text = f"{role_icon} #{event_num} · {status_icon} {status_short} · {action_short}"
        if len(text) > 64:
            text = text[:61] + "..."
        rows.append(
            [
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"event:open:{item['code']}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧭 Текущая поездка")],
            [KeyboardButton(text="📂 Мои поездки"), KeyboardButton(text="✨ Новая поездка")],
            [KeyboardButton(text="ℹ️ Как работает")],
        ],
        resize_keyboard=True,
    )


def help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Продолжить сценарий", callback_data="help:continue")],
            [InlineKeyboardButton(text="📝 Как написать вводные", callback_data="help:parser")],
            [InlineKeyboardButton(text="❓ Почему нужно уточнение", callback_data="help:clarify")],
            [InlineKeyboardButton(text="🔗 Проблема со ссылкой", callback_data="help:link")],
            [InlineKeyboardButton(text="📨 Сообщить о проблеме", callback_data="help:report")],
        ]
    )


def context_snapshot(chat_id: int, fsm_state: Optional[str]) -> Dict[str, Any]:
    recovered = get_latest_event_for_chat(chat_id)
    if not recovered:
        return {
            "has_event": False,
            "state": fsm_state or "не определено",
        }
    event_code, event, role = recovered
    return {
        "has_event": True,
        "event_code": event_code,
        "event_number": event.get("event_number"),
        "role": role,
        "state": fsm_state or "не определено",
        "invite_ready": bool(event.get("invite_link")),
        "missing_fields": missing_brief_fields(event.get("brief") or {}),
    }


async def start_handler(message: Message, state: Optional[FSMContext] = None) -> None:
    logging.info("Received /start from chat_id=%s", message.chat.id)
    if state is not None:
        await state.update_data(role="organizer")
    await message.answer(
        "👋 <b>Привет! Я помогу собрать вводные по поездке в единый бриф</b> — даты, бюджет, состав, пожелания участников и спорные моменты — без хаоса в переписке.\n\n"
        "⚙️ <b>Как это работает</b>\n"
        "1) ты создаёшь поездку и отправляешь вводные одним сообщением\n"
        "2) участники подключаются по ссылке и добавляют свои пожелания\n"
        "3) я собираю всё в одну картину и подсвечиваю расхождения.\n\n"
        "👑 <b>Твоя роль — организатор</b>\n"
        "Организатор задаёт базовые параметры и приглашает участников.",
        reply_markup=welcome_keyboard(),
    )
    await log_session_action(message.bot, message, "/start", role="organizer")


async def help_handler(message: Message, state: Optional[FSMContext] = None) -> None:
    logging.info("Received /help from chat_id=%s", message.chat.id)
    fsm_state = await state.get_state() if state is not None else None
    snap = context_snapshot(message.chat.id, fsm_state)
    if snap.get("has_event"):
        event_number = snap.get("event_number")
        event_label = f"#{event_number}" if isinstance(event_number, int) else "без номера"
        role_label = "организатор" if snap.get("role") == "organizer" else "участник"
        context_block = (
            "🧭 <b>Твой контекст</b>\n"
            f"• Поездка: <b>{event_label}</b>\n"
            f"• Роль: <b>{role_label}</b>\n"
            f"• Этап: <b>{html.escape(str(snap.get('state') or 'не определено'))}</b>"
        )
    else:
        context_block = (
            "🧭 <b>Твой контекст</b>\n"
            f"• Этап: <b>{html.escape(str(snap.get('state') or 'не определено'))}</b>\n"
            "• Активная поездка пока не найдена."
        )

    await message.answer(
        "🆘 <b>Помощь</b>\n"
        "Выбери, с чем помочь: продолжить сценарий, разобраться с вводными или решить проблему со ссылкой.\n\n"
        f"{context_block}",
        reply_markup=help_keyboard(),
    )
    await log_session_action(message.bot, message, "помощь")


async def capabilities_handler(message: Message) -> None:
    logging.info("Capabilities requested by chat_id=%s", message.chat.id)
    await message.answer(
        "Я помогаю группе договориться без хаоса в переписке: собираю вводные в единый бриф и показываю общую картину.\n\n"
        "Сейчас я умею:\n"
        "1) принять вводные от организатора одним сообщением и уточнить только недостающее\n"
        "2) подключить участников по ссылке и собрать их пожелания\n"
        "3) собрать общую сводку и подсветить, где ожидания расходятся\n"
        "4) сохранить прогресс поездки, чтобы ты мог вернуться к ней позже.\n\n"
        "Этап рекомендаций по направлениям — следующий шаг развития.",
        reply_markup=main_menu_keyboard(),
    )
    await log_session_action(message.bot, message, "что умеет бот")


def _latest_event_activity_ts(event: Dict[str, Any]) -> int:
    ts = int(event.get("updated_at", event.get("created_at", 0)) or 0)
    participants = event.get("participants") or {}
    for row in participants.values():
        ts = max(ts, int((row or {}).get("updated_at", 0) or 0))
    updates = event.get("participant_updates") or {}
    for row in updates.values():
        ts = max(ts, int((row or {}).get("updated_at", 0) or 0))
        ts = max(ts, int((row or {}).get("confirmed_at", 0) or 0))
    return ts


def _event_status_info(event: Dict[str, Any]) -> Dict[str, str]:
    if event.get("archived_at"):
        return {"key": "archived", "icon": "🗄", "short": "архив"}
    if event.get("organizer_brief_confirmed_at") or event.get("completed_at"):
        return {"key": "completed", "icon": "✅", "short": "бриф подтверждён"}
    missing = missing_brief_fields(event.get("brief") or {})
    if missing:
        return {"key": "needs_clarification", "icon": "🧩", "short": "нужны уточнения"}
    participants = event.get("participants") or {}
    if participants:
        confirmed = sum(1 for row in participants.values() if (row or {}).get("confirmed"))
        if confirmed < len(participants):
            return {"key": "waiting_participants", "icon": "⏳", "short": "ждем участников"}
    return {"key": "active", "icon": "🟢", "short": "активно"}


def _event_action_for_chat(event: Dict[str, Any], role: str, chat_id: int) -> str:
    brief = event.get("brief") or {}
    missing = missing_brief_fields(brief)
    participants = event.get("participants") or {}
    if role == "organizer":
        if missing:
            return f"уточнить: {len(missing)}"
        if not participants:
            return "пригласить"
        confirmed = sum(1 for row in participants.values() if (row or {}).get("confirmed"))
        if confirmed < len(participants):
            return f"ответили: {confirmed}/{len(participants)}"
        return "готово к следующему"

    update = (event.get("participant_updates") or {}).get(str(chat_id), {})
    if not update:
        return "добавить пожелания"
    if not update.get("confirmed"):
        return "подтвердить бриф"
    return "ожидать обновлений"


def _build_my_event_item(code: str, event: Dict[str, Any], role: str, chat_id: int) -> Dict[str, Any]:
    status = _event_status_info(event)
    return {
        "code": code,
        "event_number": event.get("event_number"),
        "role": role,
        "status_icon": status["icon"],
        "status_short": status["short"],
        "action_short": _event_action_for_chat(event, role, chat_id),
        "updated_at": _latest_event_activity_ts(event),
    }


def _action_priority(action_short: str) -> int:
    if action_short.startswith("уточнить:"):
        return 0
    if action_short in {"добавить пожелания", "подтвердить бриф", "пригласить"}:
        return 1
    if action_short.startswith("ответили:"):
        return 2
    if action_short == "готово к следующему":
        return 3
    return 4


async def my_events_handler(message: Message, state: Optional[FSMContext]) -> None:
    chat_id = message.chat.id
    items: List[Dict[str, Any]] = []
    for code, event in EVENTS.items():
        participants = event.get("participants") or {}
        if event.get("organizer_chat_id") == chat_id:
            items.append(_build_my_event_item(code, event, "organizer", chat_id))
        elif str(chat_id) in participants:
            items.append(_build_my_event_item(code, event, "participant", chat_id))

    if not items:
        await message.answer(
            "У вас пока нет сохранённых событий.\n"
            "Создайте новое событие кнопкой «✨ Создать событие».",
            reply_markup=main_menu_keyboard(),
        )
        return

    items.sort(
        key=lambda x: (
            -int(x.get("updated_at", 0) or 0),
            _action_priority(str(x.get("action_short") or "")),
        )
    )
    await message.answer(
        "📂 <b>Мои поездки</b>\n"
        "Актуальные поездки с ролью, статусом и следующим шагом.\n"
        "Выбери поездку, чтобы продолжить:",
        reply_markup=my_events_keyboard(items),
    )
    await log_session_action(message.bot, message, "мои события")


async def new_event_handler(message: Message, state: FSMContext) -> None:
    logging.info("New event requested by chat_id=%s", message.chat.id)
    await state.update_data(organizer_chat_id=message.chat.id)
    await state.set_state(FlowState.organizer_dump)
    event_code = new_event_code()
    event_number = next_event_number()
    EVENTS[event_code] = {
        "code": event_code,
        "event_number": event_number,
        "created_at": now_ts(),
        "updated_at": now_ts(),
        "organizer_chat_id": message.chat.id,
        "organizer_dump": None,
        "participants": {},
        "invite_link": None,
    }
    await state.update_data(event_code=event_code)

    if BOT_USERNAME:
        invite_link = f"https://t.me/{BOT_USERNAME}?start=join_{event_code}"
    else:
        invite_link = None

    EVENTS[event_code]["invite_link"] = invite_link
    touch_event(EVENTS[event_code])
    save_events()

    await message.answer(
        "✅ <b>Поездка создана</b>\n"
        f"Номер: <b>#{event_number}</b>\n\n"
        "Напиши вводные одним сообщением — я разложу их в понятный бриф.\n\n"
        "📝 <b>Пример</b>\n"
        "«2 взрослых + ребёнок 6 лет, июль/август, море, бюджет до 250к, перелёт до 5 часов, без визы»",
        reply_markup=main_menu_keyboard(),
    )
    await log_session_action(
        message.bot,
        message,
        "создание события",
        role="organizer",
        event_number=event_number,
    )


async def send_next_step_after_brief(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    event_code = data.get("event_code")
    event = EVENTS.get(event_code) if event_code else None

    await message.answer(
        "✨ <b>Базовый бриф уже собран</b>\n"
        "Теперь можно подключить участников — они добавят свои пожелания, а я соберу всё в одну картину.\n\n"
        "🔗 <b>Готово — ссылка для участников создана</b>\n"
        "Теперь не нужно собирать пожелания вручную в чате: участники перейдут по ссылке, напишут вводные, "
        "а я добавлю их в общий бриф и подсвечу расхождения.",
        reply_markup=invite_ready_keyboard(event),
    )
    await log_session_action(
        message.bot,
        message,
        "показ приглашения",
        role="organizer",
        event_number=event.get("event_number") if event else None,
    )
    await flush_session_milestone(message.bot, message, "invite_shown")


async def send_next_step_after_brief_by_event(message: Message, event_code: str) -> None:
    event = EVENTS.get(event_code) if event_code else None
    await message.answer(
        "✨ <b>Базовый бриф уже собран</b>\n"
        "Теперь можно подключить участников — они добавят свои пожелания, а я соберу всё в одну картину.\n\n"
        "🔗 <b>Готово — ссылка для участников создана</b>\n"
        "Теперь не нужно собирать пожелания вручную в чате: участники перейдут по ссылке, напишут вводные, "
        "а я добавлю их в общий бриф и подсвечу расхождения.",
        reply_markup=invite_ready_keyboard(event),
    )
    await log_session_action(
        message.bot,
        message,
        "показ приглашения",
        role="organizer",
        event_number=event.get("event_number") if event else None,
    )
    await flush_session_milestone(message.bot, message, "invite_shown")


async def event_create_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    logging.info("Event create clicked chat_id=%s", callback.message.chat.id)
    await callback.answer()
    await new_event_handler(callback.message, state)


async def event_open_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = callback.data or ""
    event_code = data.removeprefix("event:open:")
    event = EVENTS.get(event_code)
    if not event:
        await callback.message.answer("Событие не найдено. Возможно, оно было удалено.")
        return

    chat_id = callback.message.chat.id
    participants = event.get("participants") or {}
    is_organizer = event.get("organizer_chat_id") == chat_id
    is_participant = str(chat_id) in participants

    if not is_organizer and not is_participant:
        await callback.message.answer("У вас нет доступа к этому событию.")
        return

    brief = event.get("brief") or {}
    event_number = event.get("event_number")
    if is_organizer:
        await state.update_data(role="organizer", event_code=event_code, brief=brief)
        await state.set_state(FlowState.organizer_clarify)
        await callback.message.answer(
            f"👑 Ты снова в поездке <b>#{event_number if isinstance(event_number, int) else html.escape(event_code)}</b> как организатор.\n\n"
            f"{format_brief_update_message(brief, event_number=event_number)}\n\n"
            "Продолжай уточнения одним сообщением.",
            reply_markup=main_menu_keyboard(),
        )
        return

    participant_name = (
        callback.from_user.full_name if callback.from_user else str(chat_id)
    )
    await state.update_data(role="participant", event_code=event_code, participant_name=participant_name)
    await state.set_state(FlowState.participant_contribute)
    await callback.message.answer(
        f"👤 Ты снова в поездке <b>#{event_number if isinstance(event_number, int) else html.escape(event_code)}</b> как участник.\n\n"
        f"{format_brief_for_participant(brief, event_number=event_number)}\n\n"
        "Напиши одним сообщением, что дополнить в брифе.",
        reply_markup=main_menu_keyboard(),
    )


async def _invite_link_for_state(state: FSMContext) -> Optional[str]:
    data = await state.get_data()
    event_code = data.get("event_code")
    event = EVENTS.get(event_code) if event_code else None
    if not event:
        return None
    return event.get("invite_link")


async def _organizer_event_from_state(state: FSMContext) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    data = await state.get_data()
    event_code = data.get("event_code")
    if not event_code:
        return None, None
    event = EVENTS.get(event_code)
    if not event:
        return None, None
    return event_code, event


async def notify_organizer_brief_ready(bot: Bot, event_code: str) -> None:
    event = EVENTS.get(event_code)
    if not event or not can_offer_brief_confirm(event):
        return
    organizer_chat_id = event.get("organizer_chat_id")
    if not organizer_chat_id:
        return
    await bot.send_message(
        organizer_chat_id,
        BRIEF_READY_TO_CONFIRM_TEXT,
        reply_markup=brief_ready_keyboard(),
    )


async def brief_confirm_prep_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    _event_code, event = await _organizer_event_from_state(state)
    if not event:
        await callback.message.answer("Сначала создай поездку и собери базовый бриф.")
        return
    if event.get("organizer_brief_confirmed_at"):
        await callback.message.answer(BRIEF_CONFIRMED_TEXT, reply_markup=brief_confirmed_keyboard())
        return
    if not can_offer_brief_confirm(event):
        await callback.message.answer(
            "Пока рано подтверждать бриф: дозаполни базовые вводные или дождись ответов участников.",
            reply_markup=main_menu_keyboard(),
        )
        return
    await callback.message.answer(BRIEF_READY_TO_CONFIRM_TEXT, reply_markup=brief_ready_keyboard())


async def brief_confirm_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    event_code, event = await _organizer_event_from_state(state)
    if not event or not event_code:
        await callback.message.answer("Поездка не найдена.")
        return
    if event.get("organizer_brief_confirmed_at"):
        await callback.message.answer(BRIEF_CONFIRMED_TEXT, reply_markup=brief_confirmed_keyboard())
        return
    if not can_offer_brief_confirm(event):
        await callback.message.answer(
            "Пока нельзя подтвердить бриф: проверь вводные и ответы участников.",
            reply_markup=main_menu_keyboard(),
        )
        return
    ts = now_ts()
    event["organizer_brief_confirmed_at"] = ts
    event["completed_at"] = event.get("completed_at") or ts
    touch_event(event)
    save_events()
    await callback.message.answer(BRIEF_CONFIRMED_TEXT, reply_markup=brief_confirmed_keyboard())
    await log_session_action(
        callback.bot,
        callback.message,
        "бриф подтверждён организатором",
        role="organizer",
        event_number=event.get("event_number"),
    )
    await flush_session_milestone(callback.bot, callback.message, "organizer_brief_confirmed")


async def brief_edit_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(FlowState.organizer_clarify)
    await callback.message.answer(
        "Хорошо, напиши одним сообщением, что уточнить или дополнить в брифе.",
        reply_markup=main_menu_keyboard(),
    )


async def brief_share_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    _event_code, event = await _organizer_event_from_state(state)
    if not event or not event.get("organizer_brief_confirmed_at"):
        await callback.message.answer(
            "Сначала подтверди бриф — тогда я подготовлю текст для пересылки.",
            reply_markup=brief_ready_keyboard() if event and can_offer_brief_confirm(event) else main_menu_keyboard(),
        )
        return
    await callback.message.answer(BRIEF_SHARE_INTRO_TEXT, reply_markup=brief_share_intro_keyboard())


async def brief_share_text_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    _event_code, event = await _organizer_event_from_state(state)
    if not event:
        await callback.message.answer("Поездка не найдена.")
        return
    if not event.get("organizer_brief_confirmed_at"):
        if can_offer_brief_confirm(event):
            await callback.message.answer(
                "Сначала подтверди бриф на предыдущем шаге.",
                reply_markup=brief_ready_keyboard(),
            )
        else:
            await callback.message.answer("Сначала собери и подтверди бриф поездки.")
        return
    brief = event.get("brief") or {}
    plain = format_brief_plain_for_share(brief, event.get("event_number"))
    share_text = html.escape(build_brief_share_text(plain))
    await callback.message.answer(
        "📋 <b>Скопируй и отправь</b>\n"
        "Ниже текст для пересылки. Можешь отредактировать формулировки перед отправкой.\n\n"
        f"<pre>{share_text}</pre>",
        reply_markup=brief_after_share_keyboard(),
    )


async def brief_share_done_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Принято")
    await callback.message.answer(BRIEF_SHARE_DONE_TEXT, reply_markup=brief_share_done_keyboard())


def participant_thanks_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Дополнить ещё", callback_data="participant:edit")],
            [InlineKeyboardButton(text="📌 Посмотреть бриф", callback_data="event:show_brief")],
        ]
    )


async def event_how_callback_handler(callback: CallbackQuery) -> None:
    await callback.answer()
    await capabilities_handler(callback.message)


async def event_invite_link_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    invite_link = await _invite_link_for_state(state)
    if not invite_link:
        await callback.message.answer(
            "Ссылка пока недоступна. Попробуй /start или создай новую поездку.",
            reply_markup=main_menu_keyboard(),
        )
        return
    _event_code, event = await _organizer_event_from_state(state)
    await callback.message.answer(
        "🔗 <b>Ссылка для участников</b>\n"
        f"<code>{html.escape(invite_link)}</code>",
        reply_markup=invite_ready_keyboard(event),
    )


async def event_invite_share_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    invite_link = await _invite_link_for_state(state)
    if not invite_link:
        await callback.message.answer(
            "Ссылка пока недоступна. Попробуй /start или создай новую поездку.",
            reply_markup=main_menu_keyboard(),
        )
        return
    share_text = html.escape(build_invite_share_text(invite_link))
    await callback.message.answer(
        "📤 <b>Текст для пересылки участникам</b>\n"
        "Скопируй и отправь в общий чат или личные сообщения:\n\n"
        f"<pre>{share_text}</pre>",
        reply_markup=invite_after_share_keyboard(),
    )


async def event_invite_sent_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.answer(
        "⏳ <b>Ссылка готова</b>\n"
        "Ждём ответы участников. Как только кто-то добавит пожелания, я обновлю бриф и покажу, что изменилось.",
        reply_markup=invite_waiting_keyboard(),
    )


async def event_invite_done_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Принято")
    await callback.message.answer(
        "⏳ <b>Ссылка готова</b>\n"
        "Ждём ответы участников. Как только кто-то добавит пожелания, я обновлю бриф и покажу, что изменилось.",
        reply_markup=invite_waiting_keyboard(),
    )


async def event_show_brief_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    event_code = data.get("event_code")
    role = data.get("role") or "organizer"
    if not event_code:
        recovered = get_latest_event_for_chat(callback.message.chat.id)
        if not recovered:
            await callback.message.answer("Пока нет активного брифа. Создай поездку через «✨ Новая поездка».")
            return
        event_code, event, role = recovered
        await state.update_data(event_code=event_code, role=role)
    event = EVENTS.get(event_code)
    if not event:
        await callback.message.answer("Поездка не найдена.")
        return
    brief = event.get("brief") or {}
    event_number = event.get("event_number")
    if role == "participant":
        body = format_brief_for_participant(brief, event_number=event_number)
    else:
        body = format_brief_update_message(brief, event_number=event_number)
    await callback.message.answer(body, reply_markup=main_menu_keyboard())


async def resume_latest_trip(message: Message, state: FSMContext, *, from_user: Optional[Any] = None) -> None:
    recovered = get_latest_event_for_chat(message.chat.id)
    if not recovered:
        await message.answer(
            "Пока не вижу активной поездки. Создай новую кнопкой «✨ Новая поездка» или через /start.",
            reply_markup=main_menu_keyboard(),
        )
        return
    event_code, event, role = recovered
    brief = event.get("brief") or {}
    event_number = event.get("event_number")
    if role == "organizer":
        await state.update_data(role="organizer", event_code=event_code, brief=brief)
        missing = missing_brief_fields(brief)
        if missing:
            await state.set_state(FlowState.organizer_clarify)
        else:
            await state.set_state(FlowState.organizer_clarify)
        await message.answer(
            f"🧭 <b>Текущая поездка</b> · #{event_number if isinstance(event_number, int) else '—'}\n\n"
            f"{format_brief_update_message(brief, event_number=event_number)}\n\n"
            "Напиши одним сообщением, что уточнить или дополнить.",
            reply_markup=main_menu_keyboard(),
        )
        if not missing and event.get("invite_link"):
            await message.answer(
                "Ссылка для участников уже есть — можешь поделиться ещё раз.",
                reply_markup=invite_waiting_keyboard(),
            )
        return
    participant_name = from_user.full_name if from_user and getattr(from_user, "full_name", None) else str(message.chat.id)
    await state.update_data(role="participant", event_code=event_code, participant_name=participant_name)
    await state.set_state(FlowState.participant_contribute)
    await message.answer(
        f"🧭 <b>Текущая поездка</b> · #{event_number if isinstance(event_number, int) else '—'}\n\n"
        f"{format_brief_for_participant(brief, event_number=event_number)}\n\n"
        "Напиши одним сообщением, что важно лично тебе.",
        reply_markup=main_menu_keyboard(),
    )


async def current_trip_handler(message: Message, state: FSMContext) -> None:
    logging.info("Current trip requested by chat_id=%s", message.chat.id)
    await resume_latest_trip(message, state, from_user=message.from_user)
    await log_session_action(message.bot, message, "текущая поездка")


async def help_continue_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await resume_latest_trip(callback.message, state, from_user=callback.from_user)


async def help_parser_callback_handler(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        "📝 <b>Как написать вводные</b>\n"
        "Пиши свободно, одним сообщением. Я сама разложу текст по полям.\n\n"
        "Пример:\n"
        "«2 взрослых, август, бюджет до 300к, перелёт до 5 часов, без визы, хотим море и экскурсии»\n\n"
        "Чем конкретнее формулировки, тем меньше уточняющих вопросов.",
        reply_markup=help_keyboard(),
    )


async def help_clarify_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    fsm_state = await state.get_state()
    snap = context_snapshot(callback.message.chat.id, fsm_state)
    missing = snap.get("missing_fields") or []
    if not missing:
        await callback.message.answer(
            "✅ Сейчас критичных белых пятен не вижу. Бриф достаточно полный для следующего шага.",
            reply_markup=help_keyboard(),
        )
        return
    missing_text = "\n".join(f"• {html.escape(item)}" for item in missing)
    await callback.message.answer(
        "❓ <b>Почему я прошу уточнение</b>\n"
        "Эти пункты нужны, чтобы не ошибиться в итоговом брифе:\n"
        f"{missing_text}\n\n"
        "Можешь ответить одним сообщением в свободной форме.",
        reply_markup=help_keyboard(),
    )


async def help_link_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    fsm_state = await state.get_state()
    snap = context_snapshot(callback.message.chat.id, fsm_state)
    if not snap.get("has_event"):
        await callback.message.answer(
            "Сначала создай поездку — тогда появится ссылка для участников.",
            reply_markup=help_keyboard(),
        )
        return
    if snap.get("role") != "organizer":
        await callback.message.answer(
            "Ссылку отправляет организатор. Если её нет — попроси организатора нажать «📤 Поделиться приглашением».",
            reply_markup=help_keyboard(),
        )
        return
    if not snap.get("invite_ready"):
        await callback.message.answer(
            "Ссылка ещё не готова. Сначала собери базовый бриф — тогда появится приглашение.",
            reply_markup=help_keyboard(),
        )
        return
    await callback.message.answer(
        "Если участник не может войти:\n"
        "1) попроси открыть ссылку заново\n"
        "2) попроси отправить /start в боте\n"
        "3) при необходимости нажми «📤 Поделиться приглашением» ещё раз.",
        reply_markup=help_keyboard(),
    )


async def help_my_events_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await my_events_handler(callback.message, state)


async def help_report_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    fsm_state = await state.get_state()
    snap = context_snapshot(callback.message.chat.id, fsm_state)
    if snap.get("has_event"):
        event_number = snap.get("event_number")
        role = "организатор" if snap.get("role") == "organizer" else "участник"
        context = (
            f"• Событие: #{event_number if isinstance(event_number, int) else '—'}\n"
            f"• Роль: {role}\n"
            f"• Этап: {snap.get('state')}"
        )
    else:
        context = f"• Этап: {snap.get('state')}\n• Активное событие: не найдено"
    await callback.message.answer(
        "📨 <b>Сообщить о проблеме</b>\n"
        "Отправь одним сообщением:\n"
        "1) что нажала\n"
        "2) что ожидала увидеть\n"
        "3) что пришло фактически\n\n"
        f"Контекст для сообщения:\n{context}",
        reply_markup=help_keyboard(),
    )


async def role_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    data = callback.data or ""
    logging.info("Role selected: %s chat_id=%s", data, callback.message.chat.id)
    await callback.answer()

    if data == "role:organizer":
        await state.update_data(role="organizer")
        await callback.message.answer(
            "Отлично. Раз ты создаёшь поездку — ты организатор.\n\n"
            "Нажми кнопку ниже, чтобы начать сбор вводных.",
            reply_markup=organizer_next_keyboard(),
        )
        return

    await state.update_data(role="participant")
    await callback.message.answer(
        "Ты — участник. Чтобы войти в поездку, открой ссылку от организатора.\n\n"
        "После перехода по ссылке я подключу тебя к брифу — можно сразу написать пожелания одним сообщением.",
        reply_markup=main_menu_keyboard(),
    )


async def start_payload_handler(message: Message, command: CommandObject, state: FSMContext) -> None:
    payload = (command.args or "").strip()
    if not payload.startswith("join_"):
        await start_handler(message, state)
        return

    event_code = payload.removeprefix("join_")
    event = EVENTS.get(event_code)
    if not event:
        await message.answer(
            "Похоже, ссылка устарела или поездка уже не активна.\n"
            "Попроси организатора прислать новую ссылку."
        )
        return

    participants = event.setdefault("participants", {})
    participant_id = str(message.chat.id)
    participant_row = participants.get(participant_id) or {}
    participant_row.setdefault("role", "participant")
    participant_row.setdefault("joined_at", now_ts())
    participant_row["name"] = (
        message.from_user.full_name if message.from_user else str(message.chat.id)
    )
    participant_row["username"] = (
        message.from_user.username if message.from_user else None
    )
    participant_row["updated_at"] = now_ts()
    participants[participant_id] = participant_row
    save_events()
    event_brief = event.get("brief") or {}
    event_number = event.get("event_number")
    participant_name = (
        message.from_user.full_name
        if message.from_user and message.from_user.full_name
        else str(message.chat.id)
    )
    await state.update_data(
        role="participant",
        event_code=event_code,
        participant_name=participant_name,
    )
    await state.set_state(FlowState.participant_contribute)
    await message.answer(
        "✅ <b>Ты подключён к поездке</b>\n"
        f"Номер: <b>#{event_number if isinstance(event_number, int) else '—'}</b>\n\n"
        "Организатор уже собрал базовые вводные — ты можешь добавить то, что важно лично тебе.\n\n"
        "✍️ <b>Что сделать сейчас</b>\n"
        "Посмотри бриф ниже и напиши одним сообщением пожелания: даты, бюджет, перелёт, отель, климат, активности или ограничения."
    )
    await message.answer(
        f"{format_brief_for_participant(event_brief, event_number=event_number)}"
    )
    await log_session_action(
        message.bot,
        message,
        "вход участника",
        role="participant",
        event_number=event_number,
    )


async def participant_contribute_handler(message: Message, state: FSMContext) -> None:
    if await handle_menu_shortcuts(message):
        return

    data = await state.get_data()
    event_code = data.get("event_code")
    if not event_code or event_code not in EVENTS:
        await message.answer("Событие не найдено. Попросите организатора прислать новую ссылку.")
        return

    event = EVENTS[event_code]
    event_number = event.get("event_number")
    base_brief = event.get("brief") or {}
    merger_conflicts: List[str] = []
    incoming = extract_brief_from_text(message.text or "")
    participant_name = data.get("participant_name") or (
        message.from_user.full_name if message.from_user else str(message.chat.id)
    )
    updated_brief = merge_participant_into_brief(base_brief, incoming, participant_name)
    change_info = live_response.detect_field_changes(base_brief, incoming, updated_brief)
    conflict_keys = []
    for key in incoming.keys():
        if key in base_brief and base_brief.get(key) != incoming.get(key):
            conflict_keys.append(key)
    if brief_pipeline.structured_pipeline_enabled():
        structured_participant = brief_pipeline.parse_participant_message(
            message.text or "",
            participant_name,
        )
        if structured_participant:
            participant_inputs_structured = event.get("participant_inputs_structured") or []
            participant_inputs_structured = brief_pipeline.upsert_participant_input(
                participant_inputs_structured,
                structured_participant,
            )
            event["participant_inputs_structured"] = participant_inputs_structured
            merged_structured = brief_pipeline.merge_brief_inputs(
                base_brief_json=event.get("base_brief_structured") or {},
                participant_inputs_json=participant_inputs_structured,
                new_input_json=structured_participant,
                current_event_status=_event_status_info(event).get("key", "active"),
            )
            if merged_structured:
                event["merged_brief_structured"] = merged_structured
                merger_conflicts = [
                    str(item.get("topic") or item.get("description") or "расхождение")
                    for item in (merged_structured.get("conflicts") or [])
                    if isinstance(item, dict)
                ]
    event["brief"] = updated_brief

    updates = event.setdefault("participant_updates", {})
    updates[chat_key(message.chat.id)] = {
        "text": message.text or "",
        "confirmed": False,
        "name": participant_name,
        "username": (message.from_user.username if message.from_user else None),
        "updated_at": now_ts(),
    }
    participants = event.setdefault("participants", {})
    if str(message.chat.id) in participants:
        participants[str(message.chat.id)]["updated_at"] = now_ts()
    touch_event(event)
    save_events()

    await state.set_state(FlowState.participant_confirm)
    missing = missing_brief_fields(updated_brief)
    missing_block = ""
    if missing:
        missing_text = "\n".join(f"• {html.escape(item)}" for item in missing)
        missing_block = (
            "\n\n🚨 <b>Нужно уточнить</b>\n"
            f"{missing_text}"
        )
    brief_html = format_brief_for_participant(updated_brief, event_number=event_number)
    await emit_parse_log(
        message.bot,
        message,
        role="participant",
        event_number=event_number if isinstance(event_number, int) else None,
        step_label="пожелания участника",
        user_text=message.text or "",
        brief=updated_brief,
        missing=missing,
        brief_html=brief_html,
    )
    parser_result = live_response.build_parser_result(
        saved=True,
        confidence=parser_confidence_hint(),
        added_fields=change_info["added_fields"],
        updated_fields=change_info["updated_fields"],
        conflicts=(conflict_keys + merger_conflicts),
    )
    live_context = build_live_prompt_context(
        role="participant",
        flow_step="participant_contribute",
        human_status="Получили пожелания участника",
        allowed_next_action="confirm_brief | continue_flow",
        last_system_action="participant_added_input",
        brief=updated_brief,
        missing=missing,
        parser_result=parser_result,
        conflicts=(conflict_keys + merger_conflicts),
        user_message=message.text or "",
    )
    intro_text = live_text_or_fallback(
        live_context,
        "Спасибо, добавила твои пожелания отдельно — организатор увидит их без потери деталей.",
    )
    await message.answer(
        f"{intro_text}\n\n"
        f"{brief_html}\n\n"
        f"Проверь, пожалуйста: всё верно?{missing_block}",
        reply_markup=participant_confirm_keyboard(),
    )


async def participant_confirm_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    event_code = data.get("event_code")
    if not event_code or event_code not in EVENTS:
        await callback.message.answer("Событие не найдено. Попросите новую ссылку от организатора.")
        return

    event = EVENTS[event_code]
    updates = event.setdefault("participant_updates", {})
    update_row = updates.setdefault(chat_key(callback.message.chat.id), {})
    update_row["confirmed"] = True
    update_row["confirmed_at"] = now_ts()
    participants = event.setdefault("participants", {})
    if str(callback.message.chat.id) in participants:
        participants[str(callback.message.chat.id)]["confirmed"] = True
        participants[str(callback.message.chat.id)]["confirmed_at"] = now_ts()
    touch_event(event)
    save_events()

    participant_name = data.get("participant_name") or (
        callback.from_user.full_name if callback.from_user else str(callback.message.chat.id)
    )
    await callback.message.answer(
        PARTICIPANT_THANKS_TEXT,
        reply_markup=participant_thanks_keyboard(),
    )

    organizer_chat_id = event.get("organizer_chat_id")
    if organizer_chat_id:
        username = callback.from_user.username if callback.from_user else None
        user_caption = f"@{username}" if username else participant_name
        await callback.bot.send_message(
            organizer_chat_id,
            "🔔 <b>Участник добавил пожелания</b>\n"
            "Я обновила бриф и отдельно показала, что изменилось.\n\n"
            f"{html.escape(user_caption)} подтвердил(а), что всё верно.\n\n"
            f"{format_brief_for_participant(event.get('brief') or {}, event_number=event.get('event_number'))}",
            reply_markup=invite_waiting_keyboard(),
        )
        if participants_all_confirmed(event):
            await notify_organizer_brief_ready(callback.bot, event_code)

    await log_session_action(
        callback.bot,
        callback.message,
        "подтверждение брифа",
        role="participant",
        event_number=event.get("event_number"),
    )
    await flush_session_milestone(callback.bot, callback.message, "participant_confirmed")


async def participant_edit_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(FlowState.participant_contribute)
    await callback.message.answer(
        "Хорошо, напиши одним сообщением, что уточнить или добавить в бриф."
    )


async def organizer_dump_handler(message: Message, state: FSMContext) -> None:
    try:
        if await handle_menu_shortcuts(message):
            return
        logging.info("Organizer dump received chat_id=%s", message.chat.id)
        data = await state.get_data()
        event_code = data.get("event_code")
        text = message.text or ""

        existing_brief = {}
        if event_code and event_code in EVENTS:
            existing_brief = EVENTS[event_code].get("brief") or {}

        incoming = extract_brief_from_text(text)
        brief = merge_brief(existing_brief, incoming)
        change_info = live_response.detect_field_changes(existing_brief, incoming, brief)
        merger_conflicts: List[str] = []

        if event_code and event_code in EVENTS:
            if brief_pipeline.structured_pipeline_enabled():
                structured_organizer = brief_pipeline.parse_organizer_message(text)
                if structured_organizer:
                    EVENTS[event_code]["base_brief_structured"] = structured_organizer
                    merged_structured = brief_pipeline.merge_brief_inputs(
                        base_brief_json=structured_organizer,
                        participant_inputs_json=EVENTS[event_code].get("participant_inputs_structured") or [],
                        new_input_json=structured_organizer,
                        current_event_status=_event_status_info(EVENTS[event_code]).get("key", "active"),
                    )
                    if merged_structured:
                        EVENTS[event_code]["merged_brief_structured"] = merged_structured
                        merger_conflicts = [
                            str(item.get("topic") or item.get("description") or "расхождение")
                            for item in (merged_structured.get("conflicts") or [])
                            if isinstance(item, dict)
                        ]
            EVENTS[event_code]["organizer_dump"] = text
            EVENTS[event_code]["brief"] = brief
            touch_event(EVENTS[event_code])
            save_events()

        await state.update_data(organizer_dump=text, brief=brief)
        await state.set_state(FlowState.organizer_clarify)

        missing = missing_brief_fields(brief)

        summary_text = format_brief_update_message(brief, event_number=EVENTS.get(event_code, {}).get("event_number"))
        event_number = EVENTS.get(event_code, {}).get("event_number")
        await emit_parse_log(
            message.bot,
            message,
            role="organizer",
            event_number=event_number if isinstance(event_number, int) else None,
            step_label="отправка брифа",
            user_text=text,
            brief=brief,
            missing=missing,
            brief_html=summary_text,
        )
        parser_result = live_response.build_parser_result(
            saved=True,
            confidence=parser_confidence_hint(),
            added_fields=change_info["added_fields"],
            updated_fields=change_info["updated_fields"],
            conflicts=merger_conflicts,
        )
        live_context = build_live_prompt_context(
            role="organizer",
            flow_step="organizer_dump",
            human_status="Ждём уточнение вводных" if missing else "Бриф собран",
            allowed_next_action="ask_clarification | show_invite_link | continue_flow",
            last_system_action="brief_updated" if not missing else "clarification_requested",
            brief=brief,
            missing=missing,
            parser_result=parser_result,
            conflicts=merger_conflicts,
            user_message=text,
        )

        if not missing:
            intro_text = live_text_or_fallback(
                live_context,
                "Отлично, базовых данных достаточно. Переходим к подключению участников.",
            )
            await message.answer(
                f"{summary_text}\n\n"
                f"{intro_text}",
                reply_markup=main_menu_keyboard(),
            )
            await send_next_step_after_brief(message, state)
            return

        missing_text = "\n".join(f"- {m}" for m in missing)
        clarify_text = live_text_or_fallback(
            live_context,
            "🚨 <b>Уточните только это</b> (можно одним сообщением):",
        )
        await message.answer(
            f"{summary_text}\n\n"
            f"{clarify_text}\n"
            f"{missing_text}",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as err:
        logging.exception("organizer_dump_handler failed: %s", err)
        await message.answer(
            "Не удалось обработать сообщение с первого раза.\n"
            "Отправьте, пожалуйста, вводные ещё раз одним сообщением.",
            reply_markup=main_menu_keyboard(),
        )


async def organizer_clarify_handler(message: Message, state: FSMContext) -> None:
    try:
        if await handle_menu_shortcuts(message):
            return
        # Any follow-up message in clarify state merges into brief and asks only remaining missing fields
        data = await state.get_data()
        event_code = data.get("event_code")
        brief = data.get("brief") or {}

        incoming = extract_brief_from_text(message.text or "")
        previous_brief = dict(brief)
        brief = merge_brief(brief, incoming)
        change_info = live_response.detect_field_changes(previous_brief, incoming, brief)
        merger_conflicts: List[str] = []

        if event_code and event_code in EVENTS:
            if brief_pipeline.structured_pipeline_enabled():
                structured_organizer = brief_pipeline.parse_organizer_message(message.text or "")
                if structured_organizer:
                    EVENTS[event_code]["base_brief_structured"] = structured_organizer
                    merged_structured = brief_pipeline.merge_brief_inputs(
                        base_brief_json=structured_organizer,
                        participant_inputs_json=EVENTS[event_code].get("participant_inputs_structured") or [],
                        new_input_json=structured_organizer,
                        current_event_status=_event_status_info(EVENTS[event_code]).get("key", "active"),
                    )
                    if merged_structured:
                        EVENTS[event_code]["merged_brief_structured"] = merged_structured
                        merger_conflicts = [
                            str(item.get("topic") or item.get("description") or "расхождение")
                            for item in (merged_structured.get("conflicts") or [])
                            if isinstance(item, dict)
                        ]
            EVENTS[event_code]["brief"] = brief
            touch_event(EVENTS[event_code])
            save_events()

        await state.update_data(brief=brief)

        missing = missing_brief_fields(brief)
        event_number = EVENTS.get(event_code, {}).get("event_number") if event_code else None
        summary_text = format_brief_update_message(brief, event_number=event_number)
        await emit_parse_log(
            message.bot,
            message,
            role="organizer",
            event_number=event_number if isinstance(event_number, int) else None,
            step_label="уточнение брифа",
            user_text=message.text or "",
            brief=brief,
            missing=missing,
            brief_html=summary_text,
        )
        parser_result = live_response.build_parser_result(
            saved=True,
            confidence=parser_confidence_hint(),
            added_fields=change_info["added_fields"],
            updated_fields=change_info["updated_fields"],
            conflicts=merger_conflicts,
        )
        live_context = build_live_prompt_context(
            role="organizer",
            flow_step="organizer_clarify",
            human_status="Ждём уточнение вводных" if missing else "Бриф собран",
            allowed_next_action="ask_clarification | show_invite_link | continue_flow",
            last_system_action="brief_updated" if not missing else "clarification_requested",
            brief=brief,
            missing=missing,
            parser_result=parser_result,
            conflicts=merger_conflicts,
            user_message=message.text or "",
        )
        if not missing:
            intro_text = live_text_or_fallback(
                live_context,
                "Отлично, спасибо! Данных достаточно. Переходим к подключению участников.",
            )
            await message.answer(
                f"{summary_text}\n\n"
                f"{intro_text}",
                reply_markup=main_menu_keyboard(),
            )
            await send_next_step_after_brief(message, state)
            return

        missing_text = "\n".join(f"- {m}" for m in missing)
        clarify_text = live_text_or_fallback(
            live_context,
            "🚨 <b>Осталось уточнить:</b>",
        )
        await message.answer(
            f"{summary_text}\n\n"
            f"{clarify_text}\n"
            f"{missing_text}\n\n"
            "Можно одним сообщением.",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as err:
        logging.exception("organizer_clarify_handler failed: %s", err)
        await message.answer(
            "Не получилось обработать уточнение.\n"
            "Попробуйте написать проще, например: «до 250к, июль, 2 взрослых, без визы».",
            reply_markup=main_menu_keyboard(),
        )


async def text_fallback_handler(message: Message) -> None:
    logging.info("Received text from chat_id=%s: %s", message.chat.id, message.text)
    normalized = normalize_text(message.text or "")
    if normalized in {"начать", "start", "/start"}:
        await start_handler(message, None)
        return
    if is_my_events_text(message.text or ""):
        await my_events_handler(message, None)
        return
    if is_capabilities_text(message.text or ""):
        await capabilities_handler(message)
        return
    if is_help_text(message.text or ""):
        await help_handler(message)
        return

    # Recovery path: if FSM state was lost (restart/multiple processes),
    # continue active organizer/participant flow based on persisted event data.
    recovered = get_latest_event_for_chat(message.chat.id)
    if recovered:
        event_code, event, role = recovered
        event_number = event.get("event_number")
        if role == "organizer":
            existing_brief = event.get("brief") or {}
            incoming = extract_brief_from_text(message.text or "")
            brief = merge_brief(existing_brief, incoming)
            EVENTS[event_code]["brief"] = brief
            EVENTS[event_code]["organizer_dump"] = message.text or ""
            touch_event(EVENTS[event_code])
            save_events()

            summary_text = format_brief_update_message(brief, event_number=event_number)
            missing = missing_brief_fields(brief)
            await emit_parse_log(
                message.bot,
                message,
                role="organizer",
                event_number=event_number if isinstance(event_number, int) else None,
                step_label="уточнение брифа (recovery)",
                user_text=message.text or "",
                brief=brief,
                missing=missing,
                brief_html=summary_text,
            )
            if not missing:
                await message.answer(
                    f"{summary_text}\n\n"
                    "Отлично, базовых данных достаточно. Переходим к подключению участников.",
                    reply_markup=main_menu_keyboard(),
                )
                await send_next_step_after_brief_by_event(message, event_code)
                return

            missing_text = "\n".join(f"- {m}" for m in missing)
            await message.answer(
                f"{summary_text}\n\n"
                "🚨 <b>Уточните только это</b> (можно одним сообщением):\n"
                f"{missing_text}",
                reply_markup=main_menu_keyboard(),
            )
            return

        if role == "participant":
            base_brief = event.get("brief") or {}
            incoming = extract_brief_from_text(message.text or "")
            participant_name = (
                message.from_user.full_name if message.from_user and message.from_user.full_name else str(message.chat.id)
            )
            updated_brief = merge_participant_into_brief(base_brief, incoming, participant_name)
            event["brief"] = updated_brief
            updates = event.setdefault("participant_updates", {})
            updates[chat_key(message.chat.id)] = {
                "text": message.text or "",
                "confirmed": False,
                "name": participant_name,
                "username": (message.from_user.username if message.from_user else None),
                "updated_at": now_ts(),
            }
            participants = event.setdefault("participants", {})
            if str(message.chat.id) in participants:
                participants[str(message.chat.id)]["updated_at"] = now_ts()
            touch_event(event)
            save_events()

            missing = missing_brief_fields(updated_brief)
            missing_block = ""
            if missing:
                missing_text = "\n".join(f"• {html.escape(item)}" for item in missing)
                missing_block = (
                    "\n\n🚨 <b>Нужно уточнить</b>\n"
                    f"{missing_text}"
                )
            brief_html = format_brief_for_participant(updated_brief, event_number=event_number)
            await emit_parse_log(
                message.bot,
                message,
                role="participant",
                event_number=event_number if isinstance(event_number, int) else None,
                step_label="пожелания участника (recovery)",
                user_text=message.text or "",
                brief=updated_brief,
                missing=missing,
                brief_html=brief_html,
            )
            await message.answer(
                "Спасибо, добавила твои пожелания отдельно — организатор увидит их без потери деталей.\n\n"
                f"{brief_html}\n\n"
                f"Проверь, пожалуйста: всё верно?{missing_block}",
                reply_markup=participant_confirm_keyboard(),
            )
            return

    await message.answer(
        "Чтобы продолжить, выбери действие в меню ниже.",
        reply_markup=main_menu_keyboard(),
    )


async def cancel_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Ок, прервала текущий ввод. Можешь вернуться к поездке через «🧭 Текущая поездка».",
        reply_markup=main_menu_keyboard(),
    )


async def main() -> None:
    load_dotenv()
    load_events()
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Missing BOT_TOKEN in environment")

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())

    # Handle both plain /start and /start <payload> deep-links.
    dp.message.register(start_payload_handler, CommandStart())
    dp.message.register(help_handler, Command("help"))
    dp.message.register(cancel_handler, Command("cancel"))
    dp.message.register(current_trip_handler, F.text.func(is_current_trip_text))
    dp.message.register(new_event_handler, F.text.func(is_create_event_text))
    dp.message.register(my_events_handler, F.text.func(is_my_events_text))
    dp.message.register(capabilities_handler, F.text.func(is_capabilities_text))
    dp.message.register(help_handler, F.text.func(is_help_text))
    dp.message.register(participant_contribute_handler, FlowState.participant_contribute, F.text)
    dp.message.register(organizer_dump_handler, FlowState.organizer_dump, F.text)
    dp.message.register(organizer_clarify_handler, FlowState.organizer_clarify, F.text)
    dp.message.register(text_fallback_handler, F.text)

    dp.callback_query.register(role_callback_handler, F.data.startswith("role:"))
    dp.callback_query.register(event_create_callback_handler, F.data == "event:create")
    dp.callback_query.register(event_open_callback_handler, F.data.startswith("event:open:"))
    dp.callback_query.register(brief_confirm_prep_callback_handler, F.data == "brief:confirm_prep")
    dp.callback_query.register(brief_confirm_callback_handler, F.data == "brief:confirm")
    dp.callback_query.register(brief_edit_callback_handler, F.data == "brief:edit")
    dp.callback_query.register(brief_share_callback_handler, F.data == "brief:share")
    dp.callback_query.register(brief_share_text_callback_handler, F.data == "brief:share_text")
    dp.callback_query.register(brief_share_done_callback_handler, F.data == "brief:share_done")
    dp.callback_query.register(event_how_callback_handler, F.data == "event:how")
    dp.callback_query.register(event_invite_link_callback_handler, F.data == "event:invite_link")
    dp.callback_query.register(event_invite_share_callback_handler, F.data == "event:invite_share")
    dp.callback_query.register(event_invite_sent_callback_handler, F.data == "event:invite_sent")
    dp.callback_query.register(event_invite_done_callback_handler, F.data == "event:invite_done")
    dp.callback_query.register(event_show_brief_callback_handler, F.data == "event:show_brief")
    dp.callback_query.register(help_continue_callback_handler, F.data == "help:continue")
    dp.callback_query.register(help_parser_callback_handler, F.data == "help:parser")
    dp.callback_query.register(help_clarify_callback_handler, F.data == "help:clarify")
    dp.callback_query.register(help_link_callback_handler, F.data == "help:link")
    dp.callback_query.register(help_my_events_callback_handler, F.data == "help:myevents")
    dp.callback_query.register(help_report_callback_handler, F.data == "help:report")
    dp.callback_query.register(participant_confirm_callback_handler, F.data == "participant:confirm")
    dp.callback_query.register(participant_edit_callback_handler, F.data == "participant:edit")

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Перезапустить бота"),
            BotCommand(command="help", description="Помощь, если застрял"),
            BotCommand(command="cancel", description="Отменить текущий ввод"),
        ]
    )

    global BOT_USERNAME
    BOT_USERNAME = None
    me_attempts = 3
    for attempt in range(1, me_attempts + 1):
        try:
            me = await asyncio.wait_for(bot.get_me(), timeout=8)
            BOT_USERNAME = me.username
            logging.info("Bot profile loaded: @%s", BOT_USERNAME)
            break
        except Exception as err:
            if attempt >= me_attempts:
                logging.warning(
                    "Failed to load bot profile after %s attempts: %s. Continuing without username.",
                    me_attempts,
                    err,
                )
                break
            wait_seconds = attempt * 2
            logging.warning(
                "get_me failed (attempt %s/%s): %s. Retrying in %ss...",
                attempt,
                me_attempts,
                err,
                wait_seconds,
            )
            await asyncio.sleep(wait_seconds)

    # Polling mode should not compete with webhooks.
    # If Telegram API is temporarily slow, do not block startup forever.
    try:
        await asyncio.wait_for(
            bot.delete_webhook(drop_pending_updates=True),
            timeout=6,
        )
    except Exception as err:
        logging.warning("delete_webhook skipped due to network issue: %s", err)

    logging.info("Starting bot polling...")
    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            await dp.start_polling(bot)
            return
        except Exception as err:
            if attempt >= max_attempts:
                raise
            wait_seconds = attempt * 2
            logging.warning(
                "Polling start failed (attempt %s/%s): %s. Retrying in %ss...",
                attempt,
                max_attempts,
                err,
                wait_seconds,
            )
            await asyncio.sleep(wait_seconds)


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
