import asyncio
import html
import logging
import os
import re
import secrets
import time
from typing import Optional, Dict, Any, List
from urllib.parse import quote

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

import brief_flat_mapper
import brief_parser
import brief_pipeline
import brief_stay_enrich
import env_util
from parser_mode import get_parser_mode, llm_available
import dialog_context
import live_response
import message_intent
from interaction_log import flush_session_milestone, log_parse_result, log_session_action
from storage import load_events_from_file, save_events_to_file
import brief_display
import ui_feedback


format_budget_display = brief_display.format_budget_display
format_flight_display = brief_display.format_flight_display


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


def user_display_first_name(user: Any) -> str:
    if not user:
        return ""
    return (getattr(user, "first_name", None) or "").strip()


def format_start_greeting(user: Any) -> str:
    name = user_display_first_name(user)
    hello = f"Привет, {html.escape(name)}!" if name else "Привет!"
    return (
        f"👋 <b>{hello}</b>\n\n"
        "Я <b>MyTravel.Lab</b> — бот, который помогает собрать общий бриф поездки "
        "для всей компании.\n\n"
        "<b>Как это работает:</b>\n"
        "1. Ты пишешь вводные своими словами.\n"
        "2. Я формирую структурированный бриф.\n"
        "3. Участники добавляют пожелания по ссылке.\n"
        "4. Я собираю всё в одну картину и подсвечиваю расхождения.\n\n"
        "Нажми <b>✨ Создать поездку</b>, чтобы начать."
    )


def format_trip_created_organizer_message(event_number: Any) -> str:
    num = event_number if isinstance(event_number, int) else "—"
    return (
        f"✨ <b>Поездка создана</b> · #{num}\n\n"
        "<b>Твоя роль:</b> организатор — ты собираешь вводные и приглашаешь участников.\n\n"
        "Напиши <b>своими словами одним сообщением</b> — например:\n"
        "«2 взрослых, август, бюджет до 300к, перелёт до 5 часов, без визы, "
        "хотим море и экскурсии»"
    )


def build_invite_share_text(
    invite_link: str,
    *,
    trip_title: Optional[str] = None,
    include_link: bool = False,
) -> str:
    """Текст приглашения для пересылки участнику.

    Для t.me/share/url ссылку в текст не добавляем — Telegram подставляет её из параметра url.
    """
    trip_label = f"«{trip_title}»" if trip_title else "нашей поездке"
    body = (
        f"Привет! Приглашаю в поездку {trip_label} в MyTravel.Lab.\n\n"
        "Организатор собрал базовый бриф — в боте посмотри, что уже собрано, "
        "и допиши одним сообщением, что важно лично тебе."
    )
    if include_link:
        return f"{body}\n\n{invite_link}"
    return body


def invite_share_text_for_event(
    event: Dict[str, Any], *, include_link: bool = False
) -> str:
    invite_link = str((event or {}).get("invite_link") or "").strip()
    brief = (event or {}).get("brief") or {}
    if not str(brief.get("trip_title") or "").strip():
        brief_display.sync_trip_title(brief)
    trip_title = brief_display.get_trip_title(brief)
    return build_invite_share_text(
        invite_link, trip_title=trip_title, include_link=include_link
    )


def telegram_share_url(invite_link: str, share_text: Optional[str] = None) -> str:
    """Открывает выбор чата/контакта в Telegram (t.me/share/url)."""
    text = share_text if share_text is not None else build_invite_share_text(invite_link)
    if invite_link and invite_link in text:
        text = text.replace(invite_link, "").strip().rstrip("\n")
    return (
        "https://t.me/share/url?"
        f"url={quote(invite_link, safe='')}&text={quote(text, safe='')}"
    )


def ensure_event_invite_link(event: Dict[str, Any]) -> Optional[str]:
    """Вернуть invite_link; при необходимости создать и сохранить."""
    existing = str(event.get("invite_link") or "").strip()
    if existing:
        return existing
    code = event.get("code")
    if not BOT_USERNAME or not code:
        return None
    link = f"https://t.me/{BOT_USERNAME}?start=join_{code}"
    event["invite_link"] = link
    touch_event(event)
    save_events()
    return link


def backfill_invite_links() -> None:
    if not BOT_USERNAME:
        return
    changed = False
    for event in EVENTS.values():
        if event.get("invite_link") or not event.get("code"):
            continue
        event["invite_link"] = f"https://t.me/{BOT_USERNAME}?start=join_{event['code']}"
        touch_event(event)
        changed = True
    if changed:
        save_events()


def format_invite_step_message(
    event_number: Optional[int] = None,
    *,
    event: Optional[Dict[str, Any]] = None,
) -> str:
    brief = (event or {}).get("brief") or {}
    if event and not str(brief.get("trip_title") or "").strip():
        brief_display.sync_trip_title(brief)
    trip_title = brief_display.get_trip_title(brief) if brief else ""
    trip_title_esc = html.escape(trip_title) if trip_title else ""
    if trip_title_esc and trip_title != "Новая поездка":
        if isinstance(event_number, int):
            head = f"✨ <b>Бриф готов</b> · {trip_title_esc} <i>· #{event_number}</i>"
        else:
            head = f"✨ <b>Бриф готов</b> · {trip_title_esc}"
    elif isinstance(event_number, int):
        head = f"✨ <b>Бриф по #{event_number} готов</b>"
    else:
        head = "✨ <b>Бриф готов</b>"
    return (
        f"{head}\n\n"
        "Нажми <b>📤 Поделиться приглашением</b> — выбери чат с участником.\n"
        "В пересылке будет ссылка: в боте посмотрят, что уже собрано, "
        "и допишут пожелания <b>одним сообщением</b>."
    )


def format_participant_join_welcome_message(
    user: Any, brief: Dict[str, Any]
) -> str:
    """Приветствие участника после перехода по invite deep-link."""
    if not str(brief.get("trip_title") or "").strip():
        brief_display.sync_trip_title(brief)
    trip_title = html.escape(brief_display.get_trip_title(brief))
    first = user_display_first_name(user)
    if first:
        intro = f"👋 <b>{html.escape(first)}</b>, тебя пригласили в поездку"
    else:
        intro = "👋 Тебя пригласили в поездку"
    return (
        f"{intro} <b>{trip_title}</b>.\n\n"
        "Посмотри, что мы уже успели собрать.\n"
        "Допиши <b>одним сообщением</b>, что важно лично тебе — дополню общую картину."
    )


