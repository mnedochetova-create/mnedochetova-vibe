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

# In-memory storage for manual testing (will reset on restart).
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
            # Backward compatibility for old storage where participants was a list/set.
            if isinstance(participants, list):
                participants = {
                    str(chat_id): {"role": "participant", "joined_at": row.get("created_at")}
                    for chat_id in participants
                }
            row["participants"] = participants
            loaded[code] = row
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
    for token in ["ℹ️", "ℹ", "🆘", "➕", "✨"]:
        text = text.replace(token, "")
    return " ".join(text.split())


def is_capabilities_text(value: str) -> bool:
    return normalize_text(value) == "что умеет бот"


def is_help_text(value: str) -> bool:
    return normalize_text(value) == "помощь"


def is_my_events_text(value: str) -> bool:
    return normalize_text(value) == "мои события"


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

    # Flight duration: "до 5 часов"
    m = re.search(r"(?:до|не\s*больше)\s*(\d{1,2})\s*(?:ч|час)", t)
    if m:
        brief["flight_hours_max"] = int(m.group(1))

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
    if "хочу" in t:
        prefs.append("есть предпочтение «хочу …»")
    if "хотят" in t or "хочет" in t:
        prefs.append("есть предпочтения других участников")
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
    if not brief.get("flight_hours_max"):
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


def format_brief_update_message(brief: Dict[str, Any]) -> str:
    # Structured summary with richer Telegram-friendly formatting.
    def esc(value: Any) -> str:
        return html.escape(str(value))

    lines: list[str] = []
    lines.append("✨ <b>Черновик брифа обновлён</b>")

    # 1) Preferences by party (if parsed)
    parties = brief.get("party_preferences") or {}
    if parties:
        lines.append("\n👥 <b>Пожелания и ограничения участников</b>")
        for party, data in parties.items():
            row: list[str] = []
            wants = data.get("wants") or []
            constraints = data.get("constraints") or []
            if data.get("constraint"):
                constraints.append(data["constraint"])
            if wants:
                row.append("хочет: " + ", ".join(esc(item) for item in wants))
            if constraints:
                row.append("важно: " + ", ".join(esc(item) for item in constraints))
            notes = data.get("notes") or []
            if notes:
                row.append("заметки: " + ", ".join(esc(item) for item in notes))
            if row:
                lines.append(f"• <b>{esc(party)}</b>: " + " · ".join(row))

    # 2) General wishes/constraints (if any)
    general_notes = brief.get("constraints_notes") or []
    if general_notes:
        lines.append("\n🧭 <b>Общие пожелания и ограничения</b>")
        for item in general_notes:
            lines.append(f"• {esc(item)}")

    # 3) What we already know (facts)
    facts: list[str] = []
    if brief.get("date_range_raw"):
        facts.append(f"📅 <b>Даты:</b> <code>{esc(brief['date_range_raw'])}</code>")
    elif brief.get("months"):
        facts.append("📅 <b>Примерные даты:</b> " + ", ".join(esc(item) for item in brief["months"]))
    if brief.get("budget_rub_max"):
        facts.append(f"💰 <b>Бюджет:</b> до {brief['budget_rub_max']:,} ₽".replace(",", " "))
    if brief.get("flight_hours_max"):
        facts.append(f"✈️ <b>Перелёт:</b> до {esc(brief['flight_hours_max'])} ч.")
    if "visa_required" in brief:
        facts.append("🛂 <b>Визы:</b> " + ("нужна" if brief["visa_required"] else "без визы"))
    if brief.get("visa_status"):
        facts.append("🧾 <b>Статус визы:</b> " + esc(brief["visa_status"]))
    if brief.get("visa_notes"):
        facts.append("📝 <b>Визовые заметки:</b> " + "; ".join(esc(item) for item in brief["visa_notes"]))
    if brief.get("passports_status"):
        facts.append("🛃 <b>Загранпаспорта:</b> " + esc(brief["passports_status"]))
    if brief.get("passports_notes"):
        facts.append("📝 <b>Загранпаспорта:</b> " + "; ".join(esc(item) for item in brief["passports_notes"]))
    if brief.get("climate"):
        facts.append("🌤 <b>Климат:</b> " + esc(brief["climate"]))
    if brief.get("trip_type"):
        facts.append("🏝 <b>Тип отдыха:</b> " + esc(brief["trip_type"]))
    if brief.get("activity_preferences"):
        facts.append("🧩 <b>Дополнительные пожелания:</b> " + ", ".join(esc(item) for item in brief["activity_preferences"]))

    if facts:
        lines.append("\n📌 <b>Что уже известно</b>")
        lines.extend([f"• {f}" for f in facts])

    return "\n".join(lines)


