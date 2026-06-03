import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import brief_flat_mapper
import brief_pipeline
import brief_display
import brief_stay_enrich
import brief_route_combo
import brief_transport
from parser_mode import role_llm_active


LAST_PARSER_MODE = "rules_only"


def get_last_parser_mode() -> str:
    return LAST_PARSER_MODE


_DESTINATION_HINTS = brief_stay_enrich.DESTINATION_HINTS

_MONTH_PATTERN = (
    r"январ[ья]?|феврал[ья]?|март[а]?|апрел[ья]?|ма[йя]|июн[ья]?|июл[ья]?|"
    r"август[а]?|сентябр[ья]?|октябр[ья]?|ноябр[ья]?|декабр[ья]?"
)

_MONTH_STEM_TO_FULL: Dict[str, str] = {
    "январ": "январь",
    "феврал": "февраль",
    "март": "март",
    "апрел": "апрель",
    "май": "май",
    "июн": "июнь",
    "июл": "июль",
    "август": "август",
    "сентябр": "сентябрь",
    "октябр": "октябрь",
    "ноябр": "ноябрь",
    "декабр": "декабрь",
}


def _normalize_month_token(token: str) -> str:
    low = (token or "").strip().lower()
    if not low:
        return low
    for stem, full in _MONTH_STEM_TO_FULL.items():
        if low == stem or low.startswith(stem):
            return full
    return low


def _append_month(brief: Dict[str, Any], stem: str) -> None:
    month = _normalize_month_token(stem)
    brief.setdefault("months", [])
    if month and month not in brief["months"]:
        brief["months"].append(month)


def _strip_comparison_visa_and_party(t: str, brief: Dict[str, Any]) -> None:
    if not brief_stay_enrich.is_comparison_mode(t):
        return
    notes = brief.get("visa_notes") or []
    filtered = [
        n
        for n in notes
        if "франц" not in str(n).lower() and "шенген" not in str(n).lower()
    ]
    if filtered != notes:
        if filtered:
            brief["visa_notes"] = filtered
        else:
            brief.pop("visa_notes", None)
        if not brief.get("visa_notes") and "виза" not in t and "шенген" not in t:
            brief.pop("visa_required", None)
            brief.pop("documents_discussed", None)
    parties = brief.get("party_preferences")
    if not isinstance(parties, dict):
        return
    org = parties.get("организатор")
    if not isinstance(org, dict):
        return
    wants = org.get("wants") or []
    alts = {str(a).lower() for a in (brief.get("destination_alternatives") or [])}
    new_wants = [w for w in wants if str(w).lower() not in alts]
    if new_wants != wants:
        if new_wants:
            org["wants"] = new_wants
        else:
            org.pop("wants", None)
        if not org:
            parties.pop("организатор", None)
        if not parties:
            brief.pop("party_preferences", None)


def _apply_destination_roles(t: str, brief: Dict[str, Any]) -> None:
    if brief_stay_enrich.is_comparison_mode(t):
        _strip_comparison_visa_and_party(t, brief)
        return

    primary, alternatives = brief_stay_enrich.destinations_with_roles(t)
    if not primary and not alternatives:
        return
    if primary:
        brief["destination_primary"] = primary
        if not brief.get("climate"):
            for stem, name, default_climate in _DESTINATION_HINTS:
                if name == primary:
                    brief["climate"] = default_climate
                    break
    if alternatives:
        brief["destination_alternatives"] = alternatives
    elif brief.get("destination_alternatives"):
        brief.pop("destination_alternatives", None)

    activity_preferences: List[str] = []
    non_direction: List[str] = []
    for item in brief.get("activity_preferences") or []:
        low = str(item).lower()
        if low.startswith("предпочтение по направлению:"):
            continue
        non_direction.append(str(item))
    if primary:
        activity_preferences.append(f"предпочтение по направлению: {primary}")
    activity_preferences.extend(non_direction)
    if activity_preferences:
        brief["activity_preferences"] = activity_preferences

    se = dict(brief.get("stay_experience") or {})
    setting = [str(s) for s in (se.get("setting") or [])]
    country_names = {primary, *alternatives} if primary else set(alternatives)
    trimmed = [
        s
        for s in setting
        if s not in country_names
        or (primary and s == primary)
    ]
    if primary and primary not in trimmed:
        trimmed.insert(0, primary)
    if trimmed:
        se["setting"] = trimmed
        brief["stay_experience"] = se
    _strip_comparison_visa_and_party(t, brief)


