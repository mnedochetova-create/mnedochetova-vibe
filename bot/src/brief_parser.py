import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import brief_flat_mapper
import brief_pipeline
import brief_display
import brief_stay_enrich
from parser_mode import role_llm_active


LAST_PARSER_MODE = "rules_only"


def get_last_parser_mode() -> str:
    return LAST_PARSER_MODE


_DESTINATION_HINTS = brief_stay_enrich.DESTINATION_HINTS

_MONTH_PATTERN = (
    r"январ[ья]?|феврал[ья]?|март[а]?|апрел[ья]?|ма[йя]|июн[ья]?|июл[ья]?|"
    r"август[а]?|сентябр[ья]?|октябр[ья]?|ноябр[ья]?|декабр[ья]?"
)


def _detect_destinations(t: str) -> List[Tuple[str, str]]:
    return brief_stay_enrich._detect_destinations(t)


def _detect_cities(t: str) -> List[Tuple[str, List[str]]]:
    return brief_stay_enrich._detect_cities(t)


def _money_to_rub(num: int, suffix: str) -> int:
    suffix = (suffix or "").strip()
    if suffix in {"к", "т", "тыс", "тысяч"}:
        num *= 1000
    elif suffix.startswith("млн") or suffix.startswith("миллион"):
        num *= 1_000_000
    elif not suffix and num <= 1000:
        num *= 1000
    return num


def _has_group_conflict_signal(t: str) -> bool:
    if "конфликт" in t or "не можем" in t or "не получается" in t:
        return True
    for match in re.finditer(r"спор\w*", t):
        start = match.start()
        window = t[max(0, start - 4) : start + len(match.group(0)) + 2]
        if "пасп" in window:
            continue
        return True
    return False


def _infer_family_composition(t: str, brief: Dict[str, Any]) -> None:
    """Явно перечисленные роли в семейной поездке — без «тихого» +1 за организатора."""
    if brief.get("adults"):
        return
    if "семь" not in t and "семей" not in t:
        return

    adults = 0
    if "брат" in t:
        adults += 2 if ("жен" in t or "жена" in t or "с жен" in t) else 1
    if "родител" in t or "мои родители" in t or ("папа" in t and "мама" in t):
        adults += 2
    if re.search(r"(?<![\w])муж(?![\w])", t) or " с мужем" in t:
        adults += 1
    if "свекров" in t or "свекор" in t:
        adults += 1
    if "племянник" in t or "племянниц" in t:
        adults += 1

    if adults > 0:
        brief["adults"] = adults
    if brief.get("kid_age") and not brief.get("kids_count"):
        brief["kids_count"] = 1


def _has_destination_hint(brief: Dict[str, Any]) -> bool:
    if brief_stay_enrich._direction_labels_from_brief(brief):
        return True
    se = brief.get("stay_experience")
    if isinstance(se, dict) and se.get("setting"):
        return True
    t = brief_stay_enrich._brief_search_text(brief)
    return bool(brief_stay_enrich._detect_destinations(t) or brief_stay_enrich._detect_cities(t))


