"""Поездка из собранного брифа: recommendation-ready, readiness, черновики вариантов."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import brief_domestic_route
import brief_parser
import brief_route_combo

SCHEMA_VERSION = "1"
PROPOSAL_STATUS_DRAFT = "draft"

BLOCKER_BRIEF_NOT_CONFIRMED = "brief_not_confirmed"
BLOCKER_MISSING_DATES = "missing_dates"
BLOCKER_MISSING_BUDGET = "missing_budget"
BLOCKER_MISSING_DIRECTION = "missing_direction"
BLOCKER_MISSING_TRANSPORT = "missing_transport"

_BLOCKER_LABELS = {
    BLOCKER_BRIEF_NOT_CONFIRMED: "подтверди бриф поездки",
    BLOCKER_MISSING_DATES: "даты или период поездки",
    BLOCKER_MISSING_BUDGET: "бюджет (или «бюджет гибкий»)",
    BLOCKER_MISSING_DIRECTION: "направление или задача комбо/маршрут",
    BLOCKER_MISSING_TRANSPORT: "перелёт: часы в пути или пересадки",
}


def _now_ts() -> int:
    return int(time.time())


def _direction_labels_from_brief(brief: Dict[str, Any]) -> List[str]:
    labels: List[str] = []
    primary = brief.get("destination_primary")
    if isinstance(primary, str) and primary.strip():
        labels.append(primary.strip())
    for key in ("destination_alternatives", "destination_candidates"):
        raw = brief.get(key)
        if isinstance(raw, list):
            for item in raw:
                text = str(item).strip()
                if text and text not in labels:
                    labels.append(text)
    for item in brief.get("activity_preferences") or []:
        text = str(item).strip()
        low = text.lower()
        if low.startswith("предпочтение по направлению:"):
            part = text.split(":", 1)[-1].strip()
            if part and part not in labels:
                labels.append(part)
    se = brief.get("stay_experience") if isinstance(brief.get("stay_experience"), dict) else {}
    for item in se.get("setting") or []:
        text = str(item).strip()
        if text and len(text) > 2 and text not in labels:
            labels.append(text)
    return labels


def _resolve_trip_mode(brief: Dict[str, Any]) -> str:
    if brief_route_combo.is_route_combo_planning(brief):
        return "combo_route"
    if brief_domestic_route.is_domestic_auto_brief(brief) or brief.get("trip_transport") == "ground":
        return "domestic_ground"
    labels = _direction_labels_from_brief(brief)
    if len(labels) >= 2:
        return "explore"
    if labels:
        return "single_destination"
    return "explore"


def _combo_countries(brief: Dict[str, Any]) -> List[str]:
    line = brief_route_combo.combo_line_from_brief(brief)
    if not line:
        return []
    low = line.lower()
    prefix = brief_route_combo.COMBO_LINE_PREFIX
    if prefix in low:
        tail = line.split(":", 1)[-1].strip()
        return [c.strip() for c in tail.split(",") if c.strip()]
    return []


def _participant_highlights(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    prefs = (event.get("brief") or {}).get("participant_preferences") or {}
    out: List[Dict[str, Any]] = []
    for name, row in prefs.items():
        if not isinstance(row, dict):
            continue
        highlights: List[str] = []
        if row.get("flight_hours_max"):
            highlights.append(f"перелёт до {row['flight_hours_max']} ч.")
        if row.get("constraints_notes"):
            highlights.extend(str(x) for x in row["constraints_notes"][:2])
        if row.get("activity_preferences"):
            highlights.extend(str(x) for x in row["activity_preferences"][:2])
        out.append({"name": str(name), "highlights": highlights[:4]})
    return out


def build_recommendation_ready(event: Dict[str, Any]) -> Dict[str, Any]:
    """Плоский бриф + событие → нормализованный снимок для подбора."""
    brief = event.get("brief") or {}
    code = str(event.get("code") or "")
    se = brief.get("stay_experience") if isinstance(brief.get("stay_experience"), dict) else {}

    budget: Dict[str, Any] = {
        "rub_max": brief.get("budget_rub_max"),
        "eur_max": brief.get("budget_eur_max"),
        "currency": brief.get("budget_currency"),
        "flexible": bool(brief.get("budget_flexible")),
    }
    if brief.get("budget_amount_max"):
        budget["amount_max"] = brief.get("budget_amount_max")

    transport_mode = "ground" if brief_domestic_route.is_domestic_auto_brief(brief) else "flight"
    if brief.get("trip_transport") == "ground":
        transport_mode = "ground"

    return {
        "schema_version": SCHEMA_VERSION,
        "built_at": _now_ts(),
        "event_code": code,
        "trip_title": brief.get("trip_title") or "",
        "trip_mode": _resolve_trip_mode(brief),
        "destinations": {
            "primary": brief.get("destination_primary") or (_direction_labels_from_brief(brief)[:1] or [None])[0],
            "alternatives": list(brief.get("destination_alternatives") or []),
            "combo_countries": _combo_countries(brief),
            "regions": list(brief.get("regions") or []),
            "must_visit": list(brief.get("must_visit_places") or []),
            "labels": _direction_labels_from_brief(brief),
        },
        "dates": {
            "months": list(brief.get("months") or []),
            "date_range_raw": brief.get("date_range_raw"),
            "trip_duration_days_raw": brief.get("trip_duration_days_raw"),
            "flexible": not brief.get("months") and not brief.get("date_range_raw"),
        },
        "group": {
            "adults": brief.get("adults"),
            "kids_count": brief.get("kids_count"),
            "kid_ages": [brief.get("kid_age")] if brief.get("kid_age") else [],
        },
        "budget": budget,
        "transport": {
            "mode": transport_mode,
            "flight_hours_max": brief.get("flight_hours_max"),
            "transfers_allowed": brief.get("transfers_allowed"),
            "flight_hours_unrestricted": brief.get("flight_hours_unrestricted"),
            "flight_preferences": list(brief.get("flight_preferences") or []),
            "ground_notes": list(brief.get("ground_transport_notes") or []),
        },
        "stay_experience": {
            "setting": list(se.get("setting") or []),
            "accommodation_style": list(se.get("accommodation_style") or []),
            "trip_style": list(se.get("trip_style") or []),
            "season_note": str(se.get("season_note") or ""),
        },
        "constraints": {
            "hard": list(brief.get("group_conflicts") or []),
            "soft": list(brief.get("constraints_notes") or [])[:6],
        },
        "participants_summary": _participant_highlights(event),
        "group_signals": {
            "conflicts": list(brief.get("group_conflicts") or []),
            "open_questions": list(brief.get("group_open_questions") or []),
            "organizer_accepted_summary": event.get("organizer_accepted_group_summary"),
        },
        "provenance": {
            "organizer_dump_present": bool(str(event.get("organizer_dump") or "").strip()),
            "brief_confirmed_at": event.get("organizer_brief_confirmed_at"),
        },
    }


def assess_trip_readiness(
    event: Dict[str, Any],
    *,
    recommendation_ready: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Готовность к генерации черновиков вариантов."""
    ready = recommendation_ready or build_recommendation_ready(event)
    brief = event.get("brief") or {}
    blockers: List[str] = []
    warnings: List[str] = []

    if not event.get("organizer_brief_confirmed_at"):
        blockers.append(BLOCKER_BRIEF_NOT_CONFIRMED)

    dates = ready.get("dates") or {}
    if not dates.get("months") and not dates.get("date_range_raw"):
        blockers.append(BLOCKER_MISSING_DATES)

    budget = ready.get("budget") or {}
    has_budget = brief_parser.budget_is_set(brief)
    if not has_budget:
        blockers.append(BLOCKER_MISSING_BUDGET)

    dest = ready.get("destinations") or {}
    mode = ready.get("trip_mode") or "explore"
    has_direction = bool(
        dest.get("primary")
        or dest.get("labels")
        or dest.get("combo_countries")
        or dest.get("regions")
        or mode in ("combo_route", "domestic_ground")
    )
    if not has_direction:
        blockers.append(BLOCKER_MISSING_DIRECTION)

    transport = ready.get("transport") or {}
    if transport.get("mode") == "flight":
        has_flight_prefs = (
            transport.get("flight_hours_max") is not None
            or transport.get("flight_hours_unrestricted") is not None
            or transport.get("transfers_allowed") is not None
        )
        if not has_flight_prefs:
            blockers.append(BLOCKER_MISSING_TRANSPORT)

    conflicts = (ready.get("constraints") or {}).get("hard") or []
    if conflicts:
        warnings.append("есть расхождения между участниками — согласуй перед бронированием")

    if event.get("group_open_questions"):
        warnings.append("есть открытые вопросы по группе")

    return {
        "ready": len(blockers) == 0,
        "blockers": blockers,
        "blocker_labels": [_BLOCKER_LABELS.get(b, b) for b in blockers],
        "warnings": warnings,
    }


