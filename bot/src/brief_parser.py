import json
import logging
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from env_util import env_flag


LAST_PARSER_MODE = "rules_only"
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
BRIEF_PARSER_PROMPT_FILE = PROMPTS_DIR / "brief_parser_system_prompt.md"
_BRIEF_PARSER_PROMPT_CACHE: Optional[str] = None


def get_last_parser_mode() -> str:
    return LAST_PARSER_MODE


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
    enabled = env_flag("USE_LLM_BRIEF_PARSER")
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
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        KeyError,
        ValueError,
        TimeoutError,
        OSError,
        IndexError,
        TypeError,
    ) as err:
        logging.warning("LLM brief parser unavailable, fallback to rule-based parser: %s", err)
        return {}


# (stem in lowercased text, display name, default climate if user discusses weather/climate)
_DESTINATION_HINTS: List[Tuple[str, str, str]] = [
    ("грец", "Греция", "море/пляж"),
    ("турц", "Турция", "море/пляж"),
    ("кипр", "Кипр", "море/пляж"),
    ("испан", "Испания", "море/пляж"),
    ("итали", "Италия", "море/пляж"),
    ("хорват", "Хорватия", "море/пляж"),
    ("черногор", "Черногория", "море/пляж"),
    ("болгар", "Болгария", "море/пляж"),
    ("египет", "Египет", "море/пляж"),
    ("таиланд", "Таиланд", "море/пляж"),
    ("вьетнам", "Вьетнам", "море/пляж"),
    ("оаэ", "ОАЭ", "море/пляж"),
    ("дубай", "ОАЭ", "море/пляж"),
    ("мальдив", "Мальдивы", "море/пляж"),
]

_MONTH_PATTERN = (
    r"январ[ья]?|феврал[ья]?|март[а]?|апрел[ья]?|ма[йя]|июн[ья]?|июл[ья]?|"
    r"август[а]?|сентябр[ья]?|октябр[ья]?|ноябр[ья]?|декабр[ья]?"
)


def _detect_destinations(t: str) -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    seen: set[str] = set()
    for stem, name, default_climate in _DESTINATION_HINTS:
        if stem in t and name not in seen:
            found.append((name, default_climate))
            seen.add(name)
    return found