def extract_brief_rule_based(text: str) -> Dict[str, Any]:
    t = (text or "").lower()
    brief: Dict[str, Any] = {}
    brief["context_raw"] = (text or "").strip()

    if re.search(
        r"бюджет\s+гибк|гибк\w*\s+бюджет|бюджет\s+не\s+принципиал|"
        r"ориентир\s+по\s+бюджет|без\s+ж[её]стк\w*\s+бюджет|бюджет\s+не\s+важен",
        t,
    ):
        brief["budget_flexible"] = True

    m_budget_range = re.search(
        r"бюджет(?:ом)?\s*(?:до\s*)?(\d[\d\s]{1,8})\s*[-–]\s*(\d[\d\s]{1,8})\s*"
        r"(к|т|тыс|тысяч|млн|миллион[а-я]*|000|руб|₽)?",
        t,
    )
    if not m_budget_range:
        m_budget_range = re.search(
            r"(\d[\d\s]{1,8})\s*[-–]\s*(\d[\d\s]{1,8})\s*(к|т|тыс|тысяч|млн|миллион[а-я]*)(?:\s*руб)?",
            t,
        )
    if m_budget_range:
        low = _money_to_rub(int(re.sub(r"\s+", "", m_budget_range.group(1))), m_budget_range.group(3) or "")
        high = _money_to_rub(int(re.sub(r"\s+", "", m_budget_range.group(2))), m_budget_range.group(3) or "")
        if low > high:
            low, high = high, low
        brief["budget_rub_min"] = low
        brief["budget_rub_max"] = high

    _foreign_budget_patterns = (
        (r"бюджет(?:ом)?\s*(?:до\s*)?(\d[\d\s]{1,8})\s*(?:евро|eur|€)", "EUR", "budget_eur_max"),
        (r"(\d[\d\s]{1,8})\s*(?:евро|eur|€)", "EUR", "budget_eur_max"),
        (r"бюджет(?:ом)?\s*(?:до\s*)?(\d[\d\s]{1,8})\s*(?:доллар|usd|\$)", "USD", "budget_usd_max"),
        (r"(\d[\d\s]{1,8})\s*(?:доллар|usd|\$)", "USD", "budget_usd_max"),
        (r"бюджет(?:ом)?\s*(?:до\s*)?(\d[\d\s]{1,8})\s*(?:фунт|gbp|£)", "GBP", "budget_gbp_max"),
        (r"(\d[\d\s]{1,8})\s*(?:фунт|gbp|£)", "GBP", "budget_gbp_max"),
        (r"бюджет(?:ом)?\s*(?:до\s*)?(\d[\d\s]{1,8})\s*(?:лир|try|₺)", "TRY", "budget_try_max"),
        (r"(\d[\d\s]{1,8})\s*(?:лир|try|₺)", "TRY", "budget_try_max"),
        (r"бюджет(?:ом)?\s*(?:до\s*)?(\d[\d\s]{1,8})\s*(?:дирхам|aed)", "AED", "budget_aed_max"),
        (r"(\d[\d\s]{1,8})\s*(?:дирхам|aed)", "AED", "budget_aed_max"),
    )
    for pattern, currency, field_key in _foreign_budget_patterns:
        m_foreign = re.search(pattern, t)
        if m_foreign and field_key not in brief and "budget_amount_max" not in brief:
            amount = int(re.sub(r"\s+", "", m_foreign.group(1)))
            brief[field_key] = amount
            brief["budget_amount_max"] = amount
            brief["budget_currency"] = currency
            break

    budget_value = None
    budget_suffix = ""
    if (
        "budget_rub_max" not in brief
        and "budget_eur_max" not in brief
        and "budget_amount_max" not in brief
    ):
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
            brief["budget_rub_max"] = _money_to_rub(budget_value, budget_suffix)

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
        brief.setdefault("kids_count", 1)

    _infer_family_composition(t, brief)

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
        rf"(?:в\s+)?(конц[ае]?|начал[оае]?|середин[аые]?|середине|первая\s+половина|вторая\s+половина)\s+({_MONTH_PATTERN})",
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
        m = re.search(r"на\s+(\d{1,2})\s*(?:дн|дней|дня)\b", t)
        if m:
            brief["trip_duration_days_raw"] = f"{m.group(1)} дней"
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

    flight_preferences: list[str] = []
    if "эконом" in t and ("перел" in t or "рейс" in t or "авиа" in t or "билет" in t or "класс" in t):
        flight_preferences.append("эконом")
    elif re.search(r"\bэконом\b", t) and ("прям" in t or "перел" in t):
        flight_preferences.append("эконом")
    if "бизнес" in t and ("класс" in t or "перел" in t or "рейс" in t or "авиа" in t):
        flight_preferences.append("бизнес")
    if "комфорт" in t and ("класс" in t or "перел" in t or "рейс" in t):
        flight_preferences.append("комфорт")
    if flight_preferences:
        brief["flight_preferences"] = flight_preferences

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
        if re.search(r"загран\w*\s+(?:ок|в\s+порядке|готов)", t) or re.search(
            r"паспорт\w*\s+(?:ок|в\s+порядке|готов)", t
        ):
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

    if _has_group_conflict_signal(t):
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
    if re.search(r"друг\w*\s+отел", t) or "в другом отел" in t:
        split = ensure_party("разные_отели")
        split.setdefault("notes", []).append("разные отели / программы в поездке")
    if "с муж" in t or "с мам" in t or "с пап" in t:
        family = ensure_party("семья")
        if "с муж" in t:
            family.setdefault("notes", []).append("часть поездки с мужем")
        if "с мам" in t:
            family.setdefault("notes", []).append("часть поездки с мамой")
        if "с пап" in t:
            family.setdefault("notes", []).append("часть поездки с папой")
    if "племянник" in t or "племянниц" in t or "внук" in t or "внучк" in t:
        rel = ensure_party("родственники")
        if "племянник" in t or "племянниц" in t:
            rel.setdefault("notes", []).append("поездка с племянником")
        if "внук" in t or "внучк" in t:
            rel.setdefault("notes", []).append("поездка с внуками")
    if "недел" in t and ("с мам" in t or "мамой" in t):
        ensure_party("семья").setdefault("notes", []).append("неделя с мамой")

    if parties:
        brief["party_preferences"] = parties

    destinations = _detect_destinations(t)
    cities = _detect_cities(t)
    regions = brief_stay_enrich._detect_regions(t)

    has_sea = "море" in t or "пляж" in t or "пляжн" in t
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
    for city_name, _tags in cities:
        pref = f"предпочтение по направлению: {city_name}"
        if pref not in activity_preferences:
            activity_preferences.append(pref)
    for region_name, _tags in regions:
        pref = f"предпочтение по направлению: {region_name}"
        if pref not in activity_preferences:
            activity_preferences.append(pref)
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
    elif brief.get("trip_duration_days_raw"):
        score += 1
    if (
        brief.get("budget_rub_max")
        or brief.get("budget_eur_max")
        or brief.get("budget_amount_max")
        or brief.get("budget_flexible")
    ):
        score += 3
    if brief.get("adults") or brief.get("kids_count"):
        score += 3
    if (
        brief.get("flight_hours_max")
        or brief.get("flight_hours_unrestricted")
        or "transfers_allowed" in brief
        or brief.get("flight_preferences")
    ):
        score += 2
    if "visa_required" in brief or brief.get("visa_status") or brief.get("visa_notes"):
        score += 2
    if brief.get("passports_status") or brief.get("passports_notes"):
        score += 1
    if brief_stay_enrich.stay_experience_sufficient(brief):
        score += 1
    if brief.get("activity_preferences"):
        score += 1
    return score