def participant_join_keyboard(event_code: str) -> Optional[InlineKeyboardMarkup]:
    if not BOT_USERNAME or not event_code:
        return None
    join_link = f"https://t.me/{BOT_USERNAME}?start=join_{event_code}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Присоединиться к поездке", url=join_link)],
        ]
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

    budget_line = format_budget_display(brief)
    if budget_line != "—":
        lines.append(f"Бюджет: {budget_line}")

    group_parts: List[str] = []
    if brief.get("adults"):
        group_parts.append(f"{brief['adults']} взрослых")
    if brief.get("kids_count"):
        group_parts.append(f"{brief['kids_count']} детей")
    if group_parts:
        lines.append("Состав: " + ", ".join(group_parts))

    flight_line = format_flight_display(brief)
    if flight_line != "—":
        lines.append(f"Перелёт: {flight_line}")

    if brief.get("trip_duration_days_raw"):
        lines.append(f"Длительность: {brief['trip_duration_days_raw']}")

    if "visa_required" in brief:
        lines.append("Визы: " + ("нужна" if brief["visa_required"] else "без визы"))

    if brief.get("passports_status"):
        lines.append(f"Загранпаспорта: {brief['passports_status']}")

    brief_stay_enrich.enrich_stay_from_context(brief)
    scenario = brief_stay_enrich.format_stay_experience_display(brief)
    if scenario:
        lines.append(f"Сценарий и локация: {scenario}")
    elif brief.get("climate"):
        lines.append(f"Климат: {brief['climate']}")
    if brief.get("trip_type") and not scenario:
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
    "<b>📂 Мои поездки</b> или создай новую кнопкой <b>✨ Новая поездка</b>."
)

BOT_CAPABILITIES_HELP_BLOCK = (
    "ℹ️ <b>Что умеет бот</b>\n"
    "Собираю вводные всей компании в единый бриф — без анкет и таблиц.\n\n"
    "<b>Сейчас я умею:</b>\n"
    "• принять вводные организатора одним сообщением и уточнить только недостающее\n"
    "• подключить участников по ссылке и собрать их пожелания\n"
    "• собрать общую сводку и подсветить расхождения\n"
    "• сохранить прогресс, чтобы вернуться к поездке позже\n\n"
    "Рекомендации по направлениям — следующий этап развития."
)

PARTICIPANT_THANKS_TEXT = (
    "✅ <b>Спасибо, я зафиксировала твои пожелания</b>\n\n"
    "Организатор увидит их в общем брифе. Если захочешь что-то добавить — "
    "напиши одним сообщением в этот чат."
)


def _chat_id_matches(stored: Any, chat_id: int) -> bool:
    try:
        return int(stored) == int(chat_id)
    except (TypeError, ValueError):
        return stored == chat_id


def get_latest_event_for_chat(
    chat_id: int,
    *,
    preferred_organizer_code: Optional[str] = None,
) -> Optional[tuple[str, Dict[str, Any], str]]:
    """Та же политика выбора поездки организатора, что и resolve_organizer_event_code."""
    organizer_code = resolve_organizer_event_code(chat_id, preferred_organizer_code)
    if organizer_code and organizer_code in EVENTS:
        return organizer_code, EVENTS[organizer_code], "organizer"

    participant_hits: list[tuple[str, Dict[str, Any]]] = []
    for code, event in EVENTS.items():
        participants = event.get("participants") or {}
        if str(chat_id) in participants:
            participant_hits.append((code, event))
    if not participant_hits:
        return None
    participant_hits.sort(
        key=lambda x: (
            x[1].get("updated_at", x[1].get("created_at", 0)),
            brief_parser.brief_completeness_score(x[1].get("brief") or {}),
        ),
        reverse=True,
    )
    code, event = participant_hits[0]
    return code, event, "participant"


def text_looks_like_brief_submission(text: str) -> bool:
    intent = message_intent.classify_message_intent(
        text or "",
        role="organizer",
        flow_step="organizer_dump",
    )
    return intent in {"brief_input", "mixed"}


def pick_best_organizer_event(chat_id: int) -> Optional[tuple[str, Dict[str, Any]]]:
    code = resolve_organizer_event_code(chat_id, None)
    if not code:
        return None
    return code, EVENTS[code]


def resolve_organizer_event_code(chat_id: int, preferred_code: Optional[str] = None) -> Optional[str]:
    """Активная поездка организатора: сначала FSM/явный выбор, иначе самая свежая по updated_at."""
    if preferred_code and preferred_code in EVENTS:
        event = EVENTS[preferred_code]
        if _chat_id_matches(event.get("organizer_chat_id"), chat_id):
            return preferred_code
    hits: list[tuple[str, Dict[str, Any]]] = []
    for code, event in EVENTS.items():
        if _chat_id_matches(event.get("organizer_chat_id"), chat_id):
            hits.append((code, event))
    if not hits:
        return None
    hits.sort(
        key=lambda x: (
            x[1].get("updated_at", x[1].get("created_at", 0)),
            brief_parser.brief_completeness_score(x[1].get("brief") or {}),
        ),
        reverse=True,
    )
    return hits[0][0]


async def resolve_organizer_event_and_brief(
    message: Message,
    state: FSMContext,
) -> tuple[str, Dict[str, Any]]:
    """Бриф пишем в поездку из FSM; без FSM — в последнюю обновлённую поездку организатора."""
    load_events()
    chat_id = message.chat.id
    data = await state.get_data()
    preferred = data.get("event_code")
    code = resolve_organizer_event_code(chat_id, preferred if isinstance(preferred, str) else None)
    if not code:
        code = await bootstrap_organizer_event(message, state)
    existing_brief = brief_parser.restore_organizer_brief_from_event(EVENTS.get(code, {}) or {})
    await state.update_data(
        role="organizer",
        event_code=code,
        brief=existing_brief,
        organizer_chat_id=chat_id,
    )
    return code, existing_brief


async def restore_organizer_fsm_state(state: FSMContext, event_code: str) -> str:
    event = EVENTS.get(event_code) or {}
    brief = brief_parser.restore_organizer_brief_from_event(event)
    if not event.get("organizer_dump") and not brief:
        flow_step = "organizer_dump"
        await state.set_state(FlowState.organizer_dump)
    else:
        flow_step = "organizer_clarify"
        await state.set_state(FlowState.organizer_clarify)
    await state.update_data(role="organizer", event_code=event_code, brief=brief)
    return flow_step


async def bootstrap_organizer_event(message: Message, state: FSMContext) -> str:
    load_events()
    data = await state.get_data()
    preferred = data.get("event_code")
    code = resolve_organizer_event_code(
        message.chat.id,
        preferred if isinstance(preferred, str) else None,
    )
    if code:
        await restore_organizer_fsm_state(state, code)
        return code

    event_code = new_event_code()
    event_number = next_event_number()
    invite_link = (
        f"https://t.me/{BOT_USERNAME}?start=join_{event_code}" if BOT_USERNAME else None
    )
    EVENTS[event_code] = {
        "code": event_code,
        "event_number": event_number,
        "created_at": now_ts(),
        "updated_at": now_ts(),
        "organizer_chat_id": message.chat.id,
        "organizer_dump": None,
        "participants": {},
        "invite_link": invite_link,
    }
    touch_event(EVENTS[event_code])
    save_events()
    await state.update_data(
        role="organizer",
        event_code=event_code,
        organizer_chat_id=message.chat.id,
        brief={},
    )
    await state.set_state(FlowState.organizer_dump)
    logging.info("Auto-created organizer event %s for chat_id=%s", event_code, message.chat.id)
    return event_code


