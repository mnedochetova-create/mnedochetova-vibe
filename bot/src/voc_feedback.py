"""VOC после готового брифа: оценка и открытый отзыв."""

from __future__ import annotations

from typing import Any, Dict, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def voc_rating_keyboard() -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(text=str(n), callback_data=f"voc:rate:{n}")
        for n in range(1, 6)
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            row,
            [InlineKeyboardButton(text="Пропустить · Skip", callback_data="voc:skip")],
        ]
    )


def parse_rating_from_text(text: str) -> Optional[int]:
    t = (text or "").strip()
    if t.isdigit():
        n = int(t)
        if 1 <= n <= 5:
            return n
    for ch in t:
        if ch in "12345":
            return int(ch)
    return None


def build_voc_feedback_live_context(
    *,
    language_code: str,
    rating: int,
    user_message: str,
    dialog_history: list,
) -> Dict[str, Any]:
    import user_locale

    return {
        "role": "organizer",
        "flow_step": "voc_feedback",
        "human_status": f"Организатор поставил {rating}/5, ждём открытый отзыв",
        "allowed_next_action": "collect_feedback | none",
        "last_system_action": "voc_rating_received",
        "step_context_human": user_locale.llm_locale_instruction(language_code),
        "dialog_summary": "",
        "last_bot_message": "",
        "brief_json": {},
        "missing_fields_json": [],
        "parser_result_json": {},
        "conflicts_json": [],
        "recent_messages_json": dialog_history or [],
        "user_message": user_message,
        "language_code": language_code,
        "locale_instruction": user_locale.llm_locale_instruction(language_code),
    }