def _combine_climate(existing: str, new: str) -> str:
    if not existing:
        return new
    if not new or existing == new:
        return existing
    if existing in new:
        return new
    if new in existing:
        return existing
    return f"{existing} и {new}"


def _append_context_raw(out: Dict[str, Any], new_text: str) -> None:
    text = (new_text or "").strip()
    if not text:
        return
    prev = str(out.get("context_raw") or "").strip()
    if not prev:
        out["context_raw"] = text
    elif text not in prev:
        out["context_raw"] = f"{prev}\n{text}"


def merge_brief(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base or {})
    for k, v in (incoming or {}).items():
        if v is None:
            continue
        if k == "context_raw":
            _append_context_raw(out, str(v) if v else "")
            continue
        if k == "months":
            if _is_empty_brief_value(v):
                continue
            out.setdefault("months", [])
            for item in v:
                if item not in out["months"]:
                    out["months"].append(item)
            continue
        if k in {"visa_notes", "constraints_notes", "activity_preferences", "flight_preferences"}:
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
        if k == "stay_experience" and isinstance(v, dict):
            merged_se: Dict[str, Any] = dict(out.get("stay_experience") or {})
            for sub_key in ("setting", "accommodation_style", "trip_style"):
                if v.get(sub_key):
                    merged_se.setdefault(sub_key, [])
                    for item in v[sub_key]:
                        text = str(item).strip()
                        if text and text not in merged_se[sub_key]:
                            merged_se[sub_key].append(text)
            if v.get("season_note"):
                merged_se["season_note"] = str(v["season_note"]).strip()
            out[k] = merged_se
            continue
        if _is_empty_brief_value(v) and not _is_empty_brief_value(out.get(k)):
            continue
        out[k] = v
    brief_display.sync_trip_title(out)
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
    brief_stay_enrich.enrich_stay_from_context(brief)
    missing: list[str] = []
    if not brief.get("months") and not brief.get("date_range_raw"):
        missing.append("Окна дат (месяц/период) или гибкость")
    budget_ok = (
        bool(brief.get("budget_rub_max"))
        or bool(brief.get("budget_eur_max"))
        or bool(brief.get("budget_flexible"))
    )
    if not budget_ok:
        missing.append("Бюджет (хотя бы «до … ₽/€» или «бюджет гибкий»)")
    if not brief.get("adults") and not brief.get("kids_count"):
        missing.append("Кто едет (взрослые/дети)")
    flight_block_ok = (
        bool(brief.get("flight_hours_max"))
        or ("transfers_allowed" in brief)
        or bool(brief.get("flight_hours_unrestricted"))
        or bool(brief.get("flight_preferences"))
    )
    if not flight_block_ok:
        if _has_destination_hint(brief):
            missing.append(
                "Перелёт: прямой или с пересадками, класс (эконом/бизнес) — можно своими словами"
            )
        else:
            missing.append(
                "Перелёт (например, «до 5 часов», «прямой, эконом» или «пересадки допустимы»)"
            )
    # Визы/документы: извлекаем в бриф, но на этапе MVP не спрашиваем отдельно (PARSING_SPEC P3).
    if not brief_stay_enrich.stay_experience_sufficient(brief):
        missing.append(
            "Сценарий отдыха (море, горы, спокойный отель — можно своими словами)"
        )
    return missing