async def handle_menu_shortcuts(message: Message, state: Optional[FSMContext] = None) -> bool:
    if is_my_events_text(message.text or ""):
        await my_events_handler(message, state)
        return True
    if is_help_text(message.text or ""):
        await help_handler(message)
        return True
    return False


def parse_message_to_brief(
    text: str,
    *,
    role: str = "organizer",
    participant_name: str = "",
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    return brief_parser.parse_message_to_brief(
        text, role=role, participant_name=participant_name
    )


def run_group_merger_for_event(event: Dict[str, Any]) -> List[str]:
    """Merger только для группового брифа (после вклада участника)."""
    participants = event.get("participant_inputs_structured") or []
    base = event.get("base_brief_structured") or {}
    if not participants:
        return list(event.get("group_conflicts") or [])

    merged = brief_pipeline.merge_brief_inputs(
        base_brief_json=base,
        participant_inputs_json=participants,
        new_input_json=participants[-1],
        current_event_status=_event_status_info(event).get("key", "active"),
    )
    if merged:
        event["merged_brief_structured"] = merged
    conflicts = brief_flat_mapper.conflicts_from_merger(merged or {})
    event["group_conflicts"] = conflicts
    return conflicts


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
    if mode == "role_llm+rules":
        return 0.86
    if mode == "role_llm_fallback":
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
    dialog_history: Optional[List[Dict[str, str]]] = None,
    step_context_human: str = "",
) -> Dict[str, Any]:
    history = dialog_context.trim_dialog_history(dialog_history or [])
    recent = history if history else [{"role": "user", "text": user_message}]
    return {
        "role": role,
        "flow_step": flow_step,
        "human_status": human_status,
        "allowed_next_action": allowed_next_action,
        "last_system_action": last_system_action,
        "step_context_human": step_context_human
        or dialog_context.build_step_context_human(
            role=role, flow_step=flow_step, missing=missing
        ),
        "dialog_summary": dialog_context.build_dialog_summary(history),
        "last_bot_message": dialog_context.last_bot_message(history),
        "brief_json": brief,
        "missing_fields_json": missing,
        "parser_result_json": parser_result,
        "conflicts_json": conflicts,
        "recent_messages_json": recent,
        "user_message": user_message,
    }


def live_text_or_fallback(context: Dict[str, Any], fallback_text: str) -> str:
    result = live_response.generate_live_response(context, fallback_text)
    source = str(result.get("source") or "unknown")
    if source != "llm":
        logging.info("Live response using fallback (source=%s)", source)
    return str(result.get("assistant_text") or fallback_text)


