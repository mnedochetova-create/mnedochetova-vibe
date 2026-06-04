"""Индикатор «бот думает» и короткие success-анимации в чате."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

from aiogram import Bot
from aiogram.types import FSInputFile, Message

# Меняется при каждом деплое — можно проверить в /help, что бот обновился.
BOT_UI_VERSION = os.getenv("BOT_UI_VERSION", "2026-05-28-thinking-logo")

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
LOGO_PNG = ASSETS_DIR / "logo.png"
THINKING_MP4 = ASSETS_DIR / "thinking.mp4"
SUCCESS_MP4 = ASSETS_DIR / "success.mp4"

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


async def _send_thinking_animation(message: Message) -> Optional[Message]:
    """Inline-анимация: MP4 (не .gif-файл) + fallback на logo.png."""
    bot = message.bot
    if THINKING_MP4.is_file():
        try:
            return await bot.send_animation(
                chat_id=message.chat.id,
                animation=FSInputFile(str(THINKING_MP4), filename="MyTravelLab.mp4"),
                width=512,
                height=512,
            )
        except Exception as err:
            logging.warning("thinking mp4 animation failed: %s", err)

    if LOGO_PNG.is_file():
        try:
            return await bot.send_photo(
                chat_id=message.chat.id,
                photo=FSInputFile(str(LOGO_PNG), filename="MyTravelLab.png"),
            )
        except Exception as err:
            logging.debug("thinking photo fallback failed: %s", err)

    await cache_bot_logo_file_id(bot)
    if _bot_logo_file_id:
        try:
            return await bot.send_photo(chat_id=message.chat.id, photo=_bot_logo_file_id)
        except Exception as err:
            logging.debug("thinking avatar photo failed: %s", err)
    return None


@asynccontextmanager
async def thinking(message: Message) -> AsyncIterator[None]:
    """Пока идёт обработка: typing в шапке + крутящийся логотип без подписи."""
    stop = asyncio.Event()
    typing_task = asyncio.create_task(_typing_loop(message.bot, message.chat.id, stop))
    status: Optional[Message] = None
    try:
        status = await _send_thinking_animation(message)
        yield
    finally:
        stop.set()
        typing_task.cancel()
        try:
            await typing_task
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
        "Когда участник перейдёт по ссылке и допишит пожелания — обновлю бриф."
    )
    pulse: Optional[Message] = None
    try:
        if SUCCESS_MP4.is_file():
            pulse = await message.bot.send_animation(
                chat_id=message.chat.id,
                animation=FSInputFile(str(SUCCESS_MP4), filename="MyTravelLab.mp4"),
                width=512,
                height=512,
            )
            await asyncio.sleep(1.0)
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
