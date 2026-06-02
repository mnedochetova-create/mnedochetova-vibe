"""Форматирование брифа для карточки в Telegram (человекочитаемый текст).

trip_title — короткое имя поездки (2–4 слова), пересчитывается после парсинга и merge:
  1) страна/направление из stay_experience или activity_preferences;
  2) форма «Во/В …» (Франция → Во Францию);
  3) уточнение состава: с семьёй | вдвоём | с компанией | только направление.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

import brief_stay_enrich

_CURRENCY_SYMBOLS = {
    "EUR": "€",
    "USD": "$",
    "GBP": "£",
    "RUB": "₽",
    "TRY": "₺",
    "AED": "AED",
}

_PLACE_ACCUSATIVE = {
    "Франция": "Францию",
    "Турция": "Турцию",
    "Греция": "Грецию",
    "Италия": "Италию",
    "Испания": "Испанию",
    "Кипр": "Кипр",
    "Хорватия": "Хорватию",
    "Черногория": "Черногорию",
    "Болгария": "Болгарию",
    "Египет": "Египет",
    "Таиланд": "Таиланд",
    "Вьетнам": "Вьетнам",
    "ОАЭ": "ОАЭ",
    "Португалия": "Португалию",
    "Чехия": "Чехию",
    "Австрия": "Австрию",
}

_COUNTRY_NAMES = frozenset(_PLACE_ACCUSATIVE.keys())

_GENERIC_SETTING_TAGS = frozenset(
    {
        "море",
        "пляж",
        "средиземноморье",
        "рестораны",
        "рестораны и гастрономия",
        "пляжный отдых",
        "июль — тёплый сезон, купальный период",
    }
)


def normalize_duration_display(raw: Optional[str]) -> str:
    if not raw:
        return "—"
    text = str(raw).strip()
    if re.fullmatch(r"\d{1,2}", text):
        return f"{text} дней"
    if re.fullmatch(r"\d{1,2}-\d{1,2}", text):
        return f"{text} дней"
    if re.fullmatch(r"\d{1,2}", text.replace(" ", "")):
        return f"{text} дней"
    if text.isdigit():
        return f"{text} дней"
    if "дн" not in text.lower() and re.search(r"\d", text):
        m = re.search(r"(\d{1,2}(?:-\d{1,2})?)", text)
        if m:
            return f"{m.group(1)} дней"
    return text


def _foreign_budget_amount(brief: Dict[str, Any]) -> tuple[Optional[int], Optional[str]]:
    currency = (brief.get("budget_currency") or "").strip().upper()
    if currency and currency != "RUB":
        for key, amount in brief.items():
            if key.startswith("budget_") and key.endswith("_max") and isinstance(amount, int):
                if key == f"budget_{currency.lower()}_max" or key == "budget_amount_max":
                    return amount, currency
        if isinstance(brief.get("budget_amount_max"), int):
            return brief["budget_amount_max"], currency
        if currency == "EUR" and brief.get("budget_eur_max"):
            return int(brief["budget_eur_max"]), "EUR"
    if brief.get("budget_eur_max"):
        return int(brief["budget_eur_max"]), "EUR"
    return None, None


def format_budget_display(brief: Dict[str, Any]) -> str:
    amount, currency = _foreign_budget_amount(brief)
    if amount is not None and currency:
        symbol = _CURRENCY_SYMBOLS.get(currency, currency)
        formatted = f"{amount:,}".replace(",", " ")
        prefix = "гибкий, до " if brief.get("budget_flexible") else "до "
        if symbol in {"$", "€", "£", "₽", "₺"}:
            return f"{prefix}{formatted} {symbol}"
        return f"{prefix}{formatted} {symbol}"

    if brief.get("budget_flexible") and brief.get("budget_rub_min") and brief.get("budget_rub_max"):
        lo = f"{brief['budget_rub_min']:,}".replace(",", " ")
        hi = f"{brief['budget_rub_max']:,}".replace(",", " ")
        return f"гибкий, {lo}–{hi} ₽"
    if brief.get("budget_rub_min") and brief.get("budget_rub_max"):
        lo = f"{brief['budget_rub_min']:,}".replace(",", " ")
        hi = f"{brief['budget_rub_max']:,}".replace(",", " ")
        return f"{lo}–{hi} ₽"
    if brief.get("budget_rub_max"):
        prefix = "гибкий, до " if brief.get("budget_flexible") else "до "
        return f"{prefix}{brief['budget_rub_max']:,} ₽".replace(",", " ")
    if brief.get("budget_flexible"):
        return "гибкий"
    return "—"


def _flight_is_missing(brief: Dict[str, Any], missing: Optional[List[str]]) -> bool:
    if missing:
        return any(str(item).startswith("Перелёт") for item in missing)
    return not (
        brief.get("flight_hours_max")
        or brief.get("flight_hours_unrestricted")
        or "transfers_allowed" in brief
        or brief.get("flight_preferences")
    )


def format_flight_display(
    brief: Dict[str, Any],
    *,
    esc: Optional[Callable[[Any], str]] = None,
    missing: Optional[List[str]] = None,
) -> str:
    esc_fn = esc if callable(esc) else (lambda value: value)
    parts: List[str] = []
    if brief.get("flight_hours_max"):
        parts.append(f"до {esc_fn(brief['flight_hours_max'])} ч.")
    elif brief.get("flight_hours_unrestricted"):
        parts.append("без ограничений по длительности")
    if brief.get("transfers_allowed") is True:
        parts.append("пересадки допустимы")
    elif brief.get("transfers_allowed") is False:
        parts.append("прямой рейс")
    prefs = brief.get("flight_preferences") or []
    if prefs:
        parts.append(", ".join(esc_fn(str(item)) for item in prefs))
    if parts:
        return " · ".join(parts)
    if _flight_is_missing(brief, missing):
        return "нужно указать: прямой или с пересадками, класс (эконом/бизнес)"
    return "—"


def _vo_v_accusative(place: str) -> str:
    acc = _PLACE_ACCUSATIVE.get(place, place)
    if acc == "Францию":
        return f"Во {acc}"
    if acc[:1].lower() in "аоуыэюяеёи":
        return f"Во {acc}"
    return f"В {acc}"


def _primary_place_name(brief: Dict[str, Any]) -> Optional[str]:
    se = brief.get("stay_experience") if isinstance(brief.get("stay_experience"), dict) else {}
    settings = [str(s).strip() for s in (se.get("setting") or []) if str(s).strip()]
    for tag in settings:
        if "юг" in tag.lower() and "франц" in tag.lower():
            return "Юг Франции"
    for tag in settings:
        if tag in _COUNTRY_NAMES:
            return tag
    for tag in settings:
        low = tag.lower()
        if low not in _GENERIC_SETTING_TAGS and len(tag) > 3:
            return tag
    for pref in brief.get("activity_preferences") or []:
        text = str(pref)
        if text.lower().startswith("предпочтение по направлению:"):
            return text.split(":", 1)[1].strip()
    return None


def _country_for_title(brief: Dict[str, Any]) -> Optional[str]:
    se = brief.get("stay_experience") if isinstance(brief.get("stay_experience"), dict) else {}
    settings = [str(s).strip() for s in (se.get("setting") or []) if str(s).strip()]
    for tag in settings:
        if tag in _COUNTRY_NAMES:
            return tag
    for tag in settings:
        low = tag.lower()
        if "франц" in low:
            return "Франция"
        if "турц" in low:
            return "Турция"
        if "грец" in low:
            return "Греция"
    for pref in brief.get("activity_preferences") or []:
        text = str(pref)
        if text.lower().startswith("предпочтение по направлению:"):
            dest = text.split(":", 1)[1].strip()
            if dest in _COUNTRY_NAMES:
                return dest
    return _primary_place_name(brief)


def derive_trip_title(brief: Dict[str, Any]) -> str:
    """Собрать trip_title по правилам (см. модульный docstring)."""
    country = _country_for_title(brief)
    if not country:
        return "Новая поездка"

    adults = brief.get("adults")
    kids = brief.get("kids_count") or brief.get("kids")
    ctx = f"{brief.get('context_raw') or ''} {brief.get('organizer_dump') or ''}".lower()
    destination = _vo_v_accusative(country)

    if kids or "семей" in ctx or "семь" in ctx or (isinstance(adults, int) and adults >= 5):
        return f"{destination} с семьёй"
    if isinstance(adults, int) and adults == 2:
        return f"{destination} вдвоём"
    if isinstance(adults, int) and adults >= 3:
        return f"{destination} с компанией"
    return destination


def sync_trip_title(brief: Dict[str, Any]) -> str:
    """Обогатить stay_experience и записать brief['trip_title']."""
    brief_stay_enrich.enrich_stay_from_context(brief)
    title = derive_trip_title(brief)
    brief["trip_title"] = title
    return title


def get_trip_title(brief: Dict[str, Any]) -> str:
    stored = str(brief.get("trip_title") or "").strip()
    if stored:
        return stored
    return derive_trip_title(brief)


def _scenario_text_blob(brief: Dict[str, Any]) -> str:
    brief_stay_enrich.enrich_stay_from_context(brief)
    chunks: List[str] = [brief_stay_enrich.format_stay_experience_display(brief)]
    se = brief.get("stay_experience") if isinstance(brief.get("stay_experience"), dict) else {}
    for key in ("setting", "trip_style", "accommodation_style", "season_note"):
        val = se.get(key)
        if isinstance(val, list):
            chunks.extend(str(x) for x in val)
        elif val:
            chunks.append(str(val))
    return " ".join(chunks).lower()


def _extra_item_covered_by_scenario(item: str, scenario_blob: str) -> bool:
    low = item.lower().strip()
    if not low or low.startswith("предпочтение по направлению:"):
        return True
    if low in scenario_blob:
        return True
    coverage_rules = (
        ("ресторан", ("ресторан", "гастроном", "еда")),
        ("гастроном", ("ресторан", "гастроном")),
        ("локальн", ("ресторан", "еда", "гастроном")),
        ("пляж", ("пляж", "море")),
        ("море", ("море", "пляж")),
        ("экскурс", ("экскурс",)),
        ("гор", ("гор", "горы")),
        ("спокойн", ("спокойн", "релакс")),
        ("семейн", ("семей",)),
    )
    for trigger, required_any in coverage_rules:
        if trigger in low and any(token in scenario_blob for token in required_any):
            return True
    return False


def filter_extra_activity_preferences(
    brief: Dict[str, Any],
    items: List[str],
) -> List[str]:
    """Убрать из «Доп. пожеланий» то, что уже отражено в сценарии и локации."""
    if not items:
        return []
    blob = _scenario_text_blob(brief)
    filtered: List[str] = []
    for raw in items:
        text = str(raw).strip()
        if not text or _extra_item_covered_by_scenario(text, blob):
            continue
        filtered.append(text)
    return filtered


def format_party_group_summary(brief: Dict[str, Any]) -> str:
    adults = brief.get("adults")
    kids = brief.get("kids_count") or brief.get("kids")
    ctx = f"{brief.get('context_raw') or ''} {brief.get('organizer_dump') or ''}".lower()

    opener = ""
    if isinstance(adults, int):
        if kids:
            opener = f"Большая семья: {adults} взрослых и {int(kids)} ребёнок"
        else:
            opener = f"Группа: {adults} взрослых"
    elif "семей" in ctx or "семь" in ctx:
        opener = "Поездка большой семьёй"

    nuances: List[str] = []
    prefs = brief.get("party_preferences") or {}
    if isinstance(prefs, dict):
        for key, data in prefs.items():
            if not isinstance(data, dict):
                continue
            wants = [str(w) for w in (data.get("wants") or [])]
            constraints = [str(c) for c in (data.get("constraints") or [])]
            if key == "брат_и_жена" and any("море" in w.lower() or "пляж" in w.lower() for w in wants):
                nuances.append("брату с семьёй важны море и пляж")
            elif key == "организатор" and wants:
                continue
            elif constraints:
                nuances.append("есть пожелание по перелёту без длинных пересадок")

    se = brief.get("stay_experience") if isinstance(brief.get("stay_experience"), dict) else {}
    styles = " ".join(str(s).lower() for s in (se.get("trip_style") or []))
    if "ресторан" in styles or any("ресторан" in str(a).lower() for a in brief.get("activity_preferences") or []):
        nuances.append("всем близки рестораны и гастрономия")

    if not opener and not nuances:
        return ""

    parts = [p for p in [opener, *nuances] if p]
    if len(parts) == 1:
        return parts[0] + "."
    return parts[0] + " — " + "; ".join(parts[1:]) + "."