def extract_brief_rule_based(text: str) -> Dict[str, Any]:
    t = (text or "").lower()
    brief: Dict[str, Any] = {}
    brief["context_raw"] = (text or "").strip()

    budget_value = None
    budget_suffix = ""
    m_budget = re.search(
        r"бюджет(?:ом)?\s*(?:до)?\s*(\d[\d\s]{1,8})\s*(к|т|тыс|тысяч|млн|миллион[а-я]*|000|руб|₽)?",
        t,
    )
    if m_budget:
        budget_value = int(re.sub(r"\s+", "", m_budget.group(1)))
        budget_suffix = (m_budget.group(2) or "").strip()
    else:
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
            pass
        elif not suffix and num <= 1000:
            num *= 1000
        brief["budget_rub_max"] = num

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

    months = [
        "январ",
        "феврал",
        "март",
        "апрел",
        "май",
        "июн",
        "июл",
        "август",
        "сентябр",
        "октябр",
        "ноябр",
        "декабр",
    ]
    for mon in months:
        if mon in t:
            brief.setdefault("months", []).append(mon)

    m = re.search(
        rf"(?:в\s+)?(конц[ае]?|начал[оае]?|середин[аы]?|первая\s+половина|вторая\s+половина)\s+({_MONTH_PATTERN})",
        t,
    )
    if m:
        brief["date_range_raw"] = m.group(0).strip()

    m = re.search(
        r"(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?\s*[-–]\s*(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?",
        t,
    )
    if m:
        brief["date_range_raw"] = m.group(0)
    m = re.search(
        r"(?:с\s*)?(\d{1,2})\s*(?:по|[-–])\s*(\d{1,2})\s*(январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья])",
        t,
    )
    if m:
        brief["date_range_raw"] = m.group(0)
    m = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(?:дн|дней|дня)", t)
    if m:
        brief["trip_duration_days_raw"] = f"{m.group(1)}-{m.group(2)} дней"
    else:
        m = re.search(r"(\d{1,2})\s*(?:дн|дней|дня)", t)
        if m:
            brief["trip_duration_days_raw"] = f"{m.group(1)} дней"

    m = re.search(r"(?:до|не\s*больше|не\s*более)\s*(\d{1,2})\s*(?:ч|час(?:ов|а)?)\b", t)
    if not m:
        m = re.search(
            r"(?:перел[её]?т|пол[её]т)\s*(?:до|не\s*больше|не\s*более)?\s*(\d{1,2})\s*(?:ч|час(?:ов|а)?)\b",
            t,
        )
    if not m:
        m = re.search(
            r"(\d{1,2})\s*(?:ч|час(?:ов|а)?)\s*(?:максимум|макс|не\s*больше)(?:\s*на\s*(?:перел[её]?т|пол[её]т))?",
            t,
        )
    if m:
        brief["flight_hours_max"] = int(m.group(1))

    if (
        "можно с пересад" in t
        or "пересадки можно" in t
        or "пересадки ок" in t
        or "пересадки норм" in t
        or "допустимы пересад" in t
        or "пересадки допустим" in t
        or "с пересадк" in t
        or "несколько пересад" in t
        or "через пересад" in t
        or "готовы к пересад" in t
        or "пересадкам не против" in t
        or "пересадки не проблем" in t
    ):
        brief["transfers_allowed"] = True
    if "без пересад" in t or "прямой рейс" in t or "прямой перел" in t or "прямой пол" in t:
        brief["transfers_allowed"] = False

    if (
        "нет ограничений по перел" in t
        or "без ограничений по перел" in t
        or "не важно сколько лететь" in t
        or "не принципиально по перел" in t
        or "сколько угодно лететь" in t
        or "долго лететь можно" in t
        or "нет лимита на перел" in t
        or "перелет без огранич" in t
        or "перелёт без огранич" in t
        or "любая длительность перел" in t
        or ("нет ограничений по времени" in t and ("перел" in t or "пол" in t or "в воздухе" in t))
    ):
        brief["flight_hours_unrestricted"] = True

    if "без виз" in t:
        brief["visa_required"] = False
    elif "виза" in t:
        brief["visa_required"] = True

    if "загран" in t or "заграничн" in t:
        brief.setdefault("documents_discussed", True)
        if "нет" in t and ("загран" in t or "заграничн" in t):
            brief["passports_status"] = "не у всех есть"
        if "есть" in t and ("загран" in t or "заграничн" in t):
            brief["passports_status"] = "есть"
        if "срок" in t and ("загран" in t or "заграничн" in t):
            brief.setdefault("passports_notes", [])
            brief["passports_notes"].append("проверить срок действия загранпаспорта")

    if "шенген" in t or "шэнген" in t or "франц" in t:
        brief.setdefault("visa_notes", [])
        brief.setdefault("documents_discussed", True)
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

    if "не можем" in t or "не получается" in t or "спор" in t or "конфликт" in t:
        brief.setdefault("constraints_notes", [])
        if "есть разные мнения в группе" not in brief["constraints_notes"]:
            brief["constraints_notes"].append("есть разные мнения в группе — важно найти компромисс")
    prefs: list[str] = []
    if "переплач" in t:
        prefs.append("ограничение: не переплачивать")
    if (
        "без длинных пересад" in t
        or "не хочу длинных пересад" in t
        or "избегаем долгих пересад" in t
    ):
        prefs.append("ограничение: без длинных пересадок")
    for note in prefs:
        brief.setdefault("constraints_notes", [])
        if note not in brief["constraints_notes"]:
            brief["constraints_notes"].append(note)

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
        if "без длинных пересад" in t or "не хочу длинных пересад" in t:
            b.setdefault("constraints", []).append("без длинных пересадок")
        if "море" in t or "пляж" in t:
            b.setdefault("wants", []).append("на море")
    if "франц" in t or "во францию" in t:
        me = ensure_party("организатор")
        me.setdefault("wants", []).append("Франция")

    if parties:
        brief["party_preferences"] = parties

    destinations = _detect_destinations(t)

    has_sea = "море" in t or "пляж" in t
    has_mountains = bool(re.search(r"\bгор", t))
    if has_sea and has_mountains:
        brief["climate"] = "море/пляж и горы"
        brief.setdefault("activity_preferences", [])
        for note in ("виноградники / горы", "пляжный отдых"):
            if note not in brief["activity_preferences"]:
                brief["activity_preferences"].append(note)
    elif has_sea:
        brief["climate"] = "море/пляж"
    elif has_mountains or ("горн" in t and "климат" in t):
        brief["climate"] = "горы"
    if "экскурс" in t or "музе" in t:
        brief["trip_type"] = "экскурсии/город"
    if "all inclusive" in t or "оллинклюзив" in t or "всё включено" in t:
        brief["trip_type"] = "всё включено"

    # «климат в Греции в конце августа» — направление + климат из контекста страны
    if "климат" in t and not brief.get("climate") and destinations:
        brief["climate"] = destinations[0][1]
    if not brief.get("climate") and destinations:
        if "тепл" in t or "жарк" in t or "солн" in t or "купан" in t or "загора" in t:
            brief["climate"] = destinations[0][1]

    activity_preferences = []
    for dest_name, _ in destinations:
        activity_preferences.append(f"предпочтение по направлению: {dest_name}")
    if "ази" in t:
        activity_preferences.append("предпочтение по направлению: Азия")
    if "европ" in t and not destinations:
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


