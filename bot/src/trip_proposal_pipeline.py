"""LLM-генерация вариантов поездки (v2). v1 — rules в trip_from_brief."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import trip_from_brief


def trip_proposals_llm_enabled() -> bool:
    """Отдельный флаг на будущее; пока LLM-путь не подключён."""
    import env_util

    return env_util.env_flag("TRIP_PROPOSALS_LLM_ENABLED")


async def generate_proposals_llm(
    event: Dict[str, Any],
    *,
    recommendation_ready: Optional[Dict[str, Any]] = None,
    max_count: int = 3,
) -> List[Dict[str, Any]]:
    """
    Заглушка v2: при включённом LLM — вызов промпта `trip_proposal_system_prompt.md`.
    Сейчас возвращает пустой список (main использует rules-fallback).
    """
    _ = recommendation_ready or trip_from_brief.build_recommendation_ready(event)
    _ = max_count
    return []
