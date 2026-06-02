"""Маппинг structured JSON (organizer/participant parser) → плоский бриф PARSING_SPEC."""

from typing import Any, Dict, List, Optional


def _unwrap(node: Any) -> Any:
    if isinstance(node, dict) and "value" in node:
        return node["value"]
    return node


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def _set_if_present(out: Dict[str, Any], key: str, value: Any) -> None:
    if _is_empty(value):
        return
    out[key] = value


def _append_unique_strings(target: List[str], items: Any) -> None:
    if _is_empty(items):
        return
    if isinstance(items, str):
        candidates = [items]
    elif isinstance(items, list):
        candidates = [str(x) for x in items if not _is_empty(x)]
    else:
        candidates = [str(items)]
    for item in candidates:
        text = item.strip()
        if text and text not in target:
            target.append(text)


def _direction_label(raw: Any) -> Optional[str]:
    value = _unwrap(raw)
    if _is_empty(value):
        return None
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("name", "country", "region", "label", "destination"):
            part = value.get(key)
            if part and not _is_empty(part):
                return str(part).strip()
        return str(value).strip()
    return str(value).strip()


def _map_scalar_section(section: Optional[Dict[str, Any]], mapping: Dict[str, str], out: Dict[str, Any]) -> None:
    if not isinstance(section, dict):
        return
    for src_key, dst_key in mapping.items():
        if src_key not in section:
            continue
        val = _unwrap(section[src_key])
        if not _is_empty(val):
            out[dst_key] = val


def _map_months(section: Dict[str, Any], out: Dict[str, Any]) -> None:
    if "months" not in section:
        return
    raw = _unwrap(section["months"])
    if isinstance(raw, list):
        months = [str(m).strip().lower() for m in raw if not _is_empty(m)]
    elif isinstance(raw, str) and raw.strip():
        months = [raw.strip().lower()]
    else:
        return
    if months:
        out["months"] = months


def _map_documents(section: Optional[Dict[str, Any]], out: Dict[str, Any]) -> None:
    if not isinstance(section, dict):
        return
    _map_scalar_section(
        section,
        {
            "documents_discussed": "documents_discussed",
            "passports_status": "passports_status",
            "visa_status": "visa_status",
            "visa_required": "visa_required",
        },
        out,
    )
    for notes_key, dst in (("visa_notes", "visa_notes"), ("passports_notes", "passports_notes")):
        if notes_key not in section:
            continue
        val = _unwrap(section[notes_key])
        out.setdefault(dst, [])
        _append_unique_strings(out[dst], val)


def _map_activity_and_constraints(
    preferences: Optional[Dict[str, Any]],
    constraints: Optional[Dict[str, Any]],
    out: Dict[str, Any],
) -> None:
    prefs = preferences if isinstance(preferences, dict) else {}
    cons = constraints if isinstance(constraints, dict) else {}

    _set_if_present(out, "climate", _unwrap(prefs.get("climate")))
    _set_if_present(out, "trip_type", _unwrap(prefs.get("trip_type")))

    activities: List[str] = []
    for key in (
        "activity_preferences",
        "location_preferences",
        "accommodation_preferences",
        "food_preferences",
        "additional_wishes",
        "pace_preferences",
        "children_needs",
    ):
        if key in prefs:
            _append_unique_strings(activities, _unwrap(prefs[key]))

    party = prefs.get("party_preferences")
    if isinstance(party, dict) and party:
        out["party_preferences"] = party
    elif party is not None and not _is_empty(_unwrap(party)):
        out["party_preferences"] = _unwrap(party)

    _map_scalar_section(
        cons,
        {
            "flight_hours_max": "flight_hours_max",
            "transfers_allowed": "transfers_allowed",
            "flight_hours_unrestricted": "flight_hours_unrestricted",
            "visa_required": "visa_required",
        },
        out,
    )
    notes: List[str] = []
    for key in ("other_constraints", "health_or_mobility_constraints", "budget_constraints", "date_constraints"):
        if key in cons:
            _append_unique_strings(notes, _unwrap(cons[key]))
    if notes:
        out.setdefault("constraints_notes", [])
        _append_unique_strings(out["constraints_notes"], notes)

    if activities:
        out.setdefault("activity_preferences", [])
        _append_unique_strings(out["activity_preferences"], activities)


