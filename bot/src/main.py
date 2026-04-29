import asyncio
import html
import json
import logging
import os
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path
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
EVENTS_FILE = (Path(__file__).resolve().parent.parent / "data" / "events.json")
PROMPTS_DIR = (Path(__file__).resolve().parent.parent / "prompts")
BRIEF_PARSER_PROMPT_FILE = (PROMPTS_DIR / "brief_parser_system_prompt.md")
_BRIEF_PARSER_PROMPT_CACHE: Optional[str] = None


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
    global _BRIEF_PARSER_PROMPT_CACHE
    if _BRIEF_PARSER_PROMPT_CACHE is not None:
        return _BRIEF_PARSER_PROMPT_CACHE
    try:
        _BRIEF_PARSER_PROMPT_CACHE = BRIEF_PARSER_PROMPT_FILE.read_text(encoding="utf-8")
    except Exception as err:
        logging.warning("Failed to load brief parser prompt: %s", err)
        _BRIEF_PARSER_PROMPT_CACHE = ""
    return _BRIEF_PARSER_PROMPT_CACHE


def parse_brief_with_llm(text: str) -> Dict[str, Any]:
    enabled = (os.getenv("USE_LLM_BRIEF_PARSER", "false").strip().lower() == "true")
    api_key = os.getenv("LLM_API_KEY")
    if not enabled or not api_key:
        return {}

    prompt = get_brief_parser_prompt()
    if not prompt:
        return {}

    model = os.getenv("LLM_PARSER_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": (text or "").strip()},
        ],
        "temperature": 0,
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
        if not content:
            return {}
        result = json.loads(content)
        if isinstance(result, dict):
            return result
        return {}
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError, TimeoutError) as err:
        logging.warning("LLM brief parser unavailable, fallback to rule-based parser: %s", err)
        return {}


def load_events() -> None:
    global EVENTS
    try:
        if not EVENTS_FILE.exists():
            EVENTS = {}
            return
        raw = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
        loaded: Dict[str, Dict[str, Any]] = {}
        for code, event in raw.items():
            row = dict(event or {})
            participants = row.get("participants") or {}
            participant_updates = row.get("participant_updates") or {}
            event_number = row.get("event_number")
            # Backward compatibility for old storage where participants was a list/set.
            if isinstance(participants, list):
                participants = {
                    str(chat_id): {"role": "participant", "joined_at": row.get("created_at")}
                    for chat_id in participants
                }
            # Normalize participant_updates keys to string chat_id.
            if isinstance(participant_updates, dict):
                participant_updates = {
                    str(chat_id): dict(payload or {})
                    for chat_id, payload in participant_updates.items()
                }
            row["participants"] = participants
            row["participant_updates"] = participant_updates
            if not isinstance(event_number, int):
                row["event_number"] = None
            loaded[code] = row

        # Backfill event_number for old records to keep stable numbering in UI.
        numbered = [e.get("event_number") for e in loaded.values() if isinstance(e.get("event_number"), int)]
        current_max = max(numbered) if numbered else 0
        for code, event in loaded.items():
            if not isinstance(event.get("event_number"), int):
                current_max += 1
                event["event_number"] = current_max
        EVENTS = loaded
    except Exception as err:
        logging.warning("Failed to load events from disk: %s", err)
        EVENTS = {}