def format_brief_for_participant(brief: Dict[str, Any]) -> str:
    def esc(value: Any) -> str:
        return html.escape(str(value))

    def humanize_climate(value: str) -> str:
        mapping = {
            "море/пляж": "морское направление и пляжный отдых",
            "горы": "горное направление",
        }
        return mapping.get(value, value)

    lines: list[str] = []
    lines.append("📌 <b>Что уже зафиксировано по событию</b>")

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

    core_facts: list[str] = []
    style_facts: list[str] = []
    if brief.get("date_range_raw"):
        core_facts.append(f"📅 <b>Даты:</b> <code>{esc(brief['date_range_raw'])}</code>")
    elif brief.get("months"):
        core_facts.append("📅 <b>Примерные даты:</b> " + ", ".join(esc(item) for item in brief["months"]))
    if brief.get("budget_rub_max"):
        core_facts.append(f"💰 <b>Бюджет:</b> до {brief['budget_rub_max']:,} ₽".replace(",", " "))
    if brief.get("adults") or brief.get("kids_count"):
        parts: list[str] = []
        if brief.get("adults"):
            parts.append(f"{brief['adults']} взрослых")
        if brief.get("kids_count"):
            parts.append(format_kids(int(brief["kids_count"])))
        core_facts.append("👨‍👩‍👧‍👦 <b>Состав:</b> " + ", ".join(parts))
    if brief.get("flight_hours_max"):
        core_facts.append(f"✈️ <b>Перелёт:</b> до {esc(brief['flight_hours_max'])} ч.")
    if "visa_required" in brief:
        core_facts.append("🛂 <b>Визы:</b> " + ("нужна" if brief["visa_required"] else "без визы"))
    if brief.get("passports_status"):
        core_facts.append("🛃 <b>Загранпаспорта:</b> " + esc(brief["passports_status"]))
    if brief.get("climate"):
        style_facts.append("🌤 <b>Климат и локация:</b> " + esc(humanize_climate(brief["climate"])))
    if brief.get("trip_type"):
        style_facts.append("🏝 <b>Формат отдыха:</b> " + esc(brief["trip_type"]))
    if brief.get("activity_preferences"):
        style_facts.append("🧩 <b>Дополнительные пожелания:</b> " + ", ".join(esc(item) for item in brief["activity_preferences"]))

    if core_facts:
        lines.append("\n🧱 <b>Базовые параметры поездки</b>")
        lines.extend([f"• {f}" for f in core_facts])
    if style_facts:
        lines.append("\n🎯 <b>Пожелания по формату поездки</b>")
        lines.extend([f"• {f}" for f in style_facts])
    if not core_facts and not style_facts:
        lines.append("• Пока есть только базовый черновик без деталей.")

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
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{role_icon} {item['code']} · {item['title']}",
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


async def start_handler(message: Message, state: Optional[FSMContext] = None) -> None:
    logging.info("Received /start from chat_id=%s", message.chat.id)
    if state is not None:
        await state.update_data(role="organizer")
    await message.answer(
        "Привет! Я помогаю группе быстро собрать вводные и прийти к короткому списку направлений — без бесконечных уточнений в чате.\n\n"
        "Как это работает:\n"
        "1) вы создаёте событие и пишете вводные одним сообщением\n"
        "2) участники заходят по ссылке и добавляют свои пожелания\n"
        "3) я собираю общую картину и предлагаю 2–3 направления с объяснением.\n\n"
        "Вы — организатор: организатором считается тот, кто создаёт событие.\n"
        "Нажмите кнопку ниже, чтобы начать.",
        reply_markup=main_menu_keyboard(),
    )


async def help_handler(message: Message) -> None:
    logging.info("Received /help from chat_id=%s", message.chat.id)
    await message.answer(
        "Кнопки в меню:\n"
        "— ✨ Создать событие\n"
        "— ℹ️ Что умеет бот\n"
        "— 🆘 Помощь\n\n"
        "Если меню не видно, напишите /start."
    )