def _extract_domestic_route(t: str, brief: Dict[str, Any]) -> None:
    """Маршрут по России: области, must-visit, наземный сценарий."""
    regions: List[str] = []
    for stem, label, _tags in brief_stay_enrich.REGION_HINTS:
        if stem in ("центральн",):
            continue
        if stem in t and "област" in t and label not in regions:
            regions.append(label)
    m = re.search(r"центральн\w*\s+росси", t)
    if m:
        pref = "предпочтение по направлению: Центральная Россия"
        brief.setdefault("activity_preferences", [])
        if pref not in brief["activity_preferences"]:
            brief["activity_preferences"].append(pref)

    must_visit: List[str] = []
    for stem, label, _tags in brief_stay_enrich.CITY_HINTS:
        if stem in ("палех", "гороховец", "дивеев") and stem in t:
            must_visit.append(label)
    if must_visit:
        brief["must_visit_places"] = must_visit
        prefs = brief.get("activity_preferences") or []
        brief["activity_preferences"] = [
            p
            for p in prefs
            if not (
                str(p).lower().startswith("предпочтение по направлению:")
                and str(p).split(":", 1)[-1].strip() in must_visit
            )
        ]

    if regions:
        brief["regions"] = regions
        se = dict(brief.get("stay_experience") or {})
        setting = list(se.get("setting") or [])
        for r in regions:
            if r not in setting:
                setting.append(r)
        for place in must_visit:
            if place not in setting:
                setting.append(place)
        if setting:
            se["setting"] = setting
            brief["stay_experience"] = se

    if (
        regions
        or must_visit
        or re.search(r"росси|област\w*|по\s+городам|путешеств", t)
    ):
        brief["trip_transport"] = brief_transport.TRIP_TRANSPORT_GROUND
        if re.search(r"путешеств|по\s+городам|экскурс", t):
            brief["trip_type"] = "автопутешествие / региональный тур"

    if re.search(r"проживан\w*", t) and re.search(r"домик|коттедж|гостев|кухн|уедин", t):
        import brief_domestic_route

        phrase = brief_domestic_route._extract_accommodation_phrase(t)
        if phrase:
            se = dict(brief.get("stay_experience") or {})
            acc = list(se.get("accommodation_style") or [])
            if phrase not in acc:
                acc.insert(0, phrase)
            se["accommodation_style"] = acc
            brief["stay_experience"] = se
    if re.search(r"домик|коттедж|гостев", t) and (
        "кухн" in t or "уедин" in t or "необычн" in t
    ):
        se = dict(brief.get("stay_experience") or {})
        acc = list(se.get("accommodation_style") or [])
        for label in ("домик с кухней", "уединённое размещение"):
            if label not in acc:
                acc.append(label)
        if acc:
            se["accommodation_style"] = acc
            brief["stay_experience"] = se


def _ground_travel_context(t: str, brief: Dict[str, Any]) -> bool:
    if brief.get("trip_transport") == brief_transport.TRIP_TRANSPORT_GROUND:
        return True
    if re.search(r"без\s+перел|на\s+авто|автомобил|автопутешеств", t):
        return True
    return brief_transport.is_domestic_russia_context(t, brief)


def _apply_ground_transport_signals(t: str, brief: Dict[str, Any]) -> None:
    if re.search(r"без\s+перел", t):
        brief["flight_not_needed"] = True
        brief["trip_transport"] = brief_transport.TRIP_TRANSPORT_GROUND
        brief.setdefault("ground_transport_notes", [])
        note = "перелёт не планируется"
        if note not in brief["ground_transport_notes"]:
            brief["ground_transport_notes"].append(note)
    if re.search(r"на\s+авто|автомобил|автопутешеств|на\s+машин", t):
        brief["trip_transport"] = brief_transport.TRIP_TRANSPORT_GROUND
        brief.setdefault("ground_transport_notes", [])
        if "автомобиль" not in brief["ground_transport_notes"]:
            brief["ground_transport_notes"].append("автомобиль")


def _parse_travel_hours_limit(t: str, brief: Dict[str, Any]) -> None:
    m = re.search(r"(?:до|не\s*больше|не\s*более)\s*(\d{1,2})\s*(?:ч|час(?:ов|а)?)\b", t)
    if not m:
        m = re.search(
            r"(?:перел[её]?т|пол[её]т)\s*(?:до|не\s*больше|не\s*более)?\s*(\d{1,2})\s*(?:ч|час(?:ов|а)?)\b",
            t,
        )
    if not m:
        m = re.search(
            r"(\d{1,2})\s*(?:ч|час(?:ов|а)?)\s*(?:максимум|макс|не\s*больше)(?:\s*на\s*(?:перел[её]т|пол[её]т))?",
            t,
        )
    if not m:
        return
    hours = int(m.group(1))
    flight_ctx = bool(
        re.search(r"перел[её]т|авиа|рейс|вылет", t) and not re.search(r"без\s+перел", t)
    )
    if _ground_travel_context(t, brief) and not flight_ctx:
        brief["drive_hours_max"] = hours
        brief.pop("flight_hours_max", None)
    else:
        brief["flight_hours_max"] = hours


