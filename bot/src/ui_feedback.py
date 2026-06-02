"""Индикатор «бот думает» и короткие success-анимации в чате."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from itertools import cycle
from pathlib import Path
from typing import AsyncIterator, Optional

from aiogram import Bot
from aiogram.types import FSInputFile, Message

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
THINKING_GIF = ASSETS_DIR / "thinking.gif"
SUCCESS_GIF = ASSETS_DIR / "success.gif"

_SPIN_FRAMES = ("◴", "◷", "◶", "◵")
_bot_logo_file_id: Optional[str] = None


async def cache_bot_logo_file_id(bot: Bot) -> None:
    global _bot_logo_file_id
    if _bot_logo_file_id:
        return
    try:
        me = await bot.get_me()
        photos = await bot.get_user_profile_photos(me.id, limit=1)
        if photos.total_count and photos.photos:
            _bot_logo_file_id = photos.photos[0][-1].file_id
    except Exception as err:
        logging.debug("bot logo file_id unavailable: %s", err)


async def _spin_status_message(status: Message, *, photo_mode: bool) -> None:
    frames = cycle(_SPIN_FRAMES)
    while True:
        frame = next(frames)
        caption = f"{frame} <b>MyTravel.Lab</b> думает…"
        try:
            if photo_mode:
                await status.edit_caption(caption=caption)
            else:
                await status.edit_text(caption)
        except Exception:
            pass
        await asyncio.sleep(0.55)


@asynccontextmanager
async def thinking(message: Message) -> AsyncIterator[None]:
    """Пока идёт обработка: typing + GIF логотипа или спиннер в подписи к аватарке."""
    bot = message.bot
    try:
        await bot.send_chat_action(message.chat.id, "typing")
    except Exception as err:
        logging.debug("typing action skipped: %s", err)

    status: Optional[Message] = None
    spin_task: Optional[asyncio.Task] = None
    photo_mode = False

    try:
        if THINKING_GIF.is_file():
            status = await message.answer_animation(
                FSInputFile(str(THINKING_GIF)),
                caption="🔄 <b>MyTravel.Lab</b> думает…",
            )
        else:
            await cache_bot_logo_file_id(bot)
            if _bot_logo_file_id:
                status = await message.answer_photo(
                    _bot_logo_file_id,
                    caption="◴ <b>MyTravel.Lab</b> думает…",
                )
                photo_mode = True
            else:
                status = await message.answer("◴ <b>MyTravel.Lab</b> думает…")
        if status is not None:
            spin_task = asyncio.create_task(
                _spin_status_message(status, photo_mode=photo_mode)
            )
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
        if SUCCESS_GIF.is_file():
            pulse = await message.answer_animation(FSInputFile(str(SUCCESS_GIF)))
            await asyncio.sleep(0.9)
            await pulse.delete()
        else:
            pulse = await message.answer("✅")
            await asyncio.sleep(0.35)
            try:
                await pulse.edit_text("✅ ✨")
            except Exception:
                pass
            await asyncio.sleep(0.35)
            await pulse.delete()
    except Exception as err:
        logging.debug("invite success pulse skipped: %s", err)

    await message.answer(final_text, reply_markup=reply_markup)