def _is_empty_brief_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


def brief_completeness_score(brief: Dict[str, Any]) -> int:
    if not brief:
        return 0
    score = 0
    if brief.get("months") or brief.get("date_range_raw"):
        score += 3
    if brief.get("budget_rub_max"):
        score += 3
    if brief.get("adults") or brief.get("kids_count"):
        score += 3
    if brief.get("flight_hours_max") or brief.get("flight_hours_unrestricted") or "transfers_allowed" in brief:
        score += 2
    if "visa_required" in brief or brief.get("visa_status") or brief.get("visa_notes"):
        score += 2
    if brief.get("passports_status") or brief.get("passports_notes"):
        score += 1
    if brief.get("climate") or brief.get("trip_type"):
        score += 1
    if brief.get("activity_preferences"):
        score += 1
    return score


def _combine_climate(existing: str, new: str) -> str:
    if not existing:
        return new
    if not new or existing == new:
        return existing
    if new in existing or existing in new:
        return existing
    return f"{existing} и {new}"


def merge_brief(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base or {})
    for k, v in (incoming or {}).items():
        if v is None:
            continue
        if k == "context_raw":
            if v:
                out[k] = v
            continue
        if k == "months":
            if _is_empty_brief_value(v):
                continue
            out.setdefault("months", [])
            for item in v:
                if item not in out["months"]:
                    out["months"].append(item)
            continue
        if k in {"visa_notes", "constraints_notes", "activity_preferences"}:
            if _is_empty_brief_value(v):
                continue
            out.setdefault(k, [])
            for item in v:
                if item not in out[k]:
                    out[k].append(item)
            continue
        if k in {"passports_notes"}:
            if _is_empty_brief_value(v):
                continue
            out.setdefault(k, [])
            for item in v:
                if item not in out[k]:
                    out[k].append(item)
            continue
        if k == "climate" and not _is_empty_brief_value(v):
            current = out.get("climate")
            if current and str(current) != str(v):
                out[k] = _combine_climate(str(current), str(v))
            elif not _is_empty_brief_value(current):
                out[k] = current
            else:
                out[k] = v
            continue
        if _is_empty_brief_value(v) and not _is_empty_brief_value(out.get(k)):
            continue
        out[k] = v
    return out


def merge_participant_into_brief(
    base: Dict[str, Any],
    incoming: Dict[str, Any],
    participant_name: str,
) -> Dict[str, Any]:
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
    flight_block_ok = (
        bool(brief.get("flight_hours_max"))
        or ("transfers_allowed" in brief)
        or bool(brief.get("flight_hours_unrestricted"))
    )
    if not flight_block_ok:
        missing.append("Ограничение по перелёту (например, «до 5 часов»)")
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
    if brief.get("visa_required") is True and not brief.get("passports_status"):
        missing.append("Загранпаспорта у участников (есть ли у всех / срок действия)")
    if not brief.get("climate") and not brief.get("trip_type"):
        missing.append("Климат или тип отдыха (море/горы/город/санаторий и т.п.)")
    return missing


def extract_brief_from_text(text: str) -> Dict[str, Any]:
    global LAST_PARSER_MODE
    rule_based = extract_brief_rule_based(text)
    llm_enabled = env_flag("USE_LLM_BRIEF_PARSER") and bool(os.getenv("LLM_API_KEY", "").strip())
    llm_brief = parse_brief_with_llm(text)
    if not llm_enabled:
        LAST_PARSER_MODE = "rules_only"
    elif llm_brief:
        LAST_PARSER_MODE = "llm+rules"
    else:
        LAST_PARSER_MODE = "llm_fallback"
    return merge_brief(llm_brief, rule_based)
