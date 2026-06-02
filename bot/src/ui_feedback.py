"""Индикатор «бот думает» и короткие success-анимации в чате."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from itertools import cycle
from typing import AsyncIterator, Optional

from aiogram.types import Message

_SPIN_FRAMES = ("◴", "◷", "◶", "◵")


async def _spin_status_text(status: Message) -> None:
    frames = cycle(_SPIN_FRAMES)
    while True:
        frame = next(frames)
        try:
            await status.edit_text(f"{frame} <b>MyTravel.Lab</b>…")
        except Exception:
            pass
        await asyncio.sleep(0.45)


@asynccontextmanager
async def thinking(message: Message) -> AsyncIterator[None]:
    """Пока идёт обработка: typing + короткий текстовый спиннер (без файлов/фото)."""
    bot = message.bot
    try:
        await bot.send_chat_action(message.chat.id, "typing")
    except Exception as err:
        logging.debug("typing action skipped: %s", err)

    status: Optional[Message] = None
    spin_task: Optional[asyncio.Task] = None
    try:
        status = await message.answer(f"{_SPIN_FRAMES[0]} <b>MyTravel.Lab</b>…")
        spin_task = asyncio.create_task(_spin_status_text(status))
        yield
    finally:
        if spin_task is not None:
            spin_task.cancel()
            try:
                await spin_task
            except asyncio.CancelledError:
                pass
        if status is not None:
            try:
                await status.delete()
            except Exception:
                pass


async def play_invite_sent_success(
    message: Message,
    *,
    reply_markup=None,
) -> None:
    """Короткая анимация после подтверждения «приглашение отправлено»."""
    final_text = (
        "✅ <b>Готово!</b> Приглашение отправлено.\n"
        "Когда участник перейдёт по ссылке и допишет пожелания — обновлю бриф."
    )
    pulse: Optional[Message] = None
    try:
        pulse = await message.answer("✅")
        await asyncio.sleep(0.3)
        try:
            await pulse.edit_text("✅ ✨")
        except Exception:
            pass
        await asyncio.sleep(0.35)
        await pulse.delete()
    except Exception as err:
        logging.debug("invite success pulse skipped: %s", err)

    await message.answer(final_text, reply_markup=reply_markup)