def save_events() -> None:
    try:
        EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        EVENTS_FILE.write_text(
            json.dumps(EVENTS, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as err:
        logging.warning("Failed to save events to disk: %s", err)


def normalize_text(value: str) -> str:
    text = (value or "").strip().lower()
    for token in ["ℹ️", "ℹ", "🆘", "➕", "✨", "📂"]:
        text = text.replace(token, "")
    return " ".join(text.split())


def is_capabilities_text(value: str) -> bool:
    return normalize_text(value) == "что умеет бот"


def is_help_text(value: str) -> bool:
    return normalize_text(value) == "помощь"


def is_create_event_text(value: str) -> bool:
    return normalize_text(value) == "создать событие"


def is_my_events_text(value: str) -> bool:
    return normalize_text(value) == "мои события"


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
    t = (text or "").lower()
    brief: Dict[str, Any] = {}
    # Raw context can be useful internally for debugging, but we should not echo it back to the user.
    brief["context_raw"] = (text or "").strip()

    # Budget: "до 250к", "250 000", "250тыс"
    import re

    budget_value = None
    budget_suffix = ""

    # Case A: explicit budget mention.
    m_budget = re.search(
        r"бюджет(?:ом)?\s*(?:до)?\s*(\d[\d\s]{1,8})\s*(к|т|тыс|тысяч|млн|миллион[а-я]*|000|руб|₽)?",
        t,
    )
    if m_budget:
        budget_value = int(re.sub(r"\s+", "", m_budget.group(1)))
        budget_suffix = (m_budget.group(2) or "").strip()
    else:
        # Case B: monetary phrase without word "бюджет", but with explicit money marker.
        m_money = re.search(
            r"до\s*(\d[\d\s]{1,8})\s*(к|т|тыс|тысяч|млн|миллион[а-я]*|000|руб|₽)",
            t,
        )
        if m_money:
            budget_value = int(re.sub(r"\s+", "", m_money.group(1)))
            budget_suffix = (m_money.group(2) or "").strip()

    if budget_value is not None:
        num = budget_value
        suffix = budget_suffix
        if suffix in {"к", "т", "тыс", "тысяч"}:
            num *= 1000
        elif suffix.startswith("млн") or suffix.startswith("миллион"):
            num *= 1_000_000
        elif suffix in {"руб", "₽", "000"}:
            # already in rubles / thousands encoded
            pass
        elif not suffix and num <= 1000:
            # For travel chats, "бюджет 250" is usually shorthand for 250k.
            num *= 1000
        brief["budget_rub_max"] = num

    # Adults / kids: "2 взрослых", "1 ребенок 6", "ребёнок 6 лет"
    m = re.search(r"(\d+)\s*взросл", t)
    if m:
        brief["adults"] = int(m.group(1))
    m = re.search(r"(\d+)\s*девуш", t)
    if m:
        brief["adults"] = int(m.group(1))
    m = re.search(r"(\d+)\s*коллег", t)
    if m:
        brief["adults"] = int(m.group(1))
    m = re.search(r"(\d+)\s*(?:дет|реб)", t)
    if m:
        brief["kids_count"] = int(m.group(1))
    m = re.search(r"(?:реб[её]нок|дет[а-я]*)\s*(\d{1,2})\s*(?:лет|года?)", t)
    if m:
        brief["kid_age"] = int(m.group(1))

    # Dates/months: very lightweight capture
    months = [
        "январ", "феврал", "март", "апрел", "май", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"
    ]
    for mon in months:
        if mon in t:
            brief.setdefault("months", []).append(mon)

    # Explicit date ranges: "10-15 июля", "с 10 по 15", "10.07-15.07"
    m = re.search(r"(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?\s*[-–]\s*(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?", t)
    if m:
        brief["date_range_raw"] = m.group(0)
    m = re.search(r"(?:с\s*)?(\d{1,2})\s*(?:по|[-–])\s*(\d{1,2})\s*(январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья])", t)
    if m:
        brief["date_range_raw"] = m.group(0)
    m = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(?:дн|дней|дня)", t)
    if m:
        brief["trip_duration_days_raw"] = f"{m.group(1)}-{m.group(2)} дней"
    else:
        m = re.search(r"(\d{1,2})\s*(?:дн|дней|дня)", t)
        if m:
            brief["trip_duration_days_raw"] = f"{m.group(1)} дней"

    # Flight duration: "до 5 часов"
    m = re.search(r"(?:до|не\s*больше)\s*(\d{1,2})\s*(?:ч|час)", t)
    if m:
        brief["flight_hours_max"] = int(m.group(1))
    if "можно с пересад" in t or "пересадки можно" in t or "пересадки ок" in t or "пересадки норм" in t:
        brief["transfers_allowed"] = True
    if "без пересад" in t or "прямой рейс" in t:
        brief["transfers_allowed"] = False

    # Visa constraint
    if "без виз" in t:
        brief["visa_required"] = False
    elif "виза" in t:
        brief["visa_required"] = True

    # Passports (загранпаспорта)
    if "загран" in t or "заграничн" in t:
        # If passports are discussed, visas/documents are in scope.
        brief.setdefault("documents_discussed", True)
        # coarse status
        if "нет" in t and ("загран" in t or "заграничн" in t):
            brief["passports_status"] = "не у всех есть"
        if "есть" in t and ("загран" in t or "заграничн" in t):
            brief["passports_status"] = "есть"
        if "срок" in t and ("загран" in t or "заграничн" in t):
            brief.setdefault("passports_notes", [])
            brief["passports_notes"].append("проверить срок действия загранпаспорта")

    # Visa nuances (France/Schengen)
    if "шенген" in t or "шэнген" in t or "франц" in t:
        brief.setdefault("visa_notes", [])
        brief.setdefault("documents_discussed", True)
        # Schengen/France implies visa topic even if word "виза" isn't used.
        brief.setdefault("visa_required", True)
        if "франц" in t:
            brief["visa_notes"].append("направление/виза: Франция (Шенген)")
        elif "шенген" in t or "шэнген" in t:
            brief["visa_notes"].append("виза: Шенген")
    if "виза есть" in t or "виза готов" in t:
        brief.setdefault("documents_discussed", True)
        brief["visa_status"] = "есть"
    if "виза нет" in t or "визы нет" in t or "делаем визу" in t or "оформляем визу" in t:
        brief.setdefault("documents_discussed", True)
        brief["visa_status"] = "нужно оформить"

    # Conflict signal (don't store/echo the full user text)
    if "не можем" in t or "не получается" in t or "спор" in t or "конфликт" in t:
        brief.setdefault("constraints_notes", [])
        if "есть разные мнения в группе" not in brief["constraints_notes"]:
            brief["constraints_notes"].append("есть разные мнения в группе — важно найти компромисс")
    prefs = []
    if "переплач" in t:
        prefs.append("ограничение: не переплачивать")
    if "пересад" in t:
        prefs.append("ограничение: без длинных пересадок")
    if prefs:
        brief["constraints_notes"] = prefs

    # Party preferences (очень легкий разбор ролей: папа/брат/жена брата/я)
    parties: Dict[str, Dict[str, Any]] = {}
    def ensure_party(name: str) -> Dict[str, Any]:
        parties.setdefault(name, {})
        return parties[name]

    if "папа" in t:
        p = ensure_party("папа")
        if "переплач" in t or "дорого" in t:
            p["constraint"] = "не переплачивать"
        if "бюджет" in t:
            p.setdefault("notes", []).append("важен бюджет")
    if "брат" in t:
        b = ensure_party("брат_и_жена")
        if "пересад" in t:
            b.setdefault("constraints", []).append("без длинных пересадок")
        if "море" in t or "пляж" in t:
            b.setdefault("wants", []).append("на море")
    if "франц" in t or "во францию" in t:
        me = ensure_party("организатор")
        me.setdefault("wants", []).append("Франция")

    if parties:
        brief["party_preferences"] = parties

    # Climate/type
    if "море" in t or "пляж" in t:
        brief["climate"] = "море/пляж"
    if "горы" in t:
        brief["climate"] = "горы"
    if "экскурс" in t or "музе" in t:
        brief["trip_type"] = "экскурсии/город"
    if "all inclusive" in t or "оллинклюзив" in t or "всё включено" in t:
        brief["trip_type"] = "всё включено"

    # Specific activity/place preferences often mentioned by participants.
    activity_preferences = []
    if "ази" in t:
        activity_preferences.append("предпочтение по направлению: Азия")
    if "европ" in t:
        activity_preferences.append("предпочтение по направлению: Европа")
    if "песчан" in t and ("пляж" in t or "море" in t):
        activity_preferences.append("песчаный пляж")
    if "достопримеч" in t or "экскурс" in t:
        activity_preferences.append("поездки к достопримечательностям")
    if (
        ("машин" in t or "авто" in t or "на машине" in t)
        and ("достопримеч" in t or "экскурс" in t or "посмотреть" in t or "покат" in t)
    ):
        activity_preferences.append("поездки на машине к достопримечательностям")
    if "ресторан" in t or "гастроном" in t or "кафе" in t:
        activity_preferences.append("рестораны и локальная еда")
    if activity_preferences:
        brief["activity_preferences"] = activity_preferences

    return brief


def extract_brief_from_text(text: str) -> Dict[str, Any]:
    # Keep deterministic parser as baseline and optionally enrich via LLM parser.
    # If LLM parser is unavailable, behavior stays unchanged.
    rule_based = extract_brief_rule_based(text)
    llm_brief = parse_brief_with_llm(text)
    return merge_brief(llm_brief, rule_based)


def merge_brief(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base or {})
    for k, v in (incoming or {}).items():
        if v is None:
            continue
        if k == "months":
            out.setdefault("months", [])
            for item in v:
                if item not in out["months"]:
                    out["months"].append(item)
            continue
        if k in {"visa_notes", "constraints_notes", "activity_preferences"}:
            out.setdefault(k, [])
            for item in v:
                if item not in out[k]:
                    out[k].append(item)
            continue
        if k in {"passports_notes"}:
            out.setdefault(k, [])
            for item in v:
                if item not in out[k]:
                    out[k].append(item)
            continue
        out[k] = v
    return out


def merge_participant_into_brief(
    base: Dict[str, Any],
    incoming: Dict[str, Any],
    participant_name: str,
) -> Dict[str, Any]:
    # Participant input should enrich the event brief, but should not blindly overwrite
    # organizer's already fixed core fields (especially budget and trip composition).
    out = dict(base or {})
    immutable_if_set = {
        "budget_rub_max",
        "adults",
        "kids_count",
        "kid_age",
        "months",
        "date_range_raw",
        "flight_hours_max",
        "visa_required",
        "visa_status",
        "passports_status",
        "climate",
        "trip_type",
    }

    for k, v in (incoming or {}).items():
        if v is None:
            continue
        if k in {"months", "visa_notes", "constraints_notes", "passports_notes", "activity_preferences"}:
            out.setdefault(k, [])
            for item in v:
                if item not in out[k]:
                    out[k].append(item)
            continue
        if k in immutable_if_set and k in out and out.get(k):
            continue
        out[k] = v

    # Keep participant-specific preference visible without rewriting organizer base fields.
    out.setdefault("participant_preferences", {})
    out["participant_preferences"][participant_name] = incoming
    return out


def missing_brief_fields(brief: Dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not brief.get("months"):
        missing.append("Окна дат (месяц/период) или гибкость")
    if not brief.get("budget_rub_max"):
        missing.append("Бюджет (хотя бы «до … ₽»)")
    if not brief.get("adults") and not brief.get("kids_count"):
        missing.append("Кто едет (взрослые/дети)")
    if not brief.get("flight_hours_max") and ("transfers_allowed" not in brief):
        missing.append("Ограничение по перелёту (например, «до 5 часов»)")
    # Visas/documents: consider answered if user mentioned visa status/notes/passports
    documents_answered = (
        ("visa_required" in brief)
        or bool(brief.get("visa_status"))
        or bool(brief.get("visa_notes"))
        or bool(brief.get("passports_status"))
        or bool(brief.get("passports_notes"))
        or bool(brief.get("documents_discussed"))
    )
    if not documents_answered:
        missing.append("Визы/документы (например, «без визы» / «нужен Шенген» / «загранпаспорта у всех есть»)")
    # If visa is relevant, passports are too
    if brief.get("visa_required") is True and not brief.get("passports_status"):
        missing.append("Загранпаспорта у участников (есть ли у всех / срок действия)")
    if not brief.get("climate") and not brief.get("trip_type"):
        missing.append("Климат или тип отдыха (море/горы/город/санаторий и т.п.)")
    return missing


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
            [InlineKeyboardButton(text="✨ Создать событие", callback_data="event:create")],
        ]
    )


def organizer_next_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✨ Создать событие", callback_data="event:create")],
        ]
    )