def organizer_structured_to_flat(data: Dict[str, Any]) -> Dict[str, Any]:
    """Structured organizer parser JSON → плоские поля брифа."""
    if not isinstance(data, dict) or not data:
        return {}

    # Уже плоский ответ (legacy LLM) — пропускаем nested-маппинг.
    if "facts" not in data and "preferences" not in data and any(
        k in data for k in ("budget_rub_max", "adults", "climate", "months")
    ):
        return {k: v for k, v in data.items() if v is not None}

    out: Dict[str, Any] = {}
    if data.get("context_raw"):
        out["context_raw"] = str(data["context_raw"]).strip()

    facts = data.get("facts") if isinstance(data.get("facts"), dict) else {}
    _map_scalar_section(
        facts,
        {
            "adults": "adults",
            "kids_count": "kids_count",
            "budget_rub_max": "budget_rub_max",
            "date_range_raw": "date_range_raw",
            "trip_duration_days_raw": "trip_duration_days_raw",
        },
        out,
    )
    _map_months(facts, out)

    kids_ages = facts.get("kids_ages")
    if kids_ages is not None:
        ages = _unwrap(kids_ages)
        if isinstance(ages, list) and ages:
            out["kid_age"] = ages[0]
            if "kids_count" not in out:
                out["kids_count"] = len(ages)
        elif isinstance(ages, (int, float)):
            out["kid_age"] = int(ages)

    dest_label = _direction_label(facts.get("destination"))
    if dest_label:
        out.setdefault("activity_preferences", [])
        pref = f"предпочтение по направлению: {dest_label}"
        if pref not in out["activity_preferences"]:
            out["activity_preferences"].append(pref)

    dest_raw = facts.get("destination_raw")
    if dest_raw is not None and not _is_empty(_unwrap(dest_raw)):
        out.setdefault("activity_preferences", [])
        _append_unique_strings(out["activity_preferences"], _unwrap(dest_raw))

    _map_activity_and_constraints(data.get("preferences"), data.get("constraints"), out)
    _map_documents(data.get("documents"), out)

    return out


def participant_structured_to_flat(data: Dict[str, Any]) -> Dict[str, Any]:
    """Structured participant parser JSON → плоские поля вклада участника."""
    if not isinstance(data, dict) or not data:
        return {}

    if "personal_facts" not in data and any(
        k in data for k in ("budget_rub_max", "adults", "climate", "months")
    ):
        return {k: v for k, v in data.items() if v is not None and k != "participant_name"}

    out: Dict[str, Any] = {}
    if data.get("context_raw"):
        out["context_raw"] = str(data["context_raw"]).strip()

    facts = data.get("personal_facts") if isinstance(data.get("personal_facts"), dict) else {}
    _map_scalar_section(
        facts,
        {
            "adults": "adults",
            "kids_count": "kids_count",
            "budget_rub_max": "budget_rub_max",
            "date_range_raw": "date_range_raw",
            "trip_duration_days_raw": "trip_duration_days_raw",
        },
        out,
    )
    _map_months(facts, out)

    kids_ages = facts.get("kids_ages")
    if kids_ages is not None:
        ages = _unwrap(kids_ages)
        if isinstance(ages, list) and ages:
            out["kid_age"] = ages[0]
            if "kids_count" not in out:
                out["kids_count"] = len(ages)

    prefs = data.get("personal_preferences") if isinstance(data.get("personal_preferences"), dict) else {}
    cons = data.get("personal_constraints") if isinstance(data.get("personal_constraints"), dict) else {}

    dest_label = _direction_label(prefs.get("destination"))
    if dest_label:
        out.setdefault("activity_preferences", [])
        pref = f"предпочтение по направлению: {dest_label}"
        if pref not in out["activity_preferences"]:
            out["activity_preferences"].append(pref)

    _map_activity_and_constraints(prefs, cons, out)
    _map_documents(data.get("documents"), out)

    return out


def conflicts_from_merger(merged: Dict[str, Any]) -> List[str]:
    """Человекочитаемые строки расхождений для карточки брифа."""
    if not isinstance(merged, dict):
        return []
    lines: List[str] = []
    for item in merged.get("conflicts") or []:
        if not isinstance(item, dict):
            continue
        topic = str(item.get("topic") or "").strip()
        desc = str(item.get("description") or "").strip()
        issue = str(item.get("issue_type") or "").strip()
        if topic and desc and desc != topic:
            line = f"{topic}: {desc}"
        elif desc:
            line = desc
        elif topic:
            line = topic
        else:
            line = "расхождение между участниками"
        if issue == "hard_conflict":
            line = f"⚠️ {line}"
        if line not in lines:
            lines.append(line)
    return lines
