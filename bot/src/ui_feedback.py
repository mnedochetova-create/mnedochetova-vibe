"""Индикатор «бот думает» и короткие success-анимации в чате."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

from aiogram import Bot
from aiogram.types import FSInputFile, Message

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
LOGO_PNG = ASSETS_DIR / "logo.png"
THINKING_GIF = ASSETS_DIR / "thinking.gif"
SUCCESS_GIF = ASSETS_DIR / "success.gif"

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


async def _send_thinking_animation(message: Message) -> Optional[Message]:
    """Inline-анимация логотипа (не документ для скачивания)."""
    if THINKING_GIF.is_file():
        try:
            return await message.answer_animation(
                animation=FSInputFile(str(THINKING_GIF), filename="MyTravelLab.gif"),
                width=512,
                height=512,
            )
        except Exception as err:
            logging.warning("thinking animation failed, fallback to photo: %s", err)

    if LOGO_PNG.is_file():
        try:
            return await message.answer_photo(
                FSInputFile(str(LOGO_PNG), filename="MyTravelLab.png"),
                caption="MyTravel.Lab",
            )
        except Exception as err:
            logging.debug("thinking photo fallback failed: %s", err)

    await cache_bot_logo_file_id(message.bot)
    if _bot_logo_file_id:
        try:
            return await message.answer_photo(_bot_logo_file_id)
        except Exception as err:
            logging.debug("thinking avatar photo failed: %s", err)
    return None


@asynccontextmanager
async def thinking(message: Message) -> AsyncIterator[None]:
    """Пока идёт обработка: typing + крутящийся логотип без лишнего текста."""
    bot = message.bot
    try:
        await bot.send_chat_action(message.chat.id, "typing")
    except Exception as err:
        logging.debug("typing action skipped: %s", err)

    status: Optional[Message] = None
    try:
        status = await _send_thinking_animation(message)
        yield
    finally:
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
            pulse = await message.answer_animation(
                animation=FSInputFile(str(SUCCESS_GIF), filename="MyTravelLab.gif"),
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