def invite_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📩 Показать ссылку для участников", callback_data="event:invite")],
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
    # Простое меню (не inline), чтобы всегда было под рукой.
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✨ Создать событие")],
            [KeyboardButton(text="📂 Мои события")],
            [KeyboardButton(text="ℹ️ Что умеет бот"), KeyboardButton(text="🆘 Помощь")],
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
            [InlineKeyboardButton(text="📂 Мои события", callback_data="help:myevents")],
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
        "👋 <b>Привет! Я помогаю спокойно и быстро собрать вводные по поездке — без бесконечных уточнений в чате.</b>\n"
        "Подойду, если вы планируете поездку с семьёй, друзьями или коллегами и хотите перейти от разрозненных сообщений к понятному плану.\n\n"
        "⚙️ <b>Как это работает</b>\n"
        "1) вы создаёте событие и отправляете вводные одним сообщением\n"
        "2) участники подключаются по ссылке и добавляют свои пожелания\n"
        "3) я собираю всё в единый бриф, чтобы сразу видеть общую картину.\n\n"
        "👑 <b>Ваша роль — организатор</b>\n"
        "Организатор — тот, кто создаёт событие: задаёт базовые параметры и приглашает участников.",
        reply_markup=welcome_keyboard(),
    )


async def help_handler(message: Message, state: Optional[FSMContext] = None) -> None:
    logging.info("Received /help from chat_id=%s", message.chat.id)
    fsm_state = await state.get_state() if state is not None else None
    snap = context_snapshot(message.chat.id, fsm_state)
    if snap.get("has_event"):
        event_number = snap.get("event_number")
        event_label = f"#{event_number}" if isinstance(event_number, int) else "без номера"
        role_label = "организатор" if snap.get("role") == "organizer" else "участник"
        context_block = (
            "🧭 <b>Ваш контекст</b>\n"
            f"• Событие: <b>{event_label}</b>\n"
            f"• Роль: <b>{role_label}</b>\n"
            f"• Этап: <b>{html.escape(str(snap.get('state') or 'не определено'))}</b>"
        )
    else:
        context_block = (
            "🧭 <b>Ваш контекст</b>\n"
            f"• Этап: <b>{html.escape(str(snap.get('state') or 'не определено'))}</b>\n"
            "• Активное событие пока не найдено."
        )

    await message.answer(
        "🆘 <b>Помощь</b>\n"
        "Выберите, с чем помочь: продолжить сценарий, разобраться с парсером или решить техническую проблему.\n\n"
        f"{context_block}",
        reply_markup=help_keyboard(),
    )


