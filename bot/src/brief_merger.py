"""Merger: конфликты и сводка для организатора (без записи в плоский brief)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import brief_flat_mapper
import brief_pipeline


def append_organizer_structured(event: Dict[str, Any], structured: Dict[str, Any]) -> None:
    """Накопить structured-ответы организатора (последний — в base_brief_structured)."""
    if not isinstance(structured, dict) or not structured:
        return
    history: List[Dict[str, Any]] = list(event.get("organizer_structured_history") or [])
    if history and history[-1] == structured:
        event["base_brief_structured"] = structured
        return
    history.append(structured)
    event["organizer_structured_history"] = history
    event["base_brief_structured"] = structured


def build_merger_payload(
    event: Dict[str, Any],
    *,
    new_participant_input_json: Dict[str, Any],
    current_event_status: str,
) -> Dict[str, Any]:
    history = list(event.get("organizer_structured_history") or [])
    latest = event.get("base_brief_structured")
    if isinstance(latest, dict) and latest and (not history or history[-1] != latest):
        history = history + [latest]
    return {
        "flat_brief_json": event.get("brief") or {},
        "organizer_structured_history": history,
        "organizer_structured_latest": latest if isinstance(latest, dict) else {},
        "participant_inputs_json": event.get("participant_inputs_structured") or [],
        "new_participant_input_json": new_participant_input_json or {},
        "current_event_status": current_event_status or "active",
    }


def apply_merger_result(event: Dict[str, Any], merged: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """
    Сохранить результат merger на событии. Не меняет event['brief'].
    Возвращает (conflicts, open_questions) для карточки.
    """
    if not isinstance(merged, dict) or not merged:
        conflicts = list(event.get("group_conflicts") or [])
        questions = list(event.get("group_open_questions") or [])
        return conflicts, questions

    event["merger_result_structured"] = merged
    conflicts = brief_flat_mapper.conflicts_from_merger(merged)
    questions = open_questions_from_merger(merged)
    event["group_conflicts"] = conflicts
    event["group_open_questions"] = questions

    update_text = str(merged.get("organizer_update_text") or "").strip()
    if update_text:
        prev_pending = str(event.get("merger_pending_update_text") or "").strip()
        if update_text != prev_pending:
            event["merger_pending_update_text"] = update_text
            event.pop("merger_pending_accepted_at", None)
    return conflicts, questions


def open_questions_from_merger(merged: Dict[str, Any]) -> List[str]:
    if not isinstance(merged, dict):
        return []
    lines: List[str] = []
    for item in merged.get("open_questions") or []:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("question") or item.get("text") or item.get("description") or "").strip()
        else:
            text = str(item).strip()
        if text and text not in lines:
            lines.append(text)
    return lines


def run_merger_for_event(event: Dict[str, Any], *, current_event_status: str) -> Tuple[List[str], List[str], str]:
    """
    Вызов LLM merger. Возвращает (conflicts, open_questions, organizer_update_text).
    """
    participants = event.get("participant_inputs_structured") or []
    if not participants:
        conflicts = list(event.get("group_conflicts") or [])
        questions = list(event.get("group_open_questions") or [])
        return conflicts, questions, str(event.get("merger_pending_update_text") or "")

    new_input = participants[-1] if isinstance(participants[-1], dict) else {}
    payload = build_merger_payload(
        event,
        new_participant_input_json=new_input,
        current_event_status=current_event_status,
    )
    merged = brief_pipeline.merge_brief_inputs(**payload)
    conflicts, questions = apply_merger_result(event, merged)
    update_text = str(merged.get("organizer_update_text") or "").strip() if merged else ""
    return conflicts, questions, update_text


def should_notify_organizer_merger(event: Dict[str, Any], update_text: str) -> bool:
    if not update_text.strip():
        return False
    if not event.get("organizer_chat_id"):
        return False
    if event.get("merger_pending_accepted_at") and event.get("organizer_accepted_group_summary") == update_text:
        return False
    last_notified = str(event.get("merger_last_notified_update_text") or "").strip()
    return update_text != last_notified


def mark_merger_notified(event: Dict[str, Any], update_text: str) -> None:
    event["merger_last_notified_update_text"] = update_text.strip()