def parse_message_to_brief(
    text: str,
    *,
    role: str = "organizer",
    participant_name: str = "",
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Парсинг одного сообщения: rules → (опц.) LLM по режиму PARSER_MODE.
    Возвращает (плоский дельта-бриф, structured JSON или {}).
    """
    global LAST_PARSER_MODE
    rule_based = extract_brief_rule_based(text)
    structured: Dict[str, Any] = {}
    llm_flat: Dict[str, Any] = {}

    if role_llm_active():
        if role == "participant":
            structured = brief_pipeline.parse_participant_message(text, participant_name)
            llm_flat = brief_flat_mapper.participant_structured_to_flat(structured)
        else:
            structured = brief_pipeline.parse_organizer_message(text)
            llm_flat = brief_flat_mapper.organizer_structured_to_flat(structured)
        if llm_flat:
            LAST_PARSER_MODE = "role_llm+rules"
        else:
            LAST_PARSER_MODE = "role_llm_fallback"
    else:
        LAST_PARSER_MODE = "rules_only"

    flat = merge_brief(rule_based, llm_flat)
    brief_display.sync_trip_title(flat)
    return flat, structured


def extract_brief_from_text(
    text: str,
    *,
    role: str = "organizer",
    participant_name: str = "",
) -> Dict[str, Any]:
    flat, _structured = parse_message_to_brief(
        text, role=role, participant_name=participant_name
    )
    return flat


def restore_organizer_brief_from_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Если brief в storage обнулился, восстановить из organizer_dump."""
    brief = dict(event.get("brief") or {})
    if brief_completeness_score(brief) >= 4:
        return brief
    dump_text = event.get("organizer_dump")
    if isinstance(dump_text, str) and dump_text.strip():
        from_dump = extract_brief_from_text(dump_text)
        brief = merge_brief(from_dump, brief)
    brief_display.sync_trip_title(brief)
    return brief


_ORGANIZER_IMMUTABLE_IF_SET = frozenset(
    {
        "budget_rub_max",
        "adults",
        "kids_count",
        "kid_age",
        "months",
        "date_range_raw",
        "flight_hours_max",
        "flight_hours_unrestricted",
        "transfers_allowed",
        "visa_required",
        "visa_status",
        "passports_status",
        "documents_discussed",
    }
)


def merge_brief_clarify(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """Уточнение: дополняем бриф, не затираем уже зафиксированные поля."""
    out = dict(base or {})
    for k, v in (incoming or {}).items():
        if v is None:
            continue
        if k == "context_raw":
            _append_context_raw(out, str(v) if v else "")
            continue
        if k in {
            "months",
            "visa_notes",
            "constraints_notes",
            "activity_preferences",
            "passports_notes",
            "flight_preferences",
        }:
            if _is_empty_brief_value(v):
                continue
            out.setdefault(k, [])
            for item in v:
                if item not in out[k]:
                    out[k].append(item)
            continue
        if k == "climate":
            if _is_empty_brief_value(v):
                continue
            current = out.get("climate")
            if current and str(current) != str(v):
                out[k] = _combine_climate(str(current), str(v))
            elif not _is_empty_brief_value(current):
                out[k] = current
            else:
                out[k] = v
            continue
        if k == "stay_experience" and isinstance(v, dict):
            merged_se: Dict[str, Any] = dict(out.get("stay_experience") or {})
            for sub_key in ("setting", "accommodation_style", "trip_style"):
                if v.get(sub_key):
                    merged_se.setdefault(sub_key, [])
                    for item in v[sub_key]:
                        text = str(item).strip()
                        if text and text not in merged_se[sub_key]:
                            merged_se[sub_key].append(text)
            if v.get("season_note"):
                merged_se["season_note"] = str(v["season_note"]).strip()
            out[k] = merged_se
            continue
        if k == "budget_flexible" and v:
            out[k] = True
            continue
        if k == "budget_rub_min" and not _is_empty_brief_value(out.get("budget_rub_min")):
            continue
        if k in _ORGANIZER_IMMUTABLE_IF_SET and not _is_empty_brief_value(out.get(k)):
            continue
        if _is_empty_brief_value(v) and not _is_empty_brief_value(out.get(k)):
            continue
        out[k] = v
    brief_display.sync_trip_title(out)
    return out
