import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    BotCommand,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from dotenv import load_dotenv


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Я организатор поездки")],
            [KeyboardButton(text="Я участник поездки"), KeyboardButton(text="Что умеет бот")],
        ],
        resize_keyboard=True,
    )


async def start_handler(message: Message) -> None:
    logging.info("Received /start from chat_id=%s", message.chat.id)
    await message.answer(
        "Привет! Я Family Travel Bot.\n\n"
        "Что я умею в MVP:\n"
        "- собрать вводные поездки от организатора;\n"
        "- дозапросить участников в личке;\n"
        "- сформировать 2-3 направления и short-list.\n\n"
        "Кто вы в этой поездке?",
        reply_markup=main_menu_keyboard(),
    )


async def help_handler(message: Message) -> None:
    logging.info("Received /help from chat_id=%s", message.chat.id)
    await message.answer(
        "Команды:\n"
        "/start — начало работы\n"
        "/help — справка\n"
        "/organizer — режим организатора\n"
        "/participant — режим участника\n\n"
        "В MVP бот ведет к short-list из 2-3 направлений."
    )


async def organizer_handler(message: Message) -> None:
    logging.info("Organizer flow selected by chat_id=%s", message.chat.id)
    await message.answer(
        "Отлично, начинаем как организатор.\n\n"
        "Шаг 1: опишите ситуацию и пожелания по поездке своими словами.\n"
        "Например: \"2 взрослых и ребенок 6 лет, хотим море в июле, бюджет до 250к, без долгого перелета\"."
    )


async def participant_handler(message: Message) -> None:
    logging.info("Participant flow selected by chat_id=%s", message.chat.id)
    await message.answer(
        "Отлично, режим участника включен.\n"
        "Ожидайте приглашение в активную сессию от организатора.\n"
        "После приглашения я задам короткие вопросы по вашим ограничениям."
    )


async def capabilities_handler(message: Message) -> None:
    logging.info("Capabilities requested by chat_id=%s", message.chat.id)
    await message.answer(
        "Сейчас умею:\n"
        "1) Собирать brief от организатора.\n"
        "2) Уточнять ограничения участников.\n"
        "3) Формировать 2-3 направления с объяснением.\n"
        "4) Фиксировать short-list (без голосования в MVP)."
    )


async def text_fallback_handler(message: Message) -> None:
    logging.info("Received text from chat_id=%s: %s", message.chat.id, message.text)
    await message.answer(
        "Я пока не понял запрос.\n"
        "Выберите действие в меню или отправьте /help.",
        reply_markup=main_menu_keyboard(),
    )


async def main() -> None:
    load_dotenv()
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Missing BOT_TOKEN in environment")

    bot = Bot(token=token)
    dp = Dispatcher()

    dp.message.register(start_handler, CommandStart())
    dp.message.register(help_handler, Command("help"))
    dp.message.register(organizer_handler, Command("organizer"))
    dp.message.register(participant_handler, Command("participant"))
    dp.message.register(organizer_handler, F.text == "Я организатор поездки")
    dp.message.register(participant_handler, F.text == "Я участник поездки")
    dp.message.register(capabilities_handler, F.text == "Что умеет бот")
    dp.message.register(text_fallback_handler, F.text)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Запуск бота"),
            BotCommand(command="help", description="Что умеет бот"),
            BotCommand(command="organizer", description="Я организатор поездки"),
            BotCommand(command="participant", description="Я участник поездки"),
        ]
    )

    # Polling mode should not compete with webhooks.
    # If Telegram API is temporarily slow, do not block startup forever.
    try:
        await asyncio.wait_for(
            bot.delete_webhook(drop_pending_updates=False),
            timeout=6,
        )
    except Exception as err:
        logging.warning("delete_webhook skipped due to network issue: %s", err)

    logging.info("Starting bot polling...")
    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            await dp.start_polling(bot)
            return
        except Exception as err:
            if attempt >= max_attempts:
                raise
            wait_seconds = attempt * 2
            logging.warning(
                "Polling start failed (attempt %s/%s): %s. Retrying in %ss...",
                attempt,
                max_attempts,
                err,
                wait_seconds,
            )
            await asyncio.sleep(wait_seconds)


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