async def capabilities_handler(message: Message) -> None:
    logging.info("Capabilities requested by chat_id=%s", message.chat.id)
    await message.answer(
        "Я помогаю группе договориться без хаоса в переписке: собираю вводные в единый бриф и показываю общую картину.\n\n"
        "Сейчас я умею:\n"
        "1) принять вводные от организатора одним сообщением и уточнить только недостающее\n"
        "2) подключить участников по ссылке и собрать их пожелания\n"
        "3) собрать общую сводку и подсветить, где ожидания расходятся\n"
        "4) сохранить прогресс события, чтобы вы могли вернуться к нему позже.\n\n"
        "Этап рекомендаций по направлениям — следующий шаг развития."
    )


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
    if event.get("completed_at"):
        return {"key": "completed", "icon": "✅", "short": "завершено"}
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
        "📂 <b>Мои события</b>\n"
        "Показываю актуальные события с ролью, статусом и следующим действием.\n"
        "Выберите событие, чтобы продолжить:",
        reply_markup=my_events_keyboard(items),
    )


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
        "Событие создано ✅\n"
        f"Номер события: <b>#{event_number}</b>\n\n"
        "Опишите вводные по поездке одним сообщением."
        "\n\n"
        "📝 <b>Пример</b>\n"
        "«2 взрослых + ребёнок 6 лет, июль/август, море, бюджет до 250к, перелёт до 5 часов, без визы»\n\n"
        "Можно писать в свободной форме — я структурирую текст и соберу бриф.",
        reply_markup=main_menu_keyboard(),
    )