async def capabilities_handler(message: Message) -> None:
    logging.info("Capabilities requested by chat_id=%s", message.chat.id)
    await message.answer(
        "Я экономлю время всей группы: собираю вводные в один бриф и превращаю разрозненные сообщения в понятные ограничения.\n\n"
        "Сейчас я умею:\n"
        "1) принять вводные от организатора одним сообщением и уточнить только недостающее\n"
        "2) подключить участников по ссылке и собрать их пожелания\n"
        "3) собрать общую сводку и подсветить, где ожидания расходятся\n"
        "4) предложить 2–3 направления и зафиксировать короткий список (без голосования в MVP)."
    )


async def my_events_handler(message: Message, state: Optional[FSMContext]) -> None:
    chat_id = message.chat.id
    items: List[Dict[str, Any]] = []
    for code, event in EVENTS.items():
        participants = event.get("participants") or {}
        if event.get("organizer_chat_id") == chat_id:
            items.append(
                {
                    "code": code,
                    "role": "organizer",
                    "title": "организатор",
                    "updated_at": event.get("created_at", 0),
                }
            )
        elif str(chat_id) in participants:
            items.append(
                {
                    "code": code,
                    "role": "participant",
                    "title": "участник",
                    "updated_at": participants[str(chat_id)].get("updated_at", event.get("created_at", 0)),
                }
            )

    if not items:
        await message.answer(
            "У вас пока нет сохранённых событий.\n"
            "Создайте новое событие кнопкой «✨ Создать событие».",
            reply_markup=main_menu_keyboard(),
        )
        return

    items.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
    await message.answer(
        "📂 <b>Мои события</b>\n"
        "Выберите событие, чтобы вернуться к нему:",
        reply_markup=my_events_keyboard(items),
    )