def _brief_context_text(brief: Dict[str, Any], message_text: str = "") -> str:
    parts: List[str] = []
    if (message_text or "").strip():
        parts.append(message_text.strip())
    dump = brief.get("organizer_dump")
    if isinstance(dump, str) and dump.strip():
        parts.append(dump.strip())
    raw = brief.get("context_raw")
    if isinstance(raw, str) and raw.strip() and raw not in "\n".join(parts):
        parts.append(raw.strip())
    return "\n".join(parts)


def _finalize_brief_from_text(brief: Dict[str, Any], text: str) -> None:
    t = (text or "").lower()
    if brief.get("months"):
        brief["months"] = [_normalize_month_token(m) for m in brief["months"]]
        seen: List[str] = []
        for m in brief["months"]:
            if m and m not in seen:
                seen.append(m)
        brief["months"] = seen
    _apply_destination_roles(t, brief)
    brief_route_combo.apply_route_combo_planning(t, brief)
    _extract_domestic_route(t, brief)
    brief_transport.sync_trip_transport(brief, text)
    brief_transport.reconcile_hours_fields(brief, text)
    import brief_domestic_route

    brief_domestic_route.normalize_brief_stay_settings(brief)


def _detect_destinations(t: str) -> List[Tuple[str, str]]:
    return brief_stay_enrich._detect_destinations(t)


def _detect_cities(t: str) -> List[Tuple[str, List[str]]]:
    return brief_stay_enrich._detect_cities(t)


def _normalize_layover_hub(raw: str) -> str:
    low = (raw or "").strip().lower()
    if low in {"турция", "турции", "турцию"}:
        return "Турции"
    if low.endswith("ии"):
        return raw.strip()[:-2] + "ия"
    if low.endswith("и"):
        return raw.strip()[:-1] + "ия"
    return raw.strip().title() if raw.islower() else raw.strip()


def _extract_layover_flight_preferences(t: str) -> list[str]:
    """Пересадка/транзит с ночёвкой у аэропорта — не destination поездки."""
    if not re.search(r"(?:пересадк|стыковк|транзит|остановк)", t):
        return []
    prefs: list[str] = []
    long_layover = bool(
        re.search(r"(?:долг|длинн)\w*\s+пересад", t)
        or ("пересад" in t and ("долг" in t or "длинн" in t))
    )
    m = re.search(r"пересадк\w*\s+в\s+([a-zа-яё\-]+)", t)
    hub = _normalize_layover_hub(m.group(1)) if m else ""
    if long_layover:
        prefs.append(f"долгая пересадка в {hub}" if hub else "долгая пересадка")
    if "аэропорт" in t and ("отел" in t or "поспать" in t or "сон" in t or "ноч" in t):
        prefs.append("отель у аэропорта для отдыха на пересадке")
    return prefs