def _strip_html_for_history(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


async def load_dialog_history(state: FSMContext) -> List[Dict[str, str]]:
    data = await state.get_data()
    return dialog_context.trim_dialog_history(data.get("dialog_history") or [])


async def save_dialog_turn(
    state: FSMContext,
    *,
    user_text: str = "",
    bot_text: str = "",
) -> List[Dict[str, str]]:
    history = await load_dialog_history(state)
    if user_text.strip():
        history = dialog_context.append_dialog_turn(history, role="user", text=user_text)
    if bot_text.strip():
        history = dialog_context.append_dialog_turn(
            history, role="assistant", text=_strip_html_for_history(bot_text)
        )
    await state.update_data(dialog_history=history)
    return history


async def answer_live_text(
    message: Message,
    context: Dict[str, Any],
    fallback_text: str,
) -> str:
    async with ui_feedback.thinking(message):
        return live_text_or_fallback(context, fallback_text)


STATIC_CLARIFY_HEADER_DUMP = "🚨 <b>Уточните только это</b> (можно одним сообщением):"
STATIC_CLARIFY_HEADER_CLARIFY = "🚨 <b>Осталось уточнить</b> (сначала главное):"
CONVERSATION_FALLBACK_ORGANIZER = (
    "Поняла. Расскажи, что для тебя важно в поездке — помогу сформулировать или ответить на вопрос."
)
CONVERSATION_FALLBACK_PARTICIPANT = (
    "Поняла. Если хочешь — помогу сформулировать пожелания; когда будешь готов, напиши факты одним сообщением."
)
MIXED_FALLBACK_ORGANIZER = (
    "Поняла вопрос. Ниже — что уже зафиксировала в брифе по твоим фактам."
)


def _append_organizer_dump(existing: Optional[str], new_text: str) -> str:
    prev = (existing or "").strip()
    chunk = (new_text or "").strip()
    if not chunk:
        return prev
    if not prev:
        return chunk
    if chunk in prev:
        return prev
    return f"{prev}\n{chunk}"


def build_organizer_brief_reply_parts(
    brief: Dict[str, Any],
    *,
    flow_step: str,
    event_number: Optional[int],
    chat_id: int,
    missing: List[str],
) -> tuple[List[str], bool]:
    summary_text = format_brief_update_message(
        brief, event_number=event_number, missing=missing
    )
    parts = [summary_text]
    if not missing:
        # CTA «пригласить» — в отдельном сообщении send_next_step_after_brief
        return parts, True

    top_missing = dialog_context.prioritize_missing(missing)
    header = (
        STATIC_CLARIFY_HEADER_DUMP
        if flow_step == "organizer_dump"
        else STATIC_CLARIFY_HEADER_CLARIFY
    )
    missing_text = "\n".join(f"- {m}" for m in top_missing)
    suffix = "\n\nМожно одним сообщением." if flow_step == "organizer_clarify" else ""
    extra = ""
    if len(missing) > len(top_missing):
        extra = (
            f"\n\n<i>И ещё {len(missing) - len(top_missing)} пункт(а) — можно в том же сообщении.</i>"
        )
    parts.append(f"{header}\n{missing_text}{suffix}{extra}")
    return parts, False


async def _apply_organizer_brief_from_message(
    message: Message,
    state: FSMContext,
    *,
    flow_step: str,
) -> tuple[Dict[str, Any], List[str], Optional[int], Optional[str]]:
    text = message.text or ""
    event_code, existing_brief = await resolve_organizer_event_and_brief(message, state)
    event = EVENTS.get(event_code, {}) if event_code else {}
    has_prior_dump = isinstance(event.get("organizer_dump"), str) and bool(event.get("organizer_dump", "").strip())

    incoming, structured = parse_message_to_brief(text, role="organizer")
    brief = brief_parser.merge_organizer_incoming(
        existing_brief,
        incoming,
        flow_step=flow_step,
        has_prior_dump=has_prior_dump,
    )

    if event_code and event_code in EVENTS:
        if structured:
            EVENTS[event_code]["base_brief_structured"] = structured
        if flow_step == "organizer_dump":
            prev_dump = EVENTS[event_code].get("organizer_dump")
            if isinstance(prev_dump, str) and prev_dump.strip():
                EVENTS[event_code]["organizer_dump"] = _append_organizer_dump(prev_dump, text)
            else:
                EVENTS[event_code]["organizer_dump"] = text
        dump_text = EVENTS[event_code].get("organizer_dump")
        if isinstance(dump_text, str) and dump_text.strip():
            brief["organizer_dump"] = dump_text
        EVENTS[event_code]["brief"] = brief
        touch_event(EVENTS[event_code])
        save_events()

    if flow_step == "organizer_dump":
        await state.update_data(organizer_dump=text, brief=brief)
        await state.set_state(FlowState.organizer_clarify)
    else:
        await state.update_data(brief=brief)

    missing = missing_brief_fields(brief)
    event_number = EVENTS.get(event_code, {}).get("event_number") if event_code else None
    return brief, missing, event_number, event_code


async def handle_organizer_brief_input(
    message: Message,
    state: FSMContext,
    *,
    flow_step: str,
) -> None:
    text = message.text or ""
    await save_dialog_turn(state, user_text=text)
    async with ui_feedback.thinking(message):
        brief, missing, event_number, _event_code = await _apply_organizer_brief_from_message(
            message, state, flow_step=flow_step
        )
    parts, is_complete = build_organizer_brief_reply_parts(
        brief,
        flow_step=flow_step,
        event_number=event_number,
        chat_id=message.chat.id,
        missing=missing,
    )
    body = "\n\n".join(parts)
    await message.answer(body, reply_markup=main_menu_keyboard())
    await save_dialog_turn(state, bot_text=body)

    summary_text = format_brief_update_message(
        brief, event_number=event_number, missing=missing
    )
    step_label = "отправка брифа" if flow_step == "organizer_dump" else "уточнение брифа"
    await emit_parse_log(
        message.bot,
        message,
        role="organizer",
        event_number=event_number if isinstance(event_number, int) else None,
        step_label=step_label,
        user_text=text,
        brief=brief,
        missing=missing,
        brief_html=summary_text,
    )
    if is_complete:
        await send_next_step_after_brief(message, state)


async def handle_organizer_conversation(
    message: Message,
    state: FSMContext,
    *,
    flow_step: str,
) -> None:
    text = message.text or ""
    history = await save_dialog_turn(state, user_text=text)
    event_code, brief = await resolve_organizer_event_and_brief(message, state)

    incoming, structured = parse_message_to_brief(text, role="organizer")
    brief_updated = message_intent.has_substantive_parsed_fields(incoming)
    merger_conflicts: List[str] = list((brief or {}).get("group_conflicts") or [])
    change_info = {"added_fields": [], "updated_fields": []}
    if brief_updated:
        previous_brief = dict(brief)
        event = EVENTS.get(event_code, {}) if event_code else {}
        has_prior_dump = isinstance(event.get("organizer_dump"), str) and bool(
            event.get("organizer_dump", "").strip()
        )
        brief = brief_parser.merge_organizer_incoming(
            brief,
            incoming,
            flow_step=flow_step,
            has_prior_dump=has_prior_dump,
        )
        change_info = live_response.detect_field_changes(previous_brief, incoming, brief)
        if event_code and event_code in EVENTS:
            if structured:
                EVENTS[event_code]["base_brief_structured"] = structured
            EVENTS[event_code]["brief"] = brief
            touch_event(EVENTS[event_code])
            save_events()
        await state.update_data(brief=brief)

    missing = missing_brief_fields(brief)
    parser_result = live_response.build_parser_result(
        saved=brief_updated,
        confidence=parser_confidence_hint() if brief_updated else 0.0,
        added_fields=change_info["added_fields"],
        updated_fields=change_info["updated_fields"],
        conflicts=merger_conflicts,
    )
    step_human = dialog_context.build_step_context_human(
        role="organizer", flow_step=flow_step, missing=missing
    )
    live_context = build_live_prompt_context(
        role="organizer",
        flow_step="conversation",
        human_status="Живой диалог с организатором",
        allowed_next_action="ask_clarification | continue_flow | none",
        last_system_action="conversation_turn",
        brief=brief,
        missing=missing,
        parser_result=parser_result,
        conflicts=merger_conflicts,
        user_message=text,
        dialog_history=history,
        step_context_human=step_human,
    )
    reply = await answer_live_text(message, live_context, CONVERSATION_FALLBACK_ORGANIZER)
    parts = [reply]
    if brief_updated:
        event_number = EVENTS.get(event_code, {}).get("event_number") if event_code else None
        parts.append(
            format_brief_update_message(
                brief, event_number=event_number, missing=missing
            )
        )
        parts.append(
            "<i>Если хочешь оформить всё разом — пришли одним сообщением даты, состав и бюджет.</i>"
        )
    body = "\n\n".join(parts)
    await message.answer(body, reply_markup=main_menu_keyboard())
    await save_dialog_turn(state, bot_text=body)


async def handle_organizer_mixed(
    message: Message,
    state: FSMContext,
    *,
    flow_step: str,
) -> None:
    text = message.text or ""
    history = await save_dialog_turn(state, user_text=text)
    event_code, brief = await resolve_organizer_event_and_brief(message, state)
    missing = missing_brief_fields(brief)

    intro_context = build_live_prompt_context(
        role="organizer",
        flow_step="mixed",
        human_status="Смешанная реплика: вопрос + факты",
        allowed_next_action="ask_clarification | continue_flow | none",
        last_system_action="mixed_turn",
        brief=brief,
        missing=missing,
        parser_result=live_response.build_parser_result(saved=False, confidence=0.0),
        conflicts=[],
        user_message=text,
        dialog_history=history,
        step_context_human=dialog_context.build_step_context_human(
            role="organizer", flow_step="mixed", missing=missing
        ),
    )
    intro = await answer_live_text(message, intro_context, MIXED_FALLBACK_ORGANIZER)

    brief, missing, event_number, _event_code = await _apply_organizer_brief_from_message(
        message, state, flow_step=flow_step
    )
    brief_parts, is_complete = build_organizer_brief_reply_parts(
        brief,
        flow_step=flow_step,
        event_number=event_number,
        chat_id=message.chat.id,
        missing=missing,
    )
    body = "\n\n".join([intro, *brief_parts])
    await message.answer(body, reply_markup=main_menu_keyboard())
    await save_dialog_turn(state, bot_text=body)
    if is_complete:
        await send_next_step_after_brief(message, state)


async def route_organizer_text_message(
    message: Message,
    state: FSMContext,
    *,
    flow_step: str,
) -> None:
    if await handle_menu_shortcuts(message, state):
        return
    intent = message_intent.classify_message_intent(
        message.text or "",
        role="organizer",
        flow_step=flow_step,
    )
    # На шагах брифа любой фактический ввод идёт в парсер (не в живой диалог).
    if flow_step in {"organizer_dump", "organizer_clarify"}:
        text_stripped = (message.text or "").strip()
        if text_stripped and intent == "conversation":
            intent = "brief_input"
    logging.info("Organizer message intent=%s flow_step=%s", intent, flow_step)
    if intent == "brief_input":
        await handle_organizer_brief_input(message, state, flow_step=flow_step)
    elif intent == "mixed":
        await handle_organizer_mixed(message, state, flow_step=flow_step)
    else:
        await handle_organizer_conversation(message, state, flow_step=flow_step)


async def handle_participant_brief_input(
    message: Message,
    state: FSMContext,
    *,
    prefix: str = "",
    skip_user_history: bool = False,
) -> None:
    if not skip_user_history:
        await save_dialog_turn(state, user_text=message.text or "")
    data = await state.get_data()
    event_code = data.get("event_code")
    if not event_code or event_code not in EVENTS:
        await message.answer("Событие не найдено. Попросите организатора прислать новую ссылку.")
        return

    event = EVENTS[event_code]
    event_number = event.get("event_number")
    base_brief = event.get("brief") or {}
    participant_name = data.get("participant_name") or (
        message.from_user.full_name if message.from_user else str(message.chat.id)
    )
    async with ui_feedback.thinking(message):
        incoming, structured = parse_message_to_brief(
            message.text or "",
            role="participant",
            participant_name=participant_name,
        )
        updated_brief = merge_participant_into_brief(base_brief, incoming, participant_name)
        change_info = live_response.detect_field_changes(base_brief, incoming, updated_brief)
        merger_conflicts: List[str] = list(base_brief.get("group_conflicts") or [])
        if structured:
            participant_inputs = event.get("participant_inputs_structured") or []
            event["participant_inputs_structured"] = brief_pipeline.upsert_participant_input(
                participant_inputs,
                structured,
            )
            merger_conflicts = run_group_merger_for_event(event)
            if merger_conflicts:
                updated_brief["group_conflicts"] = merger_conflicts
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
        top_missing = dialog_context.prioritize_missing(missing)
        missing_text = "\n".join(f"• {html.escape(item)}" for item in top_missing)
        extra = ""
        if len(missing) > len(top_missing):
            extra = (
                f"\n<i>И ещё {len(missing) - len(top_missing)} пункт(а).</i>"
            )
        missing_block = "\n\n🚨 <b>Нужно уточнить</b>\n" f"{missing_text}{extra}"
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
    intro = dialog_context.pick_variant(
        message.chat.id, dialog_context.PARTICIPANT_BRIEF_INTRO_VARIANTS
    )
    lead = f"{prefix}\n\n{intro}" if prefix else intro
    body = f"{lead}\n\n{brief_html}\n\nПроверь, пожалуйста: всё верно?{missing_block}"
    await message.answer(body, reply_markup=participant_confirm_keyboard())
    await save_dialog_turn(state, bot_text=body)


async def handle_participant_conversation(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    event_code = data.get("event_code")
    if not event_code or event_code not in EVENTS:
        await message.answer("Событие не найдено. Попросите организатора прислать новую ссылку.")
        return

    event = EVENTS[event_code]
    event_number = event.get("event_number")
    text = message.text or ""
    history = await save_dialog_turn(state, user_text=text)
    base_brief = event.get("brief") or {}
    participant_name = data.get("participant_name") or (
        message.from_user.full_name if message.from_user else str(message.chat.id)
    )

    incoming, structured = parse_message_to_brief(
        text, role="participant", participant_name=participant_name
    )
    brief_updated = message_intent.has_substantive_parsed_fields(incoming)
    updated_brief = base_brief
    change_info = {"added_fields": [], "updated_fields": []}
    merger_conflicts: List[str] = list((base_brief or {}).get("group_conflicts") or [])
    if brief_updated:
        updated_brief = merge_participant_into_brief(base_brief, incoming, participant_name)
        change_info = live_response.detect_field_changes(base_brief, incoming, updated_brief)
        if structured:
            participant_inputs = event.get("participant_inputs_structured") or []
            event["participant_inputs_structured"] = brief_pipeline.upsert_participant_input(
                participant_inputs,
                structured,
            )
            merger_conflicts = run_group_merger_for_event(event)
            if merger_conflicts:
                updated_brief["group_conflicts"] = merger_conflicts
        event["brief"] = updated_brief
        touch_event(event)
        save_events()

    missing = missing_brief_fields(updated_brief)
    parser_result = live_response.build_parser_result(
        saved=brief_updated,
        confidence=parser_confidence_hint() if brief_updated else 0.0,
        added_fields=change_info["added_fields"],
        updated_fields=change_info["updated_fields"],
    )
    live_context = build_live_prompt_context(
        role="participant",
        flow_step="conversation",
        human_status="Живой диалог с участником",
        allowed_next_action="continue_flow | confirm_brief | none",
        last_system_action="conversation_turn",
        brief=updated_brief,
        missing=missing,
        parser_result=parser_result,
        conflicts=merger_conflicts,
        user_message=text,
        dialog_history=history,
        step_context_human=dialog_context.build_step_context_human(
            role="participant", flow_step="participant_contribute", missing=missing
        ),
    )
    reply = await answer_live_text(message, live_context, CONVERSATION_FALLBACK_PARTICIPANT)
    parts = [reply]
    if brief_updated:
        parts.append(format_brief_for_participant(updated_brief, event_number=event_number))
    body = "\n\n".join(parts)
    await message.answer(body, reply_markup=main_menu_keyboard())
    await save_dialog_turn(state, bot_text=body)


async def handle_participant_mixed(message: Message, state: FSMContext) -> None:
    text = message.text or ""
    history = await save_dialog_turn(state, user_text=text)
    data = await state.get_data()
    event_code = data.get("event_code")
    if not event_code or event_code not in EVENTS:
        await message.answer("Событие не найдено. Попросите организатора прислать новую ссылку.")
        return

    event = EVENTS[event_code]
    base_brief = event.get("brief") or {}
    missing = missing_brief_fields(base_brief)
    intro_context = build_live_prompt_context(
        role="participant",
        flow_step="mixed",
        human_status="Смешанная реплика участника",
        allowed_next_action="continue_flow | none",
        last_system_action="mixed_turn",
        brief=base_brief,
        missing=missing,
        parser_result=live_response.build_parser_result(saved=False, confidence=0.0),
        conflicts=[],
        user_message=text,
        dialog_history=history,
    )
    intro = await answer_live_text(
        message,
        intro_context,
        "Поняла вопрос. Ниже — как это ляжет в бриф.",
    )
    await handle_participant_brief_input(
        message, state, prefix=intro, skip_user_history=True
    )


async def route_participant_text_message(message: Message, state: FSMContext) -> None:
    if await handle_menu_shortcuts(message, state):
        return
    intent = message_intent.classify_message_intent(
        message.text or "",
        role="participant",
        flow_step="participant_contribute",
    )
    logging.info("Participant message intent=%s", intent)
    if intent == "brief_input":
        await handle_participant_brief_input(message, state)
    elif intent == "mixed":
        await handle_participant_mixed(message, state)
    else:
        await handle_participant_conversation(message, state)


def format_brief_unified(
    brief: Dict[str, Any],
    event_number: Optional[int],
    title: str,
    subtitle: str = "",
    *,
    group_conflicts: Optional[List[str]] = None,
    missing: Optional[List[str]] = None,
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
    trip_title = brief_display.get_trip_title(brief)
    if isinstance(event_number, int):
        lines.append(f"<b>{esc(trip_title)}</b> <i>· #{event_number}</i>")
    else:
        lines.append(f"<b>{esc(trip_title)}</b>")
    if subtitle:
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

    core_facts.append(f"💰 <b>Бюджет:</b> {esc(format_budget_display(brief))}")

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

    core_facts.append(
        f"✈️ <b>Перелёт:</b> {esc(format_flight_display(brief, esc=esc, missing=missing))}"
    )
    duration_value = esc(brief_display.normalize_duration_display(brief.get("trip_duration_days_raw")))
    core_facts.append(f"⏳ <b>Длительность:</b> {duration_value}")

    passports_value = esc(brief["passports_status"]) if brief.get("passports_status") else "—"
    core_facts.append(f"🛃 <b>Загранпаспорта:</b> {passports_value}")

    brief_stay_enrich.enrich_stay_from_context(brief)
    scenario_value = esc(brief_stay_enrich.format_stay_experience_display(brief)) or "—"
    style_facts.append(f"🌍 <b>Сценарий и локация:</b> {scenario_value}")

    directions, extra_activity = split_activity_preferences(brief.get("activity_preferences") or [])
    extra_filtered = brief_display.filter_extra_activity_preferences(brief, extra_activity)
    if extra_filtered:
        extra_value = ", ".join(esc(item) for item in extra_filtered)
        style_facts.append(f"🧩 <b>Дополнительные пожелания:</b> {extra_value}")

    party_summary = brief_display.format_party_group_summary(brief)
    if party_summary:
        style_facts.append(f"👥 <b>Группа:</b> {esc(party_summary)}")

    lines.append("\n🧱 <b>Базовые параметры поездки</b>")
    lines.extend([f"• {f}" for f in core_facts])
    lines.append("\n🎯 <b>Пожелания по формату поездки</b>")
    lines.extend([f"• {f}" for f in style_facts])

    conflicts = group_conflicts if group_conflicts is not None else brief.get("group_conflicts")
    if conflicts:
        lines.append("\n⚠️ <b>Расхождения в группе</b>")
        for item in conflicts:
            lines.append(f"• {esc(item)}")

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
            if prefs.get("passports_status"):
                row.append("загранпаспорта: " + esc(prefs["passports_status"]))
            brief_stay_enrich.enrich_stay_from_context(prefs)
            participant_scenario = brief_stay_enrich.format_stay_experience_display(prefs)
            if participant_scenario:
                row.append("сценарий и локация: " + esc(participant_scenario))
            elif prefs.get("climate"):
                row.append("сценарий и локация: " + esc(humanize_climate(prefs["climate"])))
            if prefs.get("activity_preferences"):
                row.append("доп. пожелания: " + ", ".join(esc(item) for item in prefs["activity_preferences"]))
            if prefs.get("constraints_notes"):
                row.append("ограничения: " + ", ".join(esc(item) for item in prefs["constraints_notes"]))
            if not row and prefs.get("context_raw"):
                row.append("свободное описание: " + esc(prefs["context_raw"]))
            if row:
                lines.append(f"• <b>{esc(name)}</b>: " + " · ".join(row))

    return "\n".join(lines)


def format_brief_update_message(
    brief: Dict[str, Any],
    event_number: Optional[int] = None,
    *,
    missing: Optional[List[str]] = None,
) -> str:
    return format_brief_unified(
        brief=brief,
        event_number=event_number,
        title="🌿 <b>Вот что собрала о твоей поездке</b>",
        missing=missing if missing is not None else missing_brief_fields(brief),
    )


def format_brief_for_participant(brief: Dict[str, Any], event_number: Optional[int] = None) -> str:
    return format_brief_unified(
        brief=brief,
        event_number=event_number,
        title="📌 <b>Актуальный бриф поездки</b>",
        missing=missing_brief_fields(brief),
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
        ]
    )


def invite_ready_keyboard(event: Optional[Dict[str, Any]] = None) -> InlineKeyboardMarkup:
    if event:
        ensure_event_invite_link(event)
    invite_link = (event or {}).get("invite_link") if event else None
    if invite_link:
        share_text = (
            invite_share_text_for_event(event)
            if event
            else build_invite_share_text(invite_link)
        )
        share_url = telegram_share_url(invite_link, share_text=share_text)
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📤 Поделиться приглашением", url=share_url)],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться приглашением", callback_data="event:invite_share")],
        ]
    )


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