def _proposal_id(index: int) -> str:
    return f"p{index}"


def _template_proposals(ready: Dict[str, Any], *, max_count: int = 3) -> List[Dict[str, Any]]:
    """Черновики без LLM и без цен — шаблоны по trip_mode."""
    mode = ready.get("trip_mode") or "explore"
    title_base = ready.get("trip_title") or "Поездка"
    dest = ready.get("destinations") or {}
    primary = dest.get("primary") or (dest.get("labels") or ["направление"])[0]
    proposals: List[Dict[str, Any]] = []

    def pack(
        idx: int,
        title: str,
        dest_label: str,
        why: List[str],
        tradeoffs: List[str],
        tags: List[str],
    ) -> Dict[str, Any]:
        return {
            "proposal_id": _proposal_id(idx),
            "status": PROPOSAL_STATUS_DRAFT,
            "title": title,
            "destination_label": dest_label,
            "trip_mode": mode,
            "fit_score": round(0.9 - idx * 0.05, 2),
            "why_fit": why,
            "tradeoffs": tradeoffs + ["черновик без проверки цен и наличия"],
            "tags": tags,
            "next_steps_human": "Сверить с группой и уточнить вылет/отель",
            "data_sources": ["rules_template"],
            "external_links": [],
        }

    if mode == "combo_route":
        countries = dest.get("combo_countries") or dest.get("labels") or ["несколько стран"]
        label = ", ".join(str(c) for c in countries[:3])
        proposals.append(
            pack(
                1,
                f"Комбо-маршрут: {label}",
                label,
                ["в брифе зафиксирована задача собрать комбинацию стран", f"база: {title_base}"],
                ["нужно выбрать порядок стран и длительность в каждой"],
                ["комбо", "активный"],
            )
        )
        if max_count > 1:
            proposals.append(
                pack(
                    2,
                    f"Упор на одну страну: {primary}",
                    str(primary),
                    ["меньше перелётов между базами", "проще с детьми"],
                    ["остальные страны из комбо — на следующий раз"],
                    ["спокойный"],
                )
            )
        return proposals[:max_count]

    if mode == "domestic_ground":
        regions = dest.get("regions") or dest.get("labels") or ["Россия"]
        label = ", ".join(str(r) for r in regions[:2])
        proposals.append(
            pack(
                1,
                f"Наземный маршрут: {label}",
                label,
                ["поездка по РФ / авто", "без международного перелёта"],
                ["логистика между точками на месте"],
                ["авто", "семейный"],
            )
        )
        return proposals[:max_count]

    templates = [
        ("спокойный отдых", ["спокойный", "релакс"], ["меньше переездов"]),
        ("активная программа", ["экскурсии", "движение"], ["больше логистики"]),
        ("баланс отдых + впечатления", ["баланс"], ["компромисс по темпу"]),
    ]
    for idx, (suffix, tags, trade) in enumerate(templates[:max_count], start=1):
        proposals.append(
            pack(
                idx,
                f"{primary} · {suffix}",
                str(primary),
                [f"совпадает с направлением из брифа", f"режим: {suffix}"],
                trade,
                tags,
            )
        )
    return proposals


