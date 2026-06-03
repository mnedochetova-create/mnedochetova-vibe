"""Планирование комбо нескольких стран (кейс «с чем совместить?»)."""

from __future__ import annotations

import re
from typing import Any, Dict, List

import brief_stay_enrich

COMBO_LINE_PREFIX = "собрать комбинацию стран:"


def all_destinations_ordered(t: str) -> List[str]:
    ordered: List[tuple[int, str]] = []
    seen: set[str] = set()
    for stem, name, _climate in brief_stay_enrich.DESTINATION_HINTS:
        if stem not in t or name in seen:
            continue
        if brief_stay_enrich._country_in_layover_context(t, stem):
            continue
        ordered.append((t.find(stem), name))
        seen.add(name)
    ordered.sort(key=lambda x: x[0])
    return [name for _pos, name in ordered]


def combo_preference_line(countries: List[str]) -> str:
    if not countries:
        return ""
    return f"{COMBO_LINE_PREFIX} {', '.join(countries)}"


def is_route_combo_planning(brief: Dict[str, Any]) -> bool:
    if brief.get("route_combo_planning"):
        return True
    return any(
        str(item).lower().startswith(COMBO_LINE_PREFIX)
        for item in (brief.get("activity_preferences") or [])
    )


def combo_line_from_brief(brief: Dict[str, Any]) -> str:
    for item in brief.get("activity_preferences") or []:
        text = str(item).strip()
        if text.lower().startswith(COMBO_LINE_PREFIX):
            return text
    return ""


def wants_max_sightseeing(t: str, brief: Dict[str, Any]) -> bool:
    blob = f"{t} {' '.join(str(x) for x in brief.get('activity_preferences') or [])}".lower()
    return bool(
        re.search(r"посмотреть\s+максим|максимум\s+достопримеч|как\s+можно\s+больше", blob)
        or "максимум достопримечательностей" in blob
    )


def apply_route_combo_planning(t: str, brief: Dict[str, Any]) -> bool:
    """
    Зафиксировать задачу «собрать комбо» в пожеланиях; снять ложный «отдых в одной стране».
    Возвращает True, если режим комбо применён.
    """
    if not brief_stay_enrich.is_comparison_mode(t):
        return False

    countries = all_destinations_ordered(t)
    if len(countries) < 2:
        return False

    combo_line = combo_preference_line(countries)
    prefs: List[str] = []
    for item in brief.get("activity_preferences") or []:
        low = str(item).lower().strip()
        if low.startswith("предпочтение по направлению:"):
            continue
        if low.startswith(COMBO_LINE_PREFIX):
            continue
        prefs.append(str(item).strip())

    ordered_prefs: List[str] = [combo_line]
    if wants_max_sightseeing(t, brief):
        goal = "максимум достопримечательностей"
        if goal not in prefs:
            ordered_prefs.append(goal)
    ordered_prefs.extend(prefs)
    brief["activity_preferences"] = ordered_prefs
    brief["route_combo_planning"] = True
    brief["destination_candidates"] = countries

    brief.pop("destination_alternatives", None)
    brief.pop("destination_primary", None)

    if wants_max_sightseeing(t, brief):
        brief.pop("climate", None)
        brief["trip_type"] = "экскурсии/город"

    se: Dict[str, Any] = dict(brief.get("stay_experience") or {})
    setting = list(countries)
    trip_style = [s for s in (se.get("trip_style") or []) if "пляж" not in str(s).lower()]
    if "планирование комбо маршрута" not in trip_style:
        trip_style.insert(0, "планирование комбо маршрута")
    se["setting"] = setting
    se["trip_style"] = trip_style
    se.pop("season_note", None)
    brief["stay_experience"] = se
    return True
