"""Индикатор «бот думает»: typing в шапке + короткий статус в чате (без GIF/файлов)."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from aiogram.enums import ChatAction
from aiogram.types import LinkPreviewOptions, Message

# Меняется при каждом деплое — можно проверить в /help, что бот обновился.
BOT_UI_VERSION = os.getenv("BOT_UI_VERSION", "2026-05-28-thinking-all")

# Текстовый статус как у Mira («Думаю»), без медиа. Отключить: THINKING_STATUS=0
THINKING_STATUS_ENABLED = os.getenv("THINKING_STATUS", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
THINKING_STATUS_HTML = os.getenv(
    "THINKING_STATUS_HTML",
    "💭 <b>Думаю…</b>",
)

_LINK_PREVIEW_OFF = LinkPreviewOptions(is_disabled=True)


async def _typing_loop(bot, chat_id: int, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await bot.send_chat_action(chat_id, ChatAction.TYPING)
        except Exception as err:
            logging.debug("typing action skipped: %s", err)
        try:
            await asyncio.wait_for(stop.wait(), timeout=4.0)
        except asyncio.TimeoutError:
            pass


async def _send_thinking_status(message: Message) -> Optional[Message]:
    if not THINKING_STATUS_ENABLED:
        return None
    try:
        return await message.answer(
            THINKING_STATUS_HTML,
            reply_to_message_id=message.message_id,
            link_preview_options=_LINK_PREVIEW_OFF,
        )
    except Exception as err:
        logging.debug("thinking status message skipped: %s", err)
        return None


@asynccontextmanager
async def thinking(message: Message) -> AsyncIterator[None]:
    """Пока идёт обработка: typing в шапке + короткое «Думаю…» (удаляется перед ответом)."""
    stop = asyncio.Event()
    try:
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    except Exception as err:
        logging.debug("typing action skipped: %s", err)
    typing_task = asyncio.create_task(_typing_loop(message.bot, message.chat.id, stop))
    status_msg: Optional[Message] = None
    try:
        status_msg = await _send_thinking_status(message)
        yield
    finally:
        stop.set()
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass
        if status_msg is not None:
            try:
                await status_msg.delete()
            except Exception:
                pass


async def play_invite_sent_success(
    message: Message,
    *,
    reply_markup=None,
) -> None:
    """Подтверждение после «приглашение отправлено»."""
    await message.answer(
        "✅ <b>Готово!</b> Приглашение отправлено.\n"
        "Когда участник перейдёт по ссылке и допишет пожелания — обновлю бриф.",
        reply_markup=reply_markup,
    )