def generate_draft_proposals(
    event: Dict[str, Any],
    *,
    max_count: int = 3,
    recommendation_ready: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Вернуть (proposals, readiness). Пустой список если не ready."""
    ready_obj = recommendation_ready or build_recommendation_ready(event)
    readiness = assess_trip_readiness(event, recommendation_ready=ready_obj)
    if not readiness["ready"]:
        return [], readiness
    proposals = _template_proposals(ready_obj, max_count=max_count)
    return proposals, readiness


def apply_trip_proposals_to_event(
    event: Dict[str, Any],
    *,
    proposals: List[Dict[str, Any]],
    readiness: Dict[str, Any],
    recommendation_ready: Optional[Dict[str, Any]] = None,
) -> None:
    """Записать результат на событие (без save — вызывает main)."""
    event["recommendation_ready"] = recommendation_ready or build_recommendation_ready(event)
    if not readiness.get("ready"):
        event["trip_proposals_status"] = "blocked"
        event["trip_proposals"] = []
        event["trip_proposals_blockers"] = readiness.get("blocker_labels") or []
        return
    event["trip_proposals"] = proposals
    event["trip_proposals_status"] = "draft" if proposals else "blocked"
    event["trip_proposals_generated_at"] = _now_ts()
    event["trip_proposals_blockers"] = []


def prepare_trip_proposals_for_event(event: Dict[str, Any], *, max_count: int = 3) -> Dict[str, Any]:
    """Полный цикл: ready → generate → apply. Возвращает readiness."""
    ready_obj = build_recommendation_ready(event)
    proposals, readiness = generate_draft_proposals(
        event, max_count=max_count, recommendation_ready=ready_obj
    )
    apply_trip_proposals_to_event(
        event,
        proposals=proposals,
        readiness=readiness,
        recommendation_ready=ready_obj,
    )
    return readiness


def format_proposals_html(
    proposals: List[Dict[str, Any]],
    *,
    warnings: Optional[List[str]] = None,
) -> str:
    import html as html_mod

    if not proposals:
        return "Пока нет черновых вариантов."

    lines = [
        "🧭 <b>Варианты поездки</b> <i>(черновик, без проверки цен)</i>",
        "",
    ]
    if warnings:
        lines.append("⚠️ <b>На заметку</b>")
        for w in warnings:
            lines.append(f"• {html_mod.escape(w)}")
        lines.append("")

    for p in proposals:
        pid = html_mod.escape(str(p.get("proposal_id") or ""))
        title = html_mod.escape(str(p.get("title") or "Вариант"))
        dest = html_mod.escape(str(p.get("destination_label") or ""))
        score = p.get("fit_score")
        score_s = f" · fit {score}" if score is not None else ""
        lines.append(f"<b>{pid}</b> — {title}{score_s}")
        if dest:
            lines.append(f"📍 {dest}")
        why = p.get("why_fit") or []
        if why:
            lines.append("Почему подходит:")
            for item in why[:3]:
                lines.append(f"• {html_mod.escape(str(item))}")
        trade = p.get("tradeoffs") or []
        if trade:
            lines.append("Компромиссы:")
            for item in trade[:2]:
                lines.append(f"• {html_mod.escape(str(item))}")
        lines.append("")

    lines.append("<i>Это не бронь. Следующий шаг — согласовать с группой и уточнить перелёт.</i>")
    return "\n".join(lines)


def format_blockers_message(readiness: Dict[str, Any]) -> str:
    import html as html_mod

    labels = readiness.get("blocker_labels") or readiness.get("blockers") or []
    if not labels:
        return "Пока нельзя собрать варианты поездки."
    items = "\n".join(f"• {html_mod.escape(str(x))}" for x in labels)
    return (
        "🧭 <b>Варианты поездки</b>\n\n"
        "Чтобы предложить 2–3 черновика, не хватает:\n"
        f"{items}\n\n"
        "Дополни бриф или уточни вводные — затем снова «Показать варианты»."
    )
