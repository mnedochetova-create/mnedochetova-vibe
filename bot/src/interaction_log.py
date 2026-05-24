"""Telegram group logs: parse quality + session summary."""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from aiogram import Bot
from aiogram.types import Message, User

logger = logging.getLogger(__name__)

TELEGRAM_HTML_LIMIT = 4000
_SKIP_BRIEF_KEYS = {"context_raw"}


@dataclass
class _Session:
    started_at: float
    user_id: int
    user_display: str
    username: Optional[str]
    role: str = "—"
    event_number: Optional[int] = None
    actions: List[tuple[str, str, str]] = field(default_factory=list)
    parse_count: int = 0


_sessions: Dict[int, _Session] = {}
_flush_tasks: Dict[int, asyncio.Task] = {}


def logging_enabled() -> bool:
    if os.getenv("LOG_GROUP_ENABLED", "false").strip().lower() not in {"1", "true", "yes"}:
        return False
    return bool(os.getenv("LOG_GROUP_CHAT_ID", "").strip())


def log_group_chat_id() -> Optional[int]:
    raw = os.getenv("LOG_GROUP_CHAT_ID", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid LOG_GROUP_CHAT_ID: %s", raw)
        return None


def session_idle_seconds() -> int:
    raw = os.getenv("LOG_SESSION_IDLE_SEC", "300").strip()
    try:
        return max(60, int(raw))
    except ValueError:
        return 300


def _now_label() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _user_line(user: Optional[User], chat_id: int) -> str:
    if user:
        name = html.escape(user.full_name or "—")
        uname = f" @{user.username}" if user.username else ""
        return f"{chat_id} ({name}){uname}"
    return str(chat_id)


def brief_snapshot(brief: Dict[str, Any]) -> str:
    cleaned = {k: v for k, v in (brief or {}).items() if k not in _SKIP_BRIEF_KEYS}
    text = json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))
    if len(text) > 1500:
        return text[:1500] + "…"
    return text


def _get_session(chat_id: int, user: Optional[User]) -> _Session:
    session = _sessions.get(chat_id)
    if session is None:
        session = _Session(
            started_at=time.time(),
            user_id=chat_id,
            user_display=user.full_name if user else str(chat_id),
            username=user.username if user else None,
        )
        _sessions[chat_id] = session
    elif user:
        session.user_display = user.full_name or session.user_display
        session.username = user.username or session.username
    return session


def _cancel_flush(chat_id: int) -> None:
    task = _flush_tasks.pop(chat_id, None)
    if task and not task.done():
        task.cancel()


def _schedule_idle_flush(bot: Bot, chat_id: int) -> None:
    _cancel_flush(chat_id)

    async def _job() -> None:
        try:
            await asyncio.sleep(session_idle_seconds())
            await flush_session_summary(bot, chat_id, reason="idle")
        except asyncio.CancelledError:
            return

    _flush_tasks[chat_id] = asyncio.create_task(_job())


async def _send_html(bot: Bot, text: str) -> None:
    chat_id = log_group_chat_id()
    if chat_id is None:
        return
    if len(text) <= TELEGRAM_HTML_LIMIT:
        await bot.send_message(chat_id, text, parse_mode="HTML")
        return
    start = 0
    part = 1
    while start < len(text):
        chunk = text[start : start + TELEGRAM_HTML_LIMIT]
        prefix = f"<i>(part {part})</i>\n\n" if part > 1 else ""
        await bot.send_message(chat_id, prefix + chunk, parse_mode="HTML")
        start += TELEGRAM_HTML_LIMIT
        part += 1


