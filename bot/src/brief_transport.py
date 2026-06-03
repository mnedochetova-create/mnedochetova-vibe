"""Режим передвижения: перелёт (авиа) vs наземная поездка — label и отображение."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

TRIP_TRANSPORT_FLIGHT = "flight"
TRIP_TRANSPORT_GROUND = "ground"


def _search_text(brief: Dict[str, Any], extra: str = "") -> str:
    parts: List[str] = []
    if extra.strip():
        parts.append(extra.strip())
    raw = brief.get("context_raw")
    if isinstance(raw, str) and raw.strip():
        parts.append(raw)
    dump = brief.get("organizer_dump")
    if isinstance(dump, str) and dump.strip() and dump not in (raw or ""):
        parts.append(dump)
    return " ".join(parts).lower()


def is_domestic_russia_context(t: str, brief: Dict[str, Any]) -> bool:
    if brief.get("regions") or brief.get("must_visit_places"):
        return True
    if re.search(
        r"росси|област\w*|центральн\w*\s+росси|золот\w*\s+кольц|по\s+городам",
        t,
    ):
        return True
    for pref in brief.get("activity_preferences") or []:
        low = str(pref).lower()
        if "росси" in low or "центральн" in low:
            return True
    return False


def infer_trip_transport(brief: Dict[str, Any], text: str = "") -> str:
    """flight | ground — по накопленному контексту брифа и текущей реплике."""
    stored = brief.get("trip_transport")
    if stored in {TRIP_TRANSPORT_FLIGHT, TRIP_TRANSPORT_GROUND}:
        return str(stored)

    t = _search_text(brief, text)
    ground = 0
    flight = 0

    if re.search(r"без\s+перел", t):
        ground += 4
    if brief.get("flight_not_needed"):
        ground += 3
    if re.search(r"на\s+авто|автомобил|автопутешеств|на\s+машин|наземн", t):
        ground += 2
    if is_domestic_russia_context(t, brief):
        ground += 2
    if brief.get("drive_hours_max"):
        ground += 2
    if brief.get("ground_transport_notes"):
        ground += 1

    if re.search(r"перел[её]т|авиа|рейс|вылет", t) and not re.search(r"без\s+перел", t):
        flight += 1
    if brief.get("transfers_allowed") is True or brief.get("transfers_allowed") is False:
        flight += 2
    if brief.get("flight_preferences"):
        flight += 2
    if brief.get("flight_hours_unrestricted"):
        flight += 2
    if brief.get("flight_hours_max") and not re.search(r"без\s+перел", t):
        flight += 1

    if ground >= 2 and ground >= flight:
        return TRIP_TRANSPORT_GROUND
    if flight >= 2:
        return TRIP_TRANSPORT_FLIGHT
    if is_domestic_russia_context(t, brief):
        return TRIP_TRANSPORT_GROUND
    return TRIP_TRANSPORT_FLIGHT


def sync_trip_transport(brief: Dict[str, Any], text: str = "") -> str:
    mode = infer_trip_transport(brief, text)
    brief["trip_transport"] = mode
    return mode


def transport_field_label(brief: Dict[str, Any], text: str = "") -> str:
    return "Передвижение" if infer_trip_transport(brief, text) == TRIP_TRANSPORT_GROUND else "Перелёт"


def transport_field_icon(brief: Dict[str, Any], text: str = "") -> str:
    return "🚗" if infer_trip_transport(brief, text) == TRIP_TRANSPORT_GROUND else "✈️"


def transport_block_ok(brief: Dict[str, Any], text: str = "") -> bool:
    import brief_domestic_route

    if brief_domestic_route.is_domestic_auto_brief(brief):
        brief_domestic_route.apply_domestic_transport_defaults(brief)
    mode = infer_trip_transport(brief, text)
    if mode == TRIP_TRANSPORT_GROUND:
        notes = brief.get("ground_transport_notes") or []
        if any("автомобил" in str(n).lower() for n in notes):
            return True
        return bool(
            brief.get("drive_hours_max")
            or brief.get("flight_not_needed")
            or re.search(r"на\s+авто|автомобил", _search_text(brief, text))
        )
    return bool(
        brief.get("flight_hours_max")
        or brief.get("flight_hours_unrestricted")
        or "transfers_allowed" in brief
        or brief.get("flight_preferences")
    )


def transport_missing_hint(brief: Dict[str, Any], *, has_destination: bool, text: str = "") -> str:
    import brief_domestic_route

    label = transport_field_label(brief, text)
    if label == "Передвижение" and brief_domestic_route.is_domestic_auto_brief(brief):
        return (
            f"{label}: до N часов между точками (если важен лимит) — опционально"
        )
    if label == "Передвижение":
        return f"{label}: автомобиль или лимит часов в пути между точками"
    if has_destination:
        return f"{label}: прямой или с пересадками, класс (эконом/бизнес) — можно своими словами"
    return f"{label} (например, «до 5 часов», «прямой, эконом» или «пересадки допустимы»)"


def _transport_is_missing(brief: Dict[str, Any], missing: Optional[List[str]], text: str = "") -> bool:
    if missing:
        label = transport_field_label(brief, text)
        return any(str(item).startswith(label) for item in missing)
    return not transport_block_ok(brief, text)


def _format_flight_value(
    brief: Dict[str, Any],
    *,
    esc: Callable[[Any], str],
    missing: Optional[List[str]],
    text: str,
) -> str:
    parts: List[str] = []
    if brief.get("flight_hours_max"):
        parts.append(f"до {esc(brief['flight_hours_max'])} ч.")
    elif brief.get("flight_hours_unrestricted"):
        parts.append("без ограничений по длительности")
    if brief.get("transfers_allowed") is True:
        parts.append("пересадки допустимы")
    elif brief.get("transfers_allowed") is False:
        parts.append("прямой рейс")
    prefs = brief.get("flight_preferences") or []
    if prefs:
        parts.append(", ".join(esc(str(item)) for item in prefs))
    if parts:
        return " · ".join(parts)
    if _transport_is_missing(brief, missing, text):
        return "нужно указать: прямой или с пересадками, класс (эконом/бизнес)"
    return "—"


def _format_ground_value(
    brief: Dict[str, Any],
    *,
    esc: Callable[[Any], str],
    missing: Optional[List[str]],
    text: str,
) -> str:
    parts: List[str] = []
    if brief.get("flight_not_needed") or re.search(r"без\s+перел", _search_text(brief, text)):
        parts.append("перелёт не планируется")
    notes = [str(n) for n in (brief.get("ground_transport_notes") or []) if str(n).strip()]
    if any("автомобил" in n.lower() for n in notes) or re.search(
        r"на\s+авто|автомобил", _search_text(brief, text)
    ):
        if not any("автомобил" in p for p in parts):
            parts.append("автомобиль")
    for note in notes:
        low = note.lower()
        if "автомобил" in low and "автомобиль" not in parts:
            continue
        if note not in parts:
            parts.append(esc(note))
    if brief.get("drive_hours_max"):
        parts.append(f"до {esc(brief['drive_hours_max'])} ч. в пути")
    if parts:
        import brief_domestic_route

        if (
            brief_domestic_route.is_domestic_auto_brief(brief)
            and len(parts) == 1
            and parts[0] == "автомобиль"
        ):
            return "автомобиль (маршрут по регионам)"
        return " · ".join(parts)
    if _transport_is_missing(brief, missing, text):
        import brief_domestic_route

        if brief_domestic_route.is_domestic_auto_brief(brief):
            return "автомобиль (маршрут по регионам)"
        return "нужно указать: автомобиль или лимит часов в пути"
    return "—"


def format_transport_display(
    brief: Dict[str, Any],
    *,
    esc: Optional[Callable[[Any], str]] = None,
    missing: Optional[List[str]] = None,
    text: str = "",
) -> str:
    esc_fn = esc if callable(esc) else (lambda value: value)
    mode = infer_trip_transport(brief, text)
    if mode == TRIP_TRANSPORT_GROUND:
        return _format_ground_value(brief, esc=esc_fn, missing=missing, text=text)
    return _format_flight_value(brief, esc=esc_fn, missing=missing, text=text)


def format_flight_display(
    brief: Dict[str, Any],
    *,
    esc: Optional[Callable[[Any], str]] = None,
    missing: Optional[List[str]] = None,
) -> str:
    """Обратная совместимость: делегирует format_transport_display."""
    return format_transport_display(brief, esc=esc, missing=missing)


def reconcile_hours_fields(brief: Dict[str, Any], text: str = "") -> None:
    """После merge: часы в пути vs часы перелёта по режиму."""
    t = (text or "").lower()
    mode = sync_trip_transport(brief, text)
    if mode != TRIP_TRANSPORT_GROUND:
        return
    if brief.get("flight_hours_max") and not re.search(
        r"перел[её]т|авиа|рейс|вылет", t
    ):
        if not brief.get("drive_hours_max"):
            brief["drive_hours_max"] = brief.pop("flight_hours_max")
        else:
            brief.pop("flight_hours_max", None)