async def send_next_step_after_brief(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    event_code = data.get("event_code")
    event = EVENTS.get(event_code) if event_code else None
    invite_link = event.get("invite_link") if event else None

    await message.answer(
        "Чтобы учесть мнения всех участников, осталось отправить приглашение.\n\n"
        "Что сделать вам:\n"
        "1) отправьте ссылку участникам\n"
        "2) попросите их перейти по кнопке и ответить на короткие вопросы\n"
        "3) после ответов я обновлю общий бриф и подсвечу расхождения, если они будут.",
        reply_markup=invite_keyboard(),
    )


async def send_next_step_after_brief_by_event(message: Message, event_code: str) -> None:
    event = EVENTS.get(event_code) if event_code else None
    invite_link = event.get("invite_link") if event else None
    await message.answer(
        "Чтобы учесть мнения всех участников, осталось отправить приглашение.\n\n"
        "Что сделать вам:\n"
        "1) отправьте ссылку участникам\n"
        "2) попросите их перейти по кнопке и ответить на короткие вопросы\n"
        "3) после ответов я обновлю общий бриф и подсвечу расхождения, если они будут.",
        reply_markup=invite_keyboard(),
    )

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
            f"👑 Вы вернулись в событие <b>{html.escape(event_code)}</b> как организатор.\n\n"
            f"{format_brief_update_message(brief, event_number=event_number)}\n\n"
            "Можете продолжить уточнения одним сообщением.",
            reply_markup=main_menu_keyboard(),
        )
        return

    participant_name = (
        callback.from_user.full_name if callback.from_user else str(chat_id)
    )
    await state.update_data(role="participant", event_code=event_code, participant_name=participant_name)
    await state.set_state(FlowState.participant_contribute)
    await callback.message.answer(
        f"👤 Вы вернулись в событие <b>{html.escape(event_code)}</b> как участник.\n\n"
        f"{format_brief_for_participant(brief, event_number=event_number)}\n\n"
        "Напишите одним сообщением, что хотите дополнить в брифе.",
        reply_markup=main_menu_keyboard(),
    )


