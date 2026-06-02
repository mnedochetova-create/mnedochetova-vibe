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
LOGO_PNG = ASSETS_DIR / "logo.png"

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


async def _spin_photo_caption(status: Message) -> None:
    frames = cycle(_SPIN_FRAMES)
    while True:
        frame = next(frames)
        try:
            await status.edit_caption(caption=frame)
        except Exception:
            pass
        await asyncio.sleep(0.45)


async def _send_thinking_logo(message: Message) -> Optional[Message]:
    """Логотип inline (photo) — Telegram не предлагает скачать как документ."""
    bot = message.bot
    if LOGO_PNG.is_file():
        try:
            return await bot.send_photo(
                chat_id=message.chat.id,
                photo=FSInputFile(str(LOGO_PNG)),
            )
        except Exception as err:
            logging.warning("thinking logo photo failed: %s", err)

    await cache_bot_logo_file_id(bot)
    if _bot_logo_file_id:
        try:
            return await bot.send_photo(
                chat_id=message.chat.id,
                photo=_bot_logo_file_id,
            )
        except Exception as err:
            logging.debug("thinking avatar photo failed: %s", err)
    return None


@asynccontextmanager
async def thinking(message: Message) -> AsyncIterator[None]:
    """Пока идёт обработка: typing + логотип (спиннер в подписи к фото)."""
    bot = message.bot
    try:
        await bot.send_chat_action(message.chat.id, "typing")
    except Exception as err:
        logging.debug("typing action skipped: %s", err)

    status: Optional[Message] = None
    spin_task: Optional[asyncio.Task] = None
    try:
        status = await _send_thinking_logo(message)
        if status is not None:
            try:
                await status.edit_caption(caption=_SPIN_FRAMES[0])
            except Exception:
                pass
            spin_task = asyncio.create_task(_spin_photo_caption(status))
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
