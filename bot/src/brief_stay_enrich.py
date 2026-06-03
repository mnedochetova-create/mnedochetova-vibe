"""Обогащение брифа: stay_experience из направления, дат и формулировок в тексте."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import brief_route_combo

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
    ("франц", "Франция", "море/пляж"),
    ("португал", "Португалия", "море/пляж"),
    ("чех", "Чехия", "город"),
    ("австри", "Австрия", "горы"),
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
    ("палех", "Палех", ["Россия", "Ивановская область"]),
    ("гороховец", "Гороховец", ["Россия", "Владимирская область"]),
    ("дивеев", "Дивеево", ["Россия", "Нижегородская область"]),
    ("ницц", "Ницца", ["Кот-д'Азур", "Франция", "море", "пляж"]),
    ("канн", "Канны", ["Кот-д'Азур", "Франция", "море"]),
    ("марсел", "Марсель", ["Прованс", "Франция", "море"]),
]

# Регионы / формулировки направления (курируемая база, не веб в рантайме)
REGION_HINTS: List[Tuple[str, str, List[str]]] = [
    ("центральн", "Центральная Россия", ["Россия", "город", "экскурсии"]),
    ("ивановск", "Ивановская область", ["Россия", "Центральная Россия"]),
    ("владимирск", "Владимирская область", ["Россия", "Центральная Россия"]),
    ("нижегородск", "Нижегородская область", ["Россия", "Центральная Россия"]),
    ("юг франц", "Юг Франции", ["Франция", "Средиземноморье", "море", "пляж"]),
    ("юга франц", "Юг Франции", ["Франция", "Средиземноморье", "море", "пляж"]),
    ("прованс", "Прованс", ["Франция", "море", "гастрономия"]),
    ("кот-д'азур", "Кот-д'Азур", ["Франция", "море", "пляж"]),
    ("кот д'азур", "Кот-д'Азур", ["Франция", "море", "пляж"]),
    ("лазурн", "Лазурный берег", ["Франция", "море"]),
    ("средиземномор", "Средиземноморье", ["море", "пляж"]),
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


def _country_in_layover_context(t: str, stem: str) -> bool:
    """Страна в контексте пересадки/транзита — не направление отдыха."""
    if stem not in t:
        return False
    if not re.search(r"(?:пересадк|стыковк|транзит|остановк|layover|stopover)", t):
        return False
    if re.search(rf"(?:пересадк|стыковк|транзит|остановк)\w*.{{0,60}}?\bв\s+\w*{stem}", t):
        return True
    if re.search(rf"\bв\s+\w*{stem}\w*.{{0,50}}?(?:пересад|аэропорт|отел|поспать|сон)", t):
        return True
    return False


def _country_in_comparison_context(t: str, stem: str) -> bool:
    """Страна в сравнении/варианте («италия?», «с чем совместить») — не основное направление."""
    if stem not in t:
        return False
    if re.search(r"совмест\w*", t):
        if re.search(rf"\b{stem}\w*\s*\?", t):
            return True
        if re.search(rf"\?\s*[^.?]*\b{stem}", t):
            return True
    if re.search(r"посмотреть\s+максим", t) and re.search(rf"\b{stem}\w*\s*\?", t):
        return True
    if re.search(rf"\b{stem}\w*\s*\?", t) and re.search(r"\?", t):
        return True
    return False


def is_comparison_mode(t: str) -> bool:
    """Несколько направлений: пользователь сравнивает или выбирает комбо."""
    if re.search(r"совмест\w*", t):
        return True
    if re.search(r"посмотреть\s+максим", t) and re.search(r"\?", t):
        return True
    country_hits = sum(1 for stem, _name, _ in DESTINATION_HINTS if stem in t)
    return country_hits >= 2 and bool(re.search(r"\?", t))


def _detect_destinations(t: str) -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    seen: set[str] = set()
    for stem, name, default_climate in DESTINATION_HINTS:
        if stem in t and name not in seen:
            if _country_in_layover_context(t, stem):
                continue
            if is_comparison_mode(t) and _country_in_comparison_context(t, stem):
                continue
            found.append((name, default_climate))
            seen.add(name)
    return found


def destinations_with_roles(t: str) -> tuple[Optional[str], List[str]]:
    """Основное направление и альтернативы при сравнении маршрутов."""
    ordered: List[tuple[int, str, str]] = []
    seen: set[str] = set()
    for stem, name, _climate in DESTINATION_HINTS:
        if stem not in t or name in seen:
            continue
        if _country_in_layover_context(t, stem):
            continue
        ordered.append((t.find(stem), name, stem))
        seen.add(name)
    ordered.sort(key=lambda x: x[0])
    if not ordered:
        return None, []

    if not is_comparison_mode(t):
        names = [x[1] for x in ordered]
        return names[0], names[1:]

    primary: Optional[str] = None
    alternatives: List[str] = []
    for _pos, name, stem in ordered:
        if _country_in_comparison_context(t, stem):
            alternatives.append(name)
        elif primary is None:
            primary = name
        else:
            alternatives.append(name)
    if primary is None and ordered:
        primary = ordered[0][1]
        alternatives = [x[1] for x in ordered[1:] if x[1] != primary]
    return primary, alternatives


def _detect_cities(t: str) -> List[Tuple[str, List[str]]]:
    found: List[Tuple[str, List[str]]] = []
    seen: set[str] = set()
    for stem, label, tags in CITY_HINTS:
        if stem in t and label not in seen:
            found.append((label, tags))
            seen.add(label)
    return found


def _detect_regions(t: str) -> List[Tuple[str, List[str]]]:
    found: List[Tuple[str, List[str]]] = []
    seen: set[str] = set()
    for stem, label, tags in REGION_HINTS:
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
    if brief.get("must_visit_places") or brief.get("regions"):
        return True
    if brief.get("trip_transport") == "ground" and (
        brief.get("stay_experience") or brief.get("constraints_notes")
    ):
        return True
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

    if brief_route_combo.is_route_combo_planning(brief):
        t = _brief_search_text(brief)
        se: Dict[str, Any] = dict(brief.get("stay_experience") or {})
        acc = list(se.get("accommodation_style") or [])
        for pattern, label in _ACCOMMODATION_PATTERNS:
            if pattern.search(t):
                _append_unique(acc, [label])
        if acc:
            se["accommodation_style"] = acc
            brief["stay_experience"] = se
        return brief

    t = _brief_search_text(brief)
    se: Dict[str, Any] = dict(brief.get("stay_experience") or {})
    setting: List[str] = list(se.get("setting") or [])
    accommodation: List[str] = list(se.get("accommodation_style") or [])
    trip_style: List[str] = list(se.get("trip_style") or [])

    for label, tags in _detect_cities(t):
        _append_unique(setting, [label] + tags)

    for label, tags in _detect_regions(t):
        _append_unique(setting, [label] + tags)

    primary = brief.get("destination_primary")
    alternatives = brief.get("destination_alternatives") or []
    destinations = _detect_destinations(t)
    if primary:
        _append_unique(setting, [str(primary)])
        for _name, default_climate in destinations:
            if _name == primary:
                for part in default_climate.replace(" и ", "/").split("/"):
                    part = part.strip()
                    if part:
                        _append_unique(setting, [part])
                break
    else:
        for name, default_climate in destinations:
            _append_unique(setting, [name])
            for part in default_climate.replace(" и ", "/").split("/"):
                part = part.strip()
                if part:
                    _append_unique(setting, [part])

    for label in _direction_labels_from_brief(brief):
        if primary and label == primary:
            _append_unique(setting, [label])
        elif not primary:
            _append_unique(setting, [label])
        elif label not in alternatives:
            _append_unique(setting, [label])

    if "море" in t or "пляж" in t or "у моря" in t or "на море" in t or "на берегу" in t:
        _append_unique(setting, ["море", "пляж"])
    if re.search(r"\bгор", t):
        _append_unique(setting, ["горы"])
    if "сосн" in t or "хвой" in t:
        _append_unique(setting, ["сосны"])
    if "ресторан" in t or "гастроном" in t:
        _append_unique(trip_style, ["рестораны и гастрономия"])

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


def _period_phrase(brief: Dict[str, Any]) -> str:
    if brief.get("date_range_raw"):
        raw = str(brief["date_range_raw"]).strip()
        if raw.startswith("в "):
            return raw
        return f"в {raw}"
    months = brief.get("months") or []
    if months:
        label = str(months[0]).strip()
        if not label.startswith("в "):
            return f"в {label}"
        return label
    return ""


def _activity_phrase(se: Dict[str, Any], brief: Dict[str, Any]) -> str:
    if brief_route_combo.is_route_combo_planning(brief):
        if brief_route_combo.wants_max_sightseeing("", brief):
            return "максимум достопримечательностей"
        return "планирование комбо маршрута"
    bits: List[str] = []
    styles = [str(s).lower() for s in (se.get("trip_style") or [])]
    settings = [str(s).lower() for s in (se.get("setting") or [])]
    combined = " ".join(styles + settings)
    if "пляж" in combined or "море" in combined:
        bits.append("пляж и море")
    if "ресторан" in combined or "гастроном" in combined:
        bits.append("рестораны")
    if "экскурс" in combined:
        bits.append("экскурсии")
    if "спокойн" in combined or "релакс" in combined:
        bits.append("спокойный ритм")
    for item in brief.get("activity_preferences") or []:
        low = str(item).lower()
        if "ресторан" in low and "рестораны" not in bits:
            bits.append("рестораны")
    if len(bits) == 1:
        return bits[0]
    if len(bits) == 2:
        return f"{bits[0]} и {bits[1]}"
    if bits:
        return ", ".join(bits[:-1]) + f" и {bits[-1]}"
    acc = se.get("accommodation_style") or []
    if acc:
        return str(acc[0]).lower()
    return "отдых по вашим вводным"


def _headline_place(se: Dict[str, Any], brief: Optional[Dict[str, Any]] = None) -> Optional[str]:
    if brief and brief_route_combo.is_route_combo_planning(brief):
        return "Планирование комбо"
    if brief and brief.get("destination_primary"):
        name = str(brief["destination_primary"]).strip()
        if name:
            return f"В {name}"
    settings = [str(s).strip() for s in (se.get("setting") or []) if str(s).strip()]
    for tag in settings:
        if "юг" in tag.lower() and "франц" in tag.lower():
            return "На юг Франции"
    for tag in settings:
        if tag in {
            "Франция",
            "Турция",
            "Греция",
            "Италия",
            "Испания",
            "Кипр",
            "Хорватия",
            "Черногория",
            "Болгария",
            "Египет",
            "Таиланд",
            "Вьетнам",
            "ОАЭ",
            "Португалия",
        }:
            return f"В {tag}"
    for tag in settings:
        low = tag.lower()
        if low in {"море", "пляж", "средиземноморье", "рестораны"}:
            continue
        if len(tag) > 4:
            return f"В {tag}" if not tag.startswith("В ") else tag
    return None


def format_stay_experience_display(brief: Dict[str, Any], *, escape_html: bool = False) -> str:
    """Короткий связный текст про направление и сезон для карточки брифа."""
    import html as html_module

    def esc(value: str) -> str:
        return html_module.escape(value) if escape_html else value

    se = brief.get("stay_experience") if isinstance(brief.get("stay_experience"), dict) else {}
    place = _headline_place(se, brief)
    period = _period_phrase(brief)
    activities = _activity_phrase(se, brief)

    sentences: List[str] = []
    if place and period:
        sentences.append(esc(f"{place} {period} — {activities}."))
    elif place:
        sentences.append(esc(f"{place} — {activities}."))
    elif period:
        sentences.append(esc(f"Поездка {period} — {activities}."))

    note = se.get("season_note")
    period_blob = f"{brief.get('date_range_raw') or ''} {' '.join(brief.get('months') or [])}".lower()
    if note:
        short = str(note).split(",")[0].strip()
        month_in_period = short.split("—")[0].strip().lower() if "—" in short else short.lower()
        if short and month_in_period and month_in_period in period_blob:
            short = ""
        if short:
            sentences.append(esc(short[0].upper() + short[1:] + "."))

    if sentences:
        return " ".join(sentences)

    legacy: List[str] = []
    if brief.get("climate"):
        legacy.append(str(brief["climate"]))
    if brief.get("trip_type"):
        legacy.append(str(brief["trip_type"]))
    directions = _direction_labels_from_brief(brief)
    if directions:
        legacy.append(", ".join(directions))
    if legacy:
        return esc(", ".join(legacy))
    return ""