async def event_invite_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    event_code = data.get("event_code")
    event = EVENTS.get(event_code) if event_code else None
    invite_link = event.get("invite_link") if event else None
    if not invite_link:
        await callback.message.answer(
            "Ссылка пока недоступна. Попробуйте чуть позже — если не сработает, напишите /start.",
            reply_markup=main_menu_keyboard(),
        )
        return
    await callback.message.answer(
        "Готово. Отправьте эту ссылку участникам:\n"
        f"{invite_link}"
    )


async def help_continue_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    recovered = get_latest_event_for_chat(callback.message.chat.id)
    if not recovered:
        await callback.message.answer(
            "Пока не вижу активного события. Создайте новое событие кнопкой «✨ Создать событие».",
            reply_markup=main_menu_keyboard(),
        )
        return
    event_code, event, role = recovered
    brief = event.get("brief") or {}
    event_number = event.get("event_number")
    if role == "organizer":
        await state.update_data(role="organizer", event_code=event_code, brief=brief)
        await state.set_state(FlowState.organizer_clarify)
        await callback.message.answer(
            f"🔁 Продолжаем событие <b>#{event_number if isinstance(event_number, int) else '—'}</b>.\n\n"
            f"{format_brief_update_message(brief, event_number=event_number)}\n\n"
            "Напишите одним сообщением, что хотите уточнить или дополнить.",
            reply_markup=main_menu_keyboard(),
        )
        return
    participant_name = (
        callback.from_user.full_name if callback.from_user and callback.from_user.full_name else str(callback.message.chat.id)
    )
    await state.update_data(role="participant", event_code=event_code, participant_name=participant_name)
    await state.set_state(FlowState.participant_contribute)
    await callback.message.answer(
        f"🔁 Продолжаем событие <b>#{event_number if isinstance(event_number, int) else '—'}</b>.\n\n"
        f"{format_brief_for_participant(brief, event_number=event_number)}\n\n"
        "Напишите одним сообщением, что важно лично вам.",
        reply_markup=main_menu_keyboard(),
    )


