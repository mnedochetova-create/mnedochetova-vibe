"""Обогащение брифа: stay_experience из направления, дат и формулировок в тексте."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# (stem, display name, default climate for legacy backfill)
DESTINATION_HINTS: List[Tuple[str, str, str]] = [
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

# (stem, city/region label, setting tags)
CITY_HINTS: List[Tuple[str, str, List[str]]] = [
    ("бодрум", "Бодрум", ["Эгейское побережье", "море", "горы", "сосны"]),
    ("анталь", "Анталья", ["Средиземноморье", "море", "пляж"]),
    ("алань", "Аланья", ["Средиземноморье", "море", "пляж"]),
    ("мармар", "Мармарис", ["Эгейское побережье", "море"]),
    ("фетхие", "Фетхие", ["Эгейское побережье", "море", "горы"]),
    ("каппадок", "Каппадокия", ["горы", "экскурсии", "природа"]),
    ("санторин", "Санторини", ["море", "острова"]),
    ("крит", "Крит", ["море", "остров"]),
    ("дубровник", "Дубровник", ["море", "город"]),
]

_SUMMER_MONTH_STEMS = {"май", "июн", "июл", "август"}
_WARM_SEASON_NOTE = "тёплый сезон, купальный период"

_ACCOMMODATION_PATTERNS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"бутик(?:\s*[-]?\s*отел)?"), "бутик-отель"),
    (re.compile(r"премиальн|премиум|люкс|5\s*\*|пятизвезд"), "премиум"),
    (re.compile(r"\bв\s+горах\b|горн(?:ой|ого|ые)?\s+отел"), "в горах"),
    (re.compile(r"у\s+моря|на\s+берегу|на\s+море"), "у моря"),
    (re.compile(r"all\s*inclusive|оллинклюзив|всё\s+включено"), "всё включено"),
]

_TRIP_STYLE_PATTERNS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"семейн"), "семейный отдых"),
    (re.compile(r"два\s+отел|разн(?:ые|ый)\s+отел|отдельн(?:о|ый)\s+отел|в\s+друг(?:ом|ой)\s+отел"), "разные отели / программы"),
    (re.compile(r"экскурс"), "экскурсии"),
    (re.compile(r"спокойн|релакс|без\s+сует"), "спокойный отдых"),
]


def _detect_destinations(t: str) -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    seen: set[str] = set()
    for stem, name, default_climate in DESTINATION_HINTS:
        if stem in t and name not in seen:
            found.append((name, default_climate))
            seen.add(name)
    return found


def _detect_cities(t: str) -> List[Tuple[str, List[str]]]:
    found: List[Tuple[str, List[str]]] = []
    seen: set[str] = set()
    for stem, label, tags in CITY_HINTS:
        if stem in t and label not in seen:
            found.append((label, tags))
            seen.add(label)
    return found


def _brief_search_text(brief: Dict[str, Any]) -> str:
    parts: List[str] = []
    raw = brief.get("context_raw")
    if isinstance(raw, str) and raw.strip():
        parts.append(raw)
    dump = brief.get("organizer_dump")
    if isinstance(dump, str) and dump.strip() and dump not in (raw or ""):
        parts.append(dump)
    for key in ("climate", "trip_type", "date_range_raw"):
        val = brief.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val)
    for item in brief.get("activity_preferences") or []:
        parts.append(str(item))
    for item in brief.get("constraints_notes") or []:
        parts.append(str(item))
    return " ".join(parts).lower()


def _append_unique(target: List[str], items: Any) -> None:
    if not items:
        return
    if isinstance(items, str):
        candidates = [items]
    else:
        candidates = list(items)
    for item in candidates:
        text = str(item).strip()
        if text and text not in target:
            target.append(text)


def _direction_labels_from_brief(brief: Dict[str, Any]) -> List[str]:
    labels: List[str] = []
    for raw in brief.get("activity_preferences") or []:
        text = str(raw).strip()
        if text.lower().startswith("предпочтение по направлению:"):
            labels.append(text.split(":", 1)[1].strip())
    return labels


def _month_stems_from_brief(brief: Dict[str, Any]) -> List[str]:
    months: List[str] = []
    for raw in brief.get("months") or []:
        months.append(str(raw).lower()[:4])
    dr = brief.get("date_range_raw")
    if isinstance(dr, str):
        low = dr.lower()
        for stem in (
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
        ):
            if stem in low:
                months.append(stem)
    return months


def _season_note_for_months(month_stems: List[str]) -> Optional[str]:
    if not month_stems:
        return None
    for stem in month_stems:
        base = stem[:4] if len(stem) >= 4 else stem
        if base in _SUMMER_MONTH_STEMS or any(base.startswith(s) for s in _SUMMER_MONTH_STEMS):
            month_label = stem.rstrip("ья").capitalize()
            if stem.startswith("июн"):
                month_label = "июнь"
            elif stem.startswith("июл"):
                month_label = "июль"
            elif stem.startswith("август"):
                month_label = "август"
            elif stem.startswith("май"):
                month_label = "май"
            return f"{month_label} — {_WARM_SEASON_NOTE}"
    return None


def _has_sea_setting(settings: List[str]) -> bool:
    joined = " ".join(settings).lower()
    return "море" in joined or "пляж" in joined or "эгей" in joined or "средизем" in joined


def stay_experience_sufficient(brief: Dict[str, Any]) -> bool:
    se = brief.get("stay_experience")
    if isinstance(se, dict):
        for key in ("setting", "accommodation_style", "trip_style"):
            if se.get(key):
                return True
        if se.get("season_note") and (se.get("setting") or _direction_labels_from_brief(brief)):
            return True
    if brief.get("climate") or brief.get("trip_type"):
        return True
    directions = _direction_labels_from_brief(brief)
    if directions and (brief.get("months") or brief.get("date_range_raw")):
        t = _brief_search_text(brief)
        if _detect_cities(t) or _detect_destinations(t):
            return True
    return False


def _sync_legacy_climate_trip(brief: Dict[str, Any], se: Dict[str, Any]) -> None:
    settings = [s.lower() for s in (se.get("setting") or [])]
    joined = " ".join(settings)
    if not brief.get("climate"):
        if "море" in joined or "пляж" in joined or "эгей" in joined:
            if "гор" in joined:
                brief["climate"] = "море/пляж и горы"
            else:
                brief["climate"] = "море/пляж"
        elif "гор" in joined and "море" not in joined:
            brief["climate"] = "горы"
    if not brief.get("trip_type"):
        styles = " ".join(se.get("trip_style") or []).lower()
        acc = " ".join(se.get("accommodation_style") or []).lower()
        if "экскурс" in styles or "экскурс" in joined:
            brief["trip_type"] = "экскурсии/город"
        elif "всё включено" in acc or "оллинклюзив" in acc:
            brief["trip_type"] = "всё включено"
        elif "семей" in styles:
            brief["trip_type"] = "семейный"


def enrich_stay_from_context(brief: Dict[str, Any]) -> Dict[str, Any]:
    """Дополняет stay_experience и legacy climate/trip_type из контекста брифа."""
    if not brief:
        return brief

    t = _brief_search_text(brief)
    se: Dict[str, Any] = dict(brief.get("stay_experience") or {})
    setting: List[str] = list(se.get("setting") or [])
    accommodation: List[str] = list(se.get("accommodation_style") or [])
    trip_style: List[str] = list(se.get("trip_style") or [])

    for label, tags in _detect_cities(t):
        _append_unique(setting, [label] + tags)

    destinations = _detect_destinations(t)
    for name, default_climate in destinations:
        _append_unique(setting, [name])
        for part in default_climate.replace(" и ", "/").split("/"):
            part = part.strip()
            if part:
                _append_unique(setting, [part])

    for label in _direction_labels_from_brief(brief):
        _append_unique(setting, [label])

    if "море" in t or "пляж" in t or "у моря" in t or "на море" in t or "на берегу" in t:
        _append_unique(setting, ["море", "пляж"])
    if re.search(r"\bгор", t):
        _append_unique(setting, ["горы"])
    if "сосн" in t or "хвой" in t:
        _append_unique(setting, ["сосны"])

    for pattern, label in _ACCOMMODATION_PATTERNS:
        if pattern.search(t):
            _append_unique(accommodation, [label])

    for pattern, label in _TRIP_STYLE_PATTERNS:
        if pattern.search(t):
            _append_unique(trip_style, [label])

    month_stems = _month_stems_from_brief(brief)
    note = _season_note_for_months(month_stems)
    if note and (_has_sea_setting(setting) or destinations or _detect_cities(t)):
        se["season_note"] = note
    elif se.get("season_note"):
        pass

    if destinations and month_stems and not _detect_cities(t):
        for _name, default in destinations:
            for part in default.split("/"):
                _append_unique(setting, [part.strip()])

    if setting:
        se["setting"] = setting
    if accommodation:
        se["accommodation_style"] = accommodation
    if trip_style:
        se["trip_style"] = trip_style

    if se:
        brief["stay_experience"] = se
        _sync_legacy_climate_trip(brief, se)

    return brief


def format_stay_experience_display(brief: Dict[str, Any], *, escape_html: bool = False) -> str:
    """Одна строка для карточки брифа."""
    import html as html_module

    def esc(value: str) -> str:
        return html_module.escape(value) if escape_html else value

    parts: List[str] = []
    se = brief.get("stay_experience") if isinstance(brief.get("stay_experience"), dict) else {}

    if se.get("setting"):
        parts.append(esc(" · ".join(se["setting"])))
    if se.get("accommodation_style"):
        parts.append(esc(" · ".join(se["accommodation_style"])))
    if se.get("trip_style"):
        parts.append(esc(" · ".join(se["trip_style"])))
    if se.get("season_note"):
        parts.append(esc(str(se["season_note"])))

    if parts:
        return " · ".join(parts)

    legacy: List[str] = []
    if brief.get("climate"):
        legacy.append(str(brief["climate"]))
    if brief.get("trip_type"):
        legacy.append(str(brief["trip_type"]))
    directions = _direction_labels_from_brief(brief)
    if directions:
        legacy.append(", ".join(directions))
    if legacy:
        return esc(" · ".join(legacy))
    return ""