async def new_event_handler(message: Message, state: FSMContext) -> None:
    logging.info("New event requested by chat_id=%s", message.chat.id)
    await state.update_data(organizer_chat_id=message.chat.id)
    await state.set_state(FlowState.organizer_dump)
    event_code = new_event_code()
    EVENTS[event_code] = {
        "code": event_code,
        "created_at": now_ts(),
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
    save_events()

    invite_text = (
        f"\n\nСсылка для участников:\n{invite_link}"
        if invite_link
        else "\n\nСсылка для участников появится после перезапуска бота."
    )

    await message.answer(
        "Ок, событие создано.\n"
        "Сейчас вы — организатор этого события.\n\n"
        "Шаг 1: одним сообщением опишите вводные по поездке."
        f"{invite_text}\n\n"
        "Пример:\n"
        "«2 взрослых + ребёнок 6 лет, июль/август, море, бюджет до 250к, перелёт до 5 часов, без визы»",
        reply_markup=main_menu_keyboard(),
    )


async def send_next_step_after_brief(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    event_code = data.get("event_code")
    event = EVENTS.get(event_code) if event_code else None
    invite_link = event.get("invite_link") if event else None

    invite_block = (
        f"\n\nСсылка для участников:\n{invite_link}"
        if invite_link
        else "\n\nСсылку для участников я пришлю после перезапуска бота."
    )

    await message.answer(
        "Дальше — подключаем участников, чтобы собрать их предпочтения.\n\n"
        "Что сделать организатору:\n"
        "1) отправьте ссылку участникам\n"
        "2) попросите их перейти по ссылке и ответить на короткие вопросы\n"
        "3) после ответов я соберу общую сводку и подсвечу расхождения.\n"
        f"{invite_block}",
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
    if is_organizer:
        await state.update_data(role="organizer", event_code=event_code, brief=brief)
        await state.set_state(FlowState.organizer_clarify)
        await callback.message.answer(
            f"👑 Вы вернулись в событие <b>{html.escape(event_code)}</b> как организатор.\n\n"
            f"{format_brief_update_message(brief)}\n\n"
            "Можно продолжить уточнения одним сообщением.",
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
        f"{format_brief_for_participant(brief)}\n\n"
        "Напишите одним сообщением, что хотите дополнить.",
        reply_markup=main_menu_keyboard(),
    )


async def event_invite_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    event_code = data.get("event_code")
    event = EVENTS.get(event_code) if event_code else None
    invite_link = event.get("invite_link") if event else None
    if not invite_link:
        await callback.message.answer("Ссылка пока недоступна. Попробуйте чуть позже.", reply_markup=main_menu_keyboard())
        return
    await callback.message.answer(f"Ссылка для участников:\n{invite_link}")


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
        "✅ <b>Вас подключили к событию поездки.</b>\n\n"
        "Событие — это общий процесс согласования поездки для вашей группы:\n"
        "организатор собирает вводные, участники добавляют свои пожелания, а я свожу всё в единый бриф.\n\n"
        "Я помогаю убрать хаос в переписке: фиксирую ограничения и показываю, что важно всей группе."
    )
    await message.answer(
        f"{format_brief_for_participant(event_brief)}\n\n"
        "✍️ <b>Дополните бриф одним сообщением:</b>\n"
        "напишите, что важно лично вам (бюджет, даты, перелёт, документы, климат, формат отдыха)."
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
    base_brief = event.get("brief") or {}
    incoming = extract_brief_from_text(message.text or "")
    participant_name = data.get("participant_name") or (
        message.from_user.full_name if message.from_user else str(message.chat.id)
    )
    updated_brief = merge_participant_into_brief(base_brief, incoming, participant_name)
    event["brief"] = updated_brief

    updates = event.setdefault("participant_updates", {})
    updates[message.chat.id] = {
        "text": message.text or "",
        "confirmed": False,
        "name": participant_name,
        "username": (message.from_user.username if message.from_user else None),
        "updated_at": now_ts(),
    }
    participants = event.setdefault("participants", {})
    if str(message.chat.id) in participants:
        participants[str(message.chat.id)]["updated_at"] = now_ts()
    save_events()

    await state.set_state(FlowState.participant_confirm)
    await message.answer(
        "Обновила бриф с учетом ваших вводных.\n\n"
        f"{format_brief_for_participant(updated_brief)}\n\n"
        "Проверьте, пожалуйста: всё верно?",
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
    update_row = updates.setdefault(callback.message.chat.id, {})
    update_row["confirmed"] = True
    update_row["confirmed_at"] = now_ts()
    participants = event.setdefault("participants", {})
    if str(callback.message.chat.id) in participants:
        participants[str(callback.message.chat.id)]["confirmed"] = True
        participants[str(callback.message.chat.id)]["confirmed_at"] = now_ts()
    save_events()

    participant_name = data.get("participant_name") or (
        callback.from_user.full_name if callback.from_user else str(callback.message.chat.id)
    )
    await callback.message.answer(
        "Спасибо, принято ✅\n"
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
            f"{format_brief_for_participant(event.get('brief') or {})}",
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
            save_events()

        await state.update_data(organizer_dump=text, brief=brief)
        await state.set_state(FlowState.organizer_clarify)

        missing = missing_brief_fields(brief)

        summary_text = format_brief_update_message(brief)

        if not missing:
            await message.answer(
                f"{summary_text}\n\n"
                "Данных достаточно. Переходим к подключению участников.",
                reply_markup=main_menu_keyboard(),
            )
            await send_next_step_after_brief(message, state)
            return

        missing_text = "\n".join(f"- {m}" for m in missing)
        await message.answer(
            f"{summary_text}\n\n"
            "Чтобы не переспрашивать лишнее, уточните, пожалуйста, только это (можно одним сообщением):\n"
            f"{missing_text}",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as err:
        logging.exception("organizer_dump_handler failed: %s", err)
        await message.answer(
            "Я столкнулся с ошибкой и не смог обработать сообщение.\n"
            "Попробуйте отправить вводные ещё раз одним сообщением.",
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
            "Спасибо! Осталось уточнить:\n"
            f"{missing_text}\n\n"
            "Можно одним сообщением.",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as err:
        logging.exception("organizer_clarify_handler failed: %s", err)
        await message.answer(
            "Похоже, я не смог обработать уточнение.\n"
            "Попробуйте написать проще (например: «до 250к, июль, 2 взрослых, без визы»).",
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
    await message.answer("Выберите действие в меню.", reply_markup=main_menu_keyboard())


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
    dp.message.register(new_event_handler, F.text == "✨ Создать событие")
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