def invite_waiting_keyboard(event: Optional[Dict[str, Any]] = None) -> InlineKeyboardMarkup:
    """Повторная отправка приглашения — та же кнопка «Поделиться»."""
    return invite_ready_keyboard(event)


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
            [KeyboardButton(text="📂 Мои поездки"), KeyboardButton(text="✨ Новая поездка")],
        ],
        resize_keyboard=True,
        is_persistent=True,
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


def context_snapshot(
    chat_id: int,
    fsm_state: Optional[str],
    *,
    preferred_event_code: Optional[str] = None,
) -> Dict[str, Any]:
    recovered = get_latest_event_for_chat(
        chat_id,
        preferred_organizer_code=preferred_event_code,
    )
    if not recovered:
        return {
            "has_event": False,
            "state": fsm_state or "не определено",
        }
    event_code, event, role = recovered
    if role == "organizer":
        brief = brief_parser.restore_organizer_brief_from_event(event)
    else:
        brief = event.get("brief") or {}
    return {
        "has_event": True,
        "event_code": event_code,
        "event_number": event.get("event_number"),
        "role": role,
        "state": fsm_state or "не определено",
        "invite_ready": bool(event.get("invite_link")),
        "missing_fields": missing_brief_fields(brief),
    }


async def start_handler(message: Message, state: Optional[FSMContext] = None) -> None:
    logging.info("Received /start from chat_id=%s", message.chat.id)
    if state is not None:
        await state.update_data(role="organizer")
    await message.answer(
        format_start_greeting(message.from_user),
        reply_markup=welcome_keyboard(),
    )
    await log_session_action(message.bot, message, "/start", role="organizer")