async def log_parse_result(
    bot: Bot,
    message: Message,
    *,
    role: str,
    event_number: Optional[int],
    step_label: str,
    user_text: str,
    brief_html: str,
    missing: List[str],
    merged_brief: Dict[str, Any],
    parser_mode: str,
) -> None:
    if not logging_enabled():
        return
    try:
        chat_id = message.chat.id
        user = message.from_user
        session = _get_session(chat_id, user)
        session.role = role
        session.event_number = event_number
        session.parse_count += 1

        missing_block = "— нет пробелов"
        if missing:
            missing_block = "\n".join(f"• {html.escape(item)}" for item in missing)

        user_input = html.escape(user_text or "—")
        snapshot = html.escape(brief_snapshot(merged_brief))
        event_label = f"#{event_number}" if isinstance(event_number, int) else "—"

        report = (
            "🤖 <b>Family Travel Bot · Parser Quality Log</b>\n\n"
            "👤 <b>PARSE REPORT</b>\n"
            f"🆔 User: {_user_line(user, chat_id)}\n"
            f"🎭 Role: {html.escape(role)} · событие {event_label}\n"
            f"🕐 Time: {_now_label()}\n"
            f"⚙️ Step: {html.escape(step_label)} · parser: {html.escape(parser_mode)}\n\n"
            f"📥 <b>USER INPUT:</b>\n{user_input}\n\n"
            f"📤 <b>PARSED BRIEF:</b>\n{brief_html}\n\n"
            f"🚨 <b>MISSING AFTER PARSE:</b>\n{missing_block}\n\n"
            f"📊 <b>MERGED EVENT BRIEF (snapshot):</b>\n<code>{snapshot}</code>"
        )
        await _send_html(bot, report)
        await log_session_action(
            bot,
            message,
            f"{step_label} (parse log sent)",
            role=role,
            event_number=event_number,
            reschedule=False,
        )
    except Exception as err:
        logger.warning("Failed to send parse log to group: %s", err)


async def log_session_action(
    bot: Bot,
    message: Message,
    label_ru: str,
    *,
    role: Optional[str] = None,
    event_number: Optional[int] = None,
    reschedule: bool = True,
) -> None:
    if not logging_enabled():
        return
    try:
        chat_id = message.chat.id
        session = _get_session(chat_id, message.from_user)
        if role:
            session.role = role
        if event_number is not None:
            session.event_number = event_number
        session.actions.append((_now_label(), label_ru, ""))
        if reschedule:
            _schedule_idle_flush(bot, chat_id)
    except Exception as err:
        logger.warning("Failed to record session action: %s", err)


async def flush_session_summary(bot: Bot, chat_id: int, *, reason: str) -> None:
    if not logging_enabled():
        return
    session = _sessions.pop(chat_id, None)
    _cancel_flush(chat_id)
    if not session or not session.actions:
        return
    try:
        duration_min = (time.time() - session.started_at) / 60.0
        uname = f" @{session.username}" if session.username else ""
        event_label = f"#{session.event_number}" if isinstance(session.event_number, int) else "—"
        timeline = "\n".join(
            f"   {ts} → {html.escape(label)}{html.escape(note)}"
            for ts, label, note in session.actions
        )
        report = (
            "🤖 <b>Family Travel Bot · Session Summary</b>\n\n"
            "👤 <b>USER INTERACTION REPORT</b>\n"
            f"🆔 User: {session.user_id} ({html.escape(session.user_display)}){uname}\n"
            f"🎭 Role: {html.escape(session.role)} · событие {event_label}\n"
            f"⏱️ Session Duration: {duration_min:.1f} minutes\n"
            f"🔄 Total Actions: {len(session.actions)}\n"
            f"📝 Parse steps in session: {session.parse_count}\n"
            f"🏁 End reason: {html.escape(reason)}\n\n"
            f"📋 <b>ACTION TIMELINE:</b>\n{timeline}"
        )
        await _send_html(bot, report)
    except Exception as err:
        logger.warning("Failed to send session summary to group: %s", err)


async def flush_session_milestone(bot: Bot, message: Message, reason: str) -> None:
    if not logging_enabled():
        return
    await flush_session_summary(bot, message.chat.id, reason=reason)
