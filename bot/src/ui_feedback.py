"""Индикатор «бот думает» и короткие success-анимации в чате."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from aiogram.types import Message

# Меняется при каждом деплое — можно проверить в /help, что бот обновился.
BOT_UI_VERSION = os.getenv("BOT_UI_VERSION", "2026-05-28-invite-org-callback-fix")


async def _typing_loop(bot, chat_id: int, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await bot.send_chat_action(chat_id, "typing")
        except Exception as err:
            logging.debug("typing action skipped: %s", err)
        try:
            await asyncio.wait_for(stop.wait(), timeout=4.0)
        except asyncio.TimeoutError:
            pass


@asynccontextmanager
async def thinking(message: Message) -> AsyncIterator[None]:
    """Пока идёт обработка — только typing в шапке чата, без сообщений и медиа."""
    stop = asyncio.Event()
    task = asyncio.create_task(_typing_loop(message.bot, message.chat.id, stop))
    try:
        yield
    finally:
        stop.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
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