async def help_handler(message: Message, state: Optional[FSMContext] = None) -> None:
    logging.info("Received /help from chat_id=%s", message.chat.id)
    fsm_state = await state.get_state() if state is not None else None
    preferred_code = None
    if state is not None:
        data = await state.get_data()
        raw = data.get("event_code")
        preferred_code = raw if isinstance(raw, str) else None
    snap = context_snapshot(message.chat.id, fsm_state, preferred_event_code=preferred_code)
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
        f"{BOT_CAPABILITIES_HELP_BLOCK}\n\n"
        "🆘 <b>Помощь</b>\n"
        "Выбери, с чем помочь: продолжить сценарий, разобраться с вводными или решить проблему со ссылкой.\n\n"
        f"{context_block}\n\n"
        f"<i>build: {html.escape(ui_feedback.BOT_UI_VERSION)}</i>",
        reply_markup=help_keyboard(),
    )
    await log_session_action(message.bot, message, "помощь")


async def capabilities_handler(message: Message) -> None:
    logging.info("Capabilities requested by chat_id=%s", message.chat.id)
    await message.answer(BOT_CAPABILITIES_HELP_BLOCK, reply_markup=main_menu_keyboard())
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
        if _chat_id_matches(event.get("organizer_chat_id"), chat_id):
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
    await state.update_data(
        role="organizer",
        organizer_chat_id=message.chat.id,
        brief={},
    )
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
        format_trip_created_organizer_message(event_number),
        reply_markup=main_menu_keyboard(),
    )
    await log_session_action(
        message.bot,
        message,
        "создание события",
        role="organizer",
        event_number=event_number,
    )