def _money_to_rub(num: int, suffix: str) -> int:
    suffix = (suffix or "").strip()
    if suffix in {"к", "т", "тыс", "тыщ", "тысяч"}:
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
        r"(к|т|тыс|тыщ|тысяч|млн|миллион[а-я]*|000|руб|₽)?",
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

    for mon in _MONTH_STEM_TO_FULL:
        if mon in t:
            _append_month(brief, mon)

    m = re.search(
        rf"(?:в\s+)?(конец|конц[ае]|начал[оае]?|середин[аые]?|середине|первая\s+половина|вторая\s+половина)\s+({_MONTH_PATTERN})",
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

    _apply_ground_transport_signals(t, brief)
    _extract_domestic_route(t, brief)
    _parse_travel_hours_limit(t, brief)

    if (
        "можно с пересад" in t
        or "пересадки можно" in t
        or "пересадки ок" in t
        or "пересадки норм" in t
        or "допустимы пересад" in t
        or "пересадки допустим" in t
        or "с пересадк" in t
        or re.search(r"с\s*\d+\s*пересад", t)
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
    if "перел" in t or "рейс" in t or "вылет" in t or "авиа" in t:
        m_dep = re.search(
            r"(?:перел[её]?т|вылет|рейс)\s+из\s+([a-zа-яё\-]+(?:\s+[a-zа-яё\-]+)?)",
            t,
        )
        if not m_dep:
            m_dep = re.search(r"\bиз\s+([a-zа-яё\-]+(?:\s+[a-zа-яё\-]+)?)\b", t)
        if m_dep:
            city = m_dep.group(1).strip()
            if city:
                low_city = city.lower()
                if low_city in {"москва", "москвы"}:
                    label = "Москвы"
                else:
                    label = city.title() if city.islower() else city
                pref = f"из {label}"
                if pref not in flight_preferences:
                    flight_preferences.append(pref)
    layover_prefs = _extract_layover_flight_preferences(t)
    if layover_prefs:
        flight_preferences.extend(p for p in layover_prefs if p not in flight_preferences)
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

    france_visa_context = "франц" in t and not brief_stay_enrich._country_in_comparison_context(
        t, "франц"
    )
    if "шенген" in t or "шэнген" in t or france_visa_context:
        brief.setdefault("visa_notes", [])
        brief.setdefault("documents_discussed", True)
        brief.setdefault("visa_required", True)
        if france_visa_context:
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
    if ("франц" in t or "во францию" in t) and not brief_stay_enrich._country_in_comparison_context(
        t, "франц"
    ):
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


def _is_zero_placeholder(value: Any, key: str) -> bool:
    """LLM иногда возвращает 0 вместо «не указано» — не затираем им заполненные поля."""
    if key not in {
        "adults",
        "kids_count",
        "kid_age",
        "budget_rub_max",
        "budget_rub_min",
        "budget_eur_max",
        "budget_amount_max",
        "flight_hours_max",
    }:
        return False
    return value == 0 or value == 0.0


def budget_is_set(brief: Dict[str, Any]) -> bool:
    """Любая явно зафиксированная сумма или «бюджет гибкий» (P1)."""
    if brief.get("budget_flexible"):
        return True
    if brief.get("budget_rub_max") or brief.get("budget_rub_min"):
        return True
    if brief.get("budget_eur_max") or brief.get("budget_amount_max"):
        return True
    currency = (brief.get("budget_currency") or "").strip().upper()
    if currency:
        keyed = f"budget_{currency.lower()}_max"
        if brief.get(keyed):
            return True
    for key, value in (brief or {}).items():
        if (
            key.startswith("budget_")
            and key.endswith("_max")
            and key not in {"budget_rub_max", "budget_eur_max", "budget_amount_max"}
            and isinstance(value, int)
            and value > 0
        ):
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
    if budget_is_set(brief):
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
        if _is_zero_placeholder(v, k):
            continue
        if k == "context_raw":
            _append_context_raw(out, str(v) if v else "")
            continue
        if k == "months":
            if _is_empty_brief_value(v):
                continue
            out.setdefault("months", [])
            for item in v:
                norm = _normalize_month_token(str(item))
                if norm and norm not in out["months"]:
                    out["months"].append(norm)
            continue
        if k in {
            "destination_primary",
            "destination_alternatives",
            "destination_candidates",
            "route_combo_planning",
            "trip_transport",
            "flight_not_needed",
            "drive_hours_max",
        }:
            if _is_empty_brief_value(v):
                continue
            out[k] = v
            continue
        if k in {"regions", "must_visit_places", "ground_transport_notes"}:
            if _is_empty_brief_value(v):
                continue
            out.setdefault(k, [])
            for item in v:
                if item not in out[k]:
                    out[k].append(item)
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


_PARTICIPANT_GROUP_LIST_FIELDS = frozenset(
    {"flight_preferences", "constraints_notes", "passports_notes", "visa_notes"}
)


def merge_participant_into_brief(
    base: Dict[str, Any],
    incoming: Dict[str, Any],
    participant_name: str,
) -> Dict[str, Any]:
    """Вклад участника — в participant_preferences; в общий бриф только перелёт/ограничения."""
    out = dict(base or {})
    for k, v in (incoming or {}).items():
        if v is None or k in {"context_raw", "trip_title", "participant_name"}:
            continue
        if k not in _PARTICIPANT_GROUP_LIST_FIELDS:
            continue
        if k in {"passports_notes", "visa_notes", "constraints_notes", "flight_preferences"}:
            if _is_empty_brief_value(v):
                continue
            out.setdefault(k, [])
            for item in v:
                text = str(item).strip()
                if text and text not in out[k]:
                    out[k].append(text)
            continue

    out.setdefault("participant_preferences", {})
    out["participant_preferences"][participant_name] = dict(incoming or {})
    return out


def merge_organizer_incoming(
    existing_brief: Dict[str, Any],
    incoming: Dict[str, Any],
    *,
    flow_step: str,
    has_prior_dump: bool = False,
) -> Dict[str, Any]:
    """Первый dump — merge_brief; уточнения и продолжение dump — merge_brief_clarify."""
    has_base = brief_completeness_score(existing_brief) > 0 or has_prior_dump
    if flow_step == "organizer_clarify" or (flow_step == "organizer_dump" and has_base):
        return merge_brief_clarify(existing_brief, incoming)
    return merge_brief(existing_brief, incoming)


def missing_brief_fields(brief: Dict[str, Any]) -> list[str]:
    brief_stay_enrich.enrich_stay_from_context(brief)
    missing: list[str] = []
    if not brief.get("months") and not brief.get("date_range_raw"):
        missing.append("Окна дат (месяц/период) или гибкость")
    if not budget_is_set(brief):
        missing.append("Бюджет (хотя бы «до … ₽/€/$» или «бюджет гибкий»)")
    if not brief.get("adults") and not brief.get("kids_count"):
        missing.append("Кто едет (взрослые/дети)")
    if not brief_route_combo.is_route_combo_planning(brief) and not brief_transport.transport_block_ok(
        brief
    ):
        missing.append(
            brief_transport.transport_missing_hint(
                brief, has_destination=_has_destination_hint(brief)
            )
        )
    # Визы/документы: извлекаем в бриф, но на этапе MVP не спрашиваем отдельно (PARSING_SPEC P3).
    if not brief_stay_enrich.stay_experience_sufficient(brief):
        missing.append(
            "Сценарий отдыха (море, горы, спокойный отель — можно своими словами)"
        )
    if brief_route_combo.is_route_combo_planning(brief) and not brief.get(
        "trip_duration_days_raw"
    ):
        hint = "Сколько дней на комбо (например 10–14) или «гибко по срокам»"
        if hint not in missing:
            missing.append(hint)
    return missing


def _is_completion_only_message(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in {"готово", "всё", "все", "ок", "готов", "готова", "done"}


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
    if _is_completion_only_message(text):
        return {}, {}
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
    _finalize_brief_from_text(flat, _brief_context_text(flat, text))
    ctx = _brief_context_text(flat, text)
    brief_transport.sync_trip_transport(flat, ctx)
    brief_transport.reconcile_hours_fields(flat, ctx)
    brief_display.sync_trip_title(flat)
    return flat, structured


def finalize_organizer_brief(brief: Dict[str, Any]) -> Dict[str, Any]:
    """Пересобрать выводы rules/combo по полному organizer_dump (после merge и LLM)."""
    ctx = _brief_context_text(brief, "")
    if ctx.strip():
        _finalize_brief_from_text(brief, ctx)
    brief_transport.sync_trip_transport(brief, ctx)
    brief_transport.reconcile_hours_fields(brief, ctx)
    brief_display.sync_trip_title(brief)
    return brief


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


def organizer_core_brief_ok(brief: Dict[str, Any]) -> bool:
    """Базовый бриф собран: состав, даты и бюджет (не только перелёт/сценарий)."""
    has_party = bool(brief.get("adults") or brief.get("kids_count"))
    has_dates = bool(brief.get("months") or brief.get("date_range_raw"))
    return has_party and has_dates and budget_is_set(brief)


def restore_organizer_brief_from_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Восстановить бриф из organizer_dump, подготовить к карточке и записать в event."""
    import brief_domestic_route

    brief = dict(event.get("brief") or {})
    dump_text = event.get("organizer_dump")
    has_dump = isinstance(dump_text, str) and bool(dump_text.strip())
    if has_dump:
        from_dump = extract_brief_from_text(dump_text)
        brief = merge_brief(from_dump, brief)
        brief["organizer_dump"] = dump_text
        brief = finalize_organizer_brief(brief)
    if has_dump and not str(brief.get("context_raw") or "").strip():
        brief["context_raw"] = dump_text.strip()
    brief_domestic_route.prepare_brief_for_display(brief)
    event["brief"] = brief
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
        if _is_zero_placeholder(v, k):
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
            "regions",
            "must_visit_places",
            "ground_transport_notes",
        }:
            if _is_empty_brief_value(v):
                continue
            out.setdefault(k, [])
            for item in v:
                if item not in out[k]:
                    out[k].append(item)
            continue
        if k in {
            "destination_primary",
            "destination_alternatives",
            "destination_candidates",
            "route_combo_planning",
            "trip_transport",
            "flight_not_needed",
            "drive_hours_max",
        }:
            if _is_empty_brief_value(v):
                continue
            out[k] = v
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