async def help_parser_callback_handler(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        "📝 <b>Как написать вводные</b>\n"
        "Пишите свободно, одним сообщением. Я сама разложу текст по полям.\n\n"
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
        "Можете ответить одним сообщением в свободной форме.",
        reply_markup=help_keyboard(),
    )


async def help_link_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    fsm_state = await state.get_state()
    snap = context_snapshot(callback.message.chat.id, fsm_state)
    if not snap.get("has_event"):
        await callback.message.answer(
            "Сначала создайте событие, и я дам кнопку со ссылкой для участников.",
            reply_markup=help_keyboard(),
        )
        return
    if snap.get("role") != "organizer":
        await callback.message.answer(
            "Ссылку отправляет организатор. Если не получили её, попросите организатора нажать «📩 Показать ссылку для участников».",
            reply_markup=help_keyboard(),
        )
        return
    if not snap.get("invite_ready"):
        await callback.message.answer(
            "Ссылка ещё не готова. Заполните базовый бриф, и кнопка для приглашения станет доступной.",
            reply_markup=help_keyboard(),
        )
        return
    await callback.message.answer(
        "Если участник не может войти:\n"
        "1) попросите открыть ссылку заново\n"
        "2) попросите отправить /start в боте\n"
        "3) при необходимости нажмите «📩 Показать ссылку для участников» ещё раз.",
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
        "Отправьте одним сообщением:\n"
        "1) что вы нажали\n"
        "2) что ожидали увидеть\n"
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
            "Отлично. Раз вы создаёте событие — вы организатор.\n\n"
            "Нажмите кнопку ниже, чтобы создать событие и начать сбор вводных.",
            reply_markup=organizer_next_keyboard(),
        )
        return

    await state.update_data(role="participant")
    await callback.message.answer(
        "Вы — участник. Чтобы войти в событие, откройте ссылку от организатора.\n\n"
        "Когда вы заходите по ссылке, я подключаю вас к событию и задам короткие вопросы по вашим предпочтениям.",
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
            "Похоже, ссылка устарела или событие уже не активно.\n"
            "Попросите организатора прислать новую ссылку."
        )
        return

    participants = event.setdefault("participants", {})
    participants[str(message.chat.id)] = {
        "role": "participant",
        "name": (message.from_user.full_name if message.from_user else str(message.chat.id)),
        "username": (message.from_user.username if message.from_user else None),
        "joined_at": now_ts(),
    }
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
        "✅ <b>Вы подключены к событию поездки.</b>\n"
        f"Номер события: <b>#{event_number if isinstance(event_number, int) else '—'}</b>\n\n"
        "Вас пригласил организатор, чтобы собрать мнения участников и согласовать общий бриф.\n\n"
        "👤 <b>Ваша роль — участник</b>\n"
        "Вы добавляете личные пожелания и ограничения, а я встраиваю их в общую картину без потери важных деталей.\n\n"
        "✍️ <b>Что сделать сейчас</b>\n"
        "Прочитайте текущий бриф ниже и дополните его одним сообщением:\n"
        "что важно лично вам (бюджет, даты, перелёт, документы, климат, формат отдыха)."
    )
    await message.answer(
        f"{format_brief_for_participant(event_brief, event_number=event_number)}"
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
    incoming = extract_brief_from_text(message.text or "")
    participant_name = data.get("participant_name") or (
        message.from_user.full_name if message.from_user else str(message.chat.id)
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

    await state.set_state(FlowState.participant_confirm)
    missing = missing_brief_fields(updated_brief)
    missing_block = ""
    if missing:
        missing_text = "\n".join(f"• {html.escape(item)}" for item in missing)
        missing_block = (
            "\n\n🚨 <b>Нужно уточнить</b>\n"
            f"{missing_text}"
        )
    await message.answer(
        "Спасибо, добавила ваши вводные в бриф.\n\n"
        f"{format_brief_for_participant(updated_brief, event_number=event_number)}\n\n"
        f"Проверьте, пожалуйста: всё верно?{missing_block}",
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
        "Принято, спасибо ✅\n"
        "Отправляю обновлённый бриф организатору."
    )

    organizer_chat_id = event.get("organizer_chat_id")
    if organizer_chat_id:
        username = callback.from_user.username if callback.from_user else None
        user_caption = f"@{username}" if username else participant_name
        await callback.bot.send_message(
            organizer_chat_id,
            "🔔 <b>Обновление от участника</b>\n\n"
            f"{html.escape(user_caption)} дополнил(а) бриф и подтвердил(а), что всё верно.\n\n"
            f"{format_brief_for_participant(event.get('brief') or {}, event_number=event.get('event_number'))}",
        )


async def participant_edit_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(FlowState.participant_contribute)
    await callback.message.answer(
        "Хорошо, напишите одним сообщением, что нужно уточнить или добавить в бриф."
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

        if event_code and event_code in EVENTS:
            EVENTS[event_code]["organizer_dump"] = text
            EVENTS[event_code]["brief"] = brief
            touch_event(EVENTS[event_code])
            save_events()

        await state.update_data(organizer_dump=text, brief=brief)
        await state.set_state(FlowState.organizer_clarify)

        missing = missing_brief_fields(brief)

        summary_text = format_brief_update_message(brief, event_number=EVENTS.get(event_code, {}).get("event_number"))

        if not missing:
            await message.answer(
                f"{summary_text}\n\n"
                "Отлично, базовых данных достаточно. Переходим к подключению участников.",
                reply_markup=main_menu_keyboard(),
            )
            await send_next_step_after_brief(message, state)
            return

        missing_text = "\n".join(f"- {m}" for m in missing)
        await message.answer(
            f"{summary_text}\n\n"
            "🚨 <b>Уточните только это</b> (можно одним сообщением):\n"
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
        brief = merge_brief(brief, incoming)

        if event_code and event_code in EVENTS:
            EVENTS[event_code]["brief"] = brief
            touch_event(EVENTS[event_code])
            save_events()

        await state.update_data(brief=brief)

        missing = missing_brief_fields(brief)
        if not missing:
            await message.answer(
                "Отлично, спасибо! Данных достаточно. Переходим к подключению участников.",
                reply_markup=main_menu_keyboard(),
            )
            await send_next_step_after_brief(message, state)
            return

        missing_text = "\n".join(f"- {m}" for m in missing)
        await message.answer(
            "🚨 <b>Осталось уточнить:</b>\n"
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
            await message.answer(
                "Спасибо, добавила ваши вводные в бриф.\n\n"
                f"{format_brief_for_participant(updated_brief, event_number=event_number)}\n\n"
                f"Проверьте, пожалуйста: всё верно?{missing_block}",
                reply_markup=participant_confirm_keyboard(),
            )
            return

    await message.answer(
        "Чтобы продолжить, выберите действие в меню ниже.",
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
    dp.message.register(new_event_handler, Command("new"))
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
    dp.callback_query.register(event_invite_callback_handler, F.data == "event:invite")
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
            BotCommand(command="start", description="Запуск бота"),
            BotCommand(command="help", description="Что умеет бот"),
            BotCommand(command="new", description="Создать событие"),
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