async def show_organizer_invite_step(
    message: Message,
    state: FSMContext,
    *,
    event: Optional[Dict[str, Any]] = None,
    event_code: Optional[str] = None,
) -> bool:
    """Показать актуальный шаг «Поделиться приглашением». Возвращает False, если ссылка недоступна."""
    if event is None:
        code = event_code or (await state.get_data()).get("event_code")
        event = EVENTS.get(code) if code else None
    if not event:
        _code, event = await _organizer_event_from_state(state)
    if not event:
        await message.answer(
            "Сначала создай поездку через «✨ Новая поездка».",
            reply_markup=main_menu_keyboard(),
        )
        return False
    ensure_event_invite_link(event)
    if not event.get("invite_link"):
        await message.answer(
            "Ссылка пока недоступна. Перезапусти бота командой /start или создай поездку заново.",
            reply_markup=main_menu_keyboard(),
        )
        return False
    event_number = event.get("event_number")
    await message.answer(
        format_invite_step_message(event_number, event=event),
        reply_markup=invite_ready_keyboard(event),
    )
    await log_session_action(
        message.bot,
        message,
        "показ приглашения",
        role="organizer",
        event_number=event_number,
    )
    await flush_session_milestone(message.bot, message, "invite_shown")
    return True


async def send_next_step_after_brief(message: Message, state: FSMContext) -> None:
    await show_organizer_invite_step(message, state)


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
    is_organizer = _chat_id_matches(event.get("organizer_chat_id"), chat_id)
    is_participant = str(chat_id) in participants

    if not is_organizer and not is_participant:
        await callback.message.answer("У вас нет доступа к этому событию.")
        return

    event_number = event.get("event_number")
    if is_organizer:
        brief = brief_parser.restore_organizer_brief_from_event(event)
        await state.update_data(role="organizer", event_code=event_code, brief=brief)
        await state.set_state(FlowState.organizer_clarify)
        missing = missing_brief_fields(brief)
        await callback.message.answer(
            f"👑 Ты снова в поездке <b>#{event_number if isinstance(event_number, int) else html.escape(event_code)}</b> как организатор.\n\n"
            f"{format_brief_update_message(brief, event_number=event_number, missing=missing)}\n\n"
            + (
                "Продолжай уточнения одним сообщением."
                if missing
                else "Бриф готов — ниже можно снова поделиться приглашением."
            ),
            reply_markup=main_menu_keyboard(),
        )
        if not missing:
            await show_organizer_invite_step(
                callback.message, state, event=event, event_code=event_code
            )
        return

    brief = event.get("brief") or {}
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
    """Старые inline-кнопки invite_link — перенаправляем на актуальный шаг приглашения."""
    await event_invite_share_callback_handler(callback, state)


async def event_invite_share_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await show_organizer_invite_step(callback.message, state)


async def event_invite_sent_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("✅")
    _event_code, event = await _organizer_event_from_state(state)
    await ui_feedback.play_invite_sent_success(
        callback.message,
        reply_markup=invite_waiting_keyboard(event),
    )


async def event_invite_done_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Принято")
    _event_code, event = await _organizer_event_from_state(state)
    await callback.message.answer(
        "⏳ Ждём ответы участников — обновлю бриф, когда кто-то допишет пожелания.",
        reply_markup=invite_waiting_keyboard(event),
    )


async def event_show_brief_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    event_code = data.get("event_code")
    role = data.get("role") or "organizer"
    if not event_code:
        preferred = data.get("event_code")
        recovered = get_latest_event_for_chat(
            callback.message.chat.id,
            preferred_organizer_code=preferred if isinstance(preferred, str) else None,
        )
        if not recovered:
            await callback.message.answer("Пока нет активного брифа. Создай поездку через «✨ Новая поездка».")
            return
        event_code, event, role = recovered
        await state.update_data(event_code=event_code, role=role)
    event = EVENTS.get(event_code)
    if not event:
        await callback.message.answer("Поездка не найдена.")
        return
    if role == "organizer":
        brief = brief_parser.restore_organizer_brief_from_event(event)
    else:
        brief = event.get("brief") or {}
    event_number = event.get("event_number")
    if role == "participant":
        body = format_brief_for_participant(brief, event_number=event_number)
    else:
        body = format_brief_update_message(brief, event_number=event_number)
    await callback.message.answer(body, reply_markup=main_menu_keyboard())


async def resume_latest_trip(message: Message, state: FSMContext, *, from_user: Optional[Any] = None) -> None:
    data = await state.get_data()
    preferred = data.get("event_code")
    recovered = get_latest_event_for_chat(
        message.chat.id,
        preferred_organizer_code=preferred if isinstance(preferred, str) else None,
    )
    if not recovered:
        await message.answer(
            "Пока не вижу активной поездки. Создай новую кнопкой «✨ Новая поездка» или через /start.",
            reply_markup=main_menu_keyboard(),
        )
        return
    event_code, event, role = recovered
    event_number = event.get("event_number")
    if role == "organizer":
        brief = brief_parser.restore_organizer_brief_from_event(event)
        await state.update_data(role="organizer", event_code=event_code, brief=brief)
        missing = missing_brief_fields(brief)
        await state.set_state(FlowState.organizer_clarify)
        await message.answer(
            f"📂 <b>Поездка</b> · #{event_number if isinstance(event_number, int) else '—'}\n\n"
            f"{format_brief_update_message(brief, event_number=event_number)}\n\n"
            "Напиши одним сообщением, что уточнить или дополнить.",
            reply_markup=main_menu_keyboard(),
        )
        if not missing and event.get("invite_link"):
            await show_organizer_invite_step(message, state, event=event, event_code=event_code)
        return
    brief = event.get("brief") or {}
    participant_name = from_user.full_name if from_user and getattr(from_user, "full_name", None) else str(message.chat.id)
    await state.update_data(role="participant", event_code=event_code, participant_name=participant_name)
    await state.set_state(FlowState.participant_contribute)
    await message.answer(
        f"📂 <b>Поездка</b> · #{event_number if isinstance(event_number, int) else '—'}\n\n"
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
    data = await state.get_data()
    preferred = data.get("event_code")
    snap = context_snapshot(
        callback.message.chat.id,
        fsm_state,
        preferred_event_code=preferred if isinstance(preferred, str) else None,
    )
    missing = snap.get("missing_fields") or []
    if not missing:
        await callback.message.answer(
            "✅ Сейчас критичных белых пятен не вижу. Бриф достаточно полный для следующего шага.",
            reply_markup=help_keyboard(),
        )
        return
    top_missing = dialog_context.prioritize_missing(missing)
    missing_text = "\n".join(f"• {html.escape(item)}" for item in top_missing)
    if len(missing) > len(top_missing):
        missing_text += f"\n<i>И ещё {len(missing) - len(top_missing)} пункт(а).</i>"
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
    data = await state.get_data()
    preferred = data.get("event_code")
    snap = context_snapshot(
        callback.message.chat.id,
        fsm_state,
        preferred_event_code=preferred if isinstance(preferred, str) else None,
    )
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
    if not await show_organizer_invite_step(callback.message, state):
        await callback.message.answer(
            "Ссылка ещё не готова. Сначала собери базовый бриф — тогда появится приглашение.",
            reply_markup=help_keyboard(),
        )
        return
    await callback.message.answer(
        "Если участник не может войти — попроси открыть ссылку из приглашения заново "
        "или отправить /start в боте.",
        reply_markup=help_keyboard(),
    )


async def help_my_events_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await my_events_handler(callback.message, state)


async def help_report_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    fsm_state = await state.get_state()
    data = await state.get_data()
    preferred = data.get("event_code")
    snap = context_snapshot(
        callback.message.chat.id,
        fsm_state,
        preferred_event_code=preferred if isinstance(preferred, str) else None,
    )
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
        existing_code = resolve_organizer_event_code(callback.message.chat.id, None)
        if existing_code:
            await restore_organizer_fsm_state(state, existing_code)
            await resume_latest_trip(callback.message, state, from_user=callback.from_user)
            return
        event_code = await bootstrap_organizer_event(callback.message, state)
        event_number = (EVENTS.get(event_code) or {}).get("event_number")
        await callback.message.answer(
            format_trip_created_organizer_message(event_number),
            reply_markup=main_menu_keyboard(),
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
        format_participant_join_welcome_message(message.from_user, event_brief),
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
    try:
        await route_participant_text_message(message, state)
    except Exception as err:
        logging.exception("participant_contribute_handler failed: %s", err)
        await message.answer(
            "Не удалось обработать сообщение. Попробуй написать пожелания одним сообщением.",
            reply_markup=main_menu_keyboard(),
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
            reply_markup=invite_waiting_keyboard(event),
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
        logging.info("Organizer dump received chat_id=%s", message.chat.id)
        await route_organizer_text_message(message, state, flow_step="organizer_dump")
    except Exception as err:
        logging.exception("organizer_dump_handler failed: %s", err)
        await message.answer(
            "Не удалось обработать сообщение с первого раза.\n"
            "Отправьте, пожалуйста, вводные ещё раз одним сообщением.",
            reply_markup=main_menu_keyboard(),
        )


async def organizer_clarify_handler(message: Message, state: FSMContext) -> None:
    try:
        await route_organizer_text_message(message, state, flow_step="organizer_clarify")
    except Exception as err:
        logging.exception("organizer_clarify_handler failed: %s", err)
        await message.answer(
            "Не получилось обработать уточнение.\n"
            "Попробуйте написать проще, например: «до 250к, июль, 2 взрослых, без визы».",
            reply_markup=main_menu_keyboard(),
        )


async def text_fallback_handler(message: Message, state: FSMContext) -> None:
    load_events()
    logging.info(
        "Text fallback chat_id=%s state=%s text=%s",
        message.chat.id,
        await state.get_state(),
        (message.text or "")[:80],
    )
    normalized = normalize_text(message.text or "")
    if normalized in {"начать", "start", "/start"}:
        await start_handler(message, state)
        return
    if await handle_menu_shortcuts(message, state):
        return

    data = await state.get_data()
    preferred = data.get("event_code")
    recovered = get_latest_event_for_chat(
        message.chat.id,
        preferred_organizer_code=preferred if isinstance(preferred, str) else None,
    )
    if recovered:
        event_code, event, role = recovered
        if role == "organizer":
            flow_step = await restore_organizer_fsm_state(state, event_code)
            await route_organizer_text_message(message, state, flow_step=flow_step)
            return
        if role == "participant":
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
            await route_participant_text_message(message, state)
            return

    if text_looks_like_brief_submission(message.text or ""):
        event_code = await bootstrap_organizer_event(message, state)
        flow_step = await restore_organizer_fsm_state(state, event_code)
        await route_organizer_text_message(message, state, flow_step=flow_step)
        return

    await message.answer(
        "Чтобы продолжить, выбери действие в меню ниже или напиши вводные по поездке одним сообщением.",
        reply_markup=main_menu_keyboard(),
    )


async def cancel_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Ок, прервала текущий ввод. Вернуться к поездке можно через «📂 Мои поездки».",
        reply_markup=main_menu_keyboard(),
    )


def log_runtime_flags() -> None:
    live_on = env_util.env_flag("USE_LLM_LIVE_RESPONSES")
    mode = get_parser_mode()
    has_key = llm_available()
    logging.info(
        "Runtime flags: live_responses=%s parser_mode=%s llm_api_key=%s",
        live_on,
        mode,
        "set" if has_key else "MISSING",
    )
    if live_on and not has_key:
        logging.warning(
            "USE_LLM_LIVE_RESPONSES is on but LLM_API_KEY is missing — live texts will use fallbacks"
        )


async def main() -> None:
    load_dotenv()
    log_runtime_flags()
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
    dp.message.register(participant_contribute_handler, FlowState.participant_contribute, F.text)
    dp.message.register(organizer_dump_handler, FlowState.organizer_dump, F.text)
    dp.message.register(organizer_clarify_handler, FlowState.organizer_clarify, F.text)
    dp.message.register(current_trip_handler, F.text.func(is_current_trip_text))
    dp.message.register(new_event_handler, F.text.func(is_create_event_text))
    dp.message.register(my_events_handler, F.text.func(is_my_events_text))
    dp.message.register(help_handler, F.text.func(is_help_text))
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

    backfill_invite_links()

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
