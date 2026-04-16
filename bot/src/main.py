import asyncio
import logging
import os
import secrets
import time
from typing import Optional, Dict, Any

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    BotCommand,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from dotenv import load_dotenv


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


class FlowState(StatesGroup):
    organizer_dump = State()
    organizer_clarify = State()

BOT_USERNAME: Optional[str] = None

# In-memory storage for manual testing (will reset on restart).
# event_code -> event dict
EVENTS: Dict[str, Dict[str, Any]] = {}


def new_event_code() -> str:
    # Short human-friendly code
    return secrets.token_hex(3)


def now_ts() -> int:
    return int(time.time())


def extract_brief_from_text(text: str) -> Dict[str, Any]:
    t = (text or "").lower()
    brief: Dict[str, Any] = {}

    # Budget: "до 250к", "250 000", "250тыс"
    import re

    m = re.search(r"(?:до|бюджет(?:ом)?\s*(?:до)?)\s*(\d[\d\s]{1,8})\s*(к|тыс|тысяч|000)?", t)
    if m:
        num = int(re.sub(r"\s+", "", m.group(1)))
        if m.group(2) in {"к", "тыс", "тысяч"}:
            num *= 1000
        brief["budget_rub_max"] = num

    # Adults / kids: "2 взрослых", "1 ребенок 6", "ребёнок 6 лет"
    m = re.search(r"(\d+)\s*(?:взросл", t)
    if m:
        brief["adults"] = int(m.group(1))
    m = re.search(r"(\d+)\s*(?:дет|реб", t)
    if m:
        brief["kids_count"] = int(m.group(1))
    m = re.search(r"(?:реб[её]нок|дет[а-я]*)\s*(\d{1,2})\s*(?:лет|года?)", t)
    if m:
        brief["kid_age"] = int(m.group(1))

    # Dates/months: very lightweight capture
    months = [
        "январ", "феврал", "март", "апрел", "май", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"
    ]
    for mon in months:
        if mon in t:
            brief.setdefault("months", []).append(mon)

    # Flight duration: "до 5 часов"
    m = re.search(r"(?:до|не\s*больше)\s*(\d{1,2})\s*(?:ч|час)", t)
    if m:
        brief["flight_hours_max"] = int(m.group(1))

    # Visa constraint
    if "без виз" in t:
        brief["visa_required"] = False
    elif "виза" in t:
        brief["visa_required"] = True

    # Climate/type
    if "море" in t or "пляж" in t:
        brief["climate"] = "море/пляж"
    if "горы" in t:
        brief["climate"] = "горы"
    if "экскурс" in t or "музе" in t:
        brief["trip_type"] = "экскурсии/город"
    if "all inclusive" in t or "оллинклюзив" in t or "всё включено" in t:
        brief["trip_type"] = "всё включено"

    return brief


def merge_brief(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base or {})
    for k, v in (incoming or {}).items():
        if v is None:
            continue
        if k == "months":
            out.setdefault("months", [])
            for item in v:
                if item not in out["months"]:
                    out["months"].append(item)
            continue
        out[k] = v
    return out


def missing_brief_fields(brief: Dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not brief.get("months"):
        missing.append("Окна дат (месяц/период) или гибкость")
    if not brief.get("budget_rub_max"):
        missing.append("Бюджет (хотя бы «до … ₽»)")
    if not brief.get("adults") and not brief.get("kids_count"):
        missing.append("Кто едет (взрослые/дети)")
    if not brief.get("flight_hours_max"):
        missing.append("Ограничение по перелёту (например, «до 5 часов»)")
    if "visa_required" not in brief:
        missing.append("Визы/документы (например, «без визы»)")
    if not brief.get("climate") and not brief.get("trip_type"):
        missing.append("Климат или тип отдыха (море/горы/город/санаторий и т.п.)")
    return missing


def welcome_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать событие", callback_data="event:create")],
        ]
    )


def organizer_next_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать событие", callback_data="event:create")],
        ]
    )


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    # Простое меню (не inline), чтобы всегда было под рукой.
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Создать событие")],
            [KeyboardButton(text="Что умеет бот"), KeyboardButton(text="/help")],
        ],
        resize_keyboard=True,
    )


async def start_handler(message: Message, state: FSMContext) -> None:
    logging.info("Received /start from chat_id=%s", message.chat.id)
    await state.update_data(role="organizer")
    await message.answer(
        "Привет! Я помогу вашей группе быстро договориться о направлении поездки — без бесконечных уточнений в чате.\n\n"
        "Что я умею:\n"
        "— создать событие поездки;\n"
        "— превратить ваши вводные в понятный бриф;\n"
        "— подключить участников по ссылке и собрать их предпочтения;\n"
        "— собрать общую сводку и предложить 2–3 направления с объяснением.\n\n"
        "Вы — организатор (организатором считается тот, кто создаёт событие).\n"
        "Нажмите «Создать событие».",
        reply_markup=main_menu_keyboard(),
    )


async def help_handler(message: Message) -> None:
    logging.info("Received /help from chat_id=%s", message.chat.id)
    await message.answer(
        "Команды:\n"
        "/start — начало работы\n"
        "/help — справка\n"
        "/new — создать событие\n\n"
        "Бот помогает собрать бриф и получить 2–3 направления с объяснением."
    )


async def capabilities_handler(message: Message) -> None:
    logging.info("Capabilities requested by chat_id=%s", message.chat.id)
    await message.answer(
        "Сейчас умею:\n"
        "1) Собирать вводные и бриф от организатора.\n"
        "2) Дозапрашивать пробелы.\n"
        "3) Формировать 2-3 направления с объяснением.\n"
        "4) Фиксировать короткий список (без голосования на этом этапе)."
    )


async def new_event_handler(message: Message, state: FSMContext) -> None:
    logging.info("New event requested by chat_id=%s", message.chat.id)
    await state.update_data(organizer_chat_id=message.chat.id)
    await state.set_state(FlowState.organizer_dump)
    event_code = new_event_code()
    EVENTS[event_code] = {
        "code": event_code,
        "created_at": now_ts(),
        "organizer_chat_id": message.chat.id,
        "organizer_dump": None,
        "participants": set(),
    }
    await state.update_data(event_code=event_code)

    if BOT_USERNAME:
        invite_link = f"https://t.me/{BOT_USERNAME}?start=join_{event_code}"
    else:
        invite_link = None

    invite_text = (
        f"\n\nСсылка для участников:\n{invite_link}"
        if invite_link
        else "\n\nСсылка для участников появится после перезапуска бота."
    )

    await message.answer(
        "Ок, событие создано.\n"
        "Сейчас вы — организатор этого события.\n\n"
        "Шаг 1: одним сообщением опишите вводные по поездке."
        f"{invite_text}\n\n"
        "Пример:\n"
        "«2 взрослых + ребёнок 6 лет, июль/август, море, бюджет до 250к, перелёт до 5 часов, без визы»",
        reply_markup=main_menu_keyboard(),
    )

async def event_create_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    logging.info("Event create clicked chat_id=%s", callback.message.chat.id)
    await callback.answer()
    await new_event_handler(callback.message, state)


async def role_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    data = callback.data or ""
    logging.info("Role selected: %s chat_id=%s", data, callback.message.chat.id)
    await callback.answer()

    if data == "role:organizer":
        await state.update_data(role="organizer")
        await callback.message.answer(
            "Отлично. Раз вы создаёте событие — вы организатор.\n\n"
            "Нажмите кнопку ниже, чтобы создать событие и начать сбор вводных.",
            reply_markup=organizer_next_keyboard(),
        )
        return

    await state.update_data(role="participant")
    await callback.message.answer(
        "Вы — участник. Чтобы войти в событие, откройте ссылку от организатора.\n\n"
        "Когда вы заходите по ссылке, я подключаю вас к событию и задам короткие вопросы по вашим предпочтениям.",
        reply_markup=main_menu_keyboard(),
    )


async def start_payload_handler(message: Message, command: CommandObject, state: FSMContext) -> None:
    payload = (command.args or "").strip()
    if not payload.startswith("join_"):
        await start_handler(message, state)
        return

    event_code = payload.removeprefix("join_")
    event = EVENTS.get(event_code)
    if not event:
        await message.answer(
            "Похоже, ссылка устарела или событие уже не активно.\n"
            "Попросите организатора прислать новую ссылку."
        )
        return

    event["participants"].add(message.chat.id)
    await message.answer(
        "Вы подключены к событию.\n"
        "Я вижу вводные организатора и скоро начну собирать ваши предпочтения.\n\n"
        "Пока просто ответьте одним сообщением:\n"
        "— что для вас важно в поездке (бюджет/даты/перелёт/дети/климат/тип отдыха)?"
    )


async def organizer_dump_handler(message: Message, state: FSMContext) -> None:
    try:
        logging.info("Organizer dump received chat_id=%s", message.chat.id)
        data = await state.get_data()
        event_code = data.get("event_code")
        text = message.text or ""

        existing_brief = {}
        if event_code and event_code in EVENTS:
            existing_brief = EVENTS[event_code].get("brief") or {}

        incoming = extract_brief_from_text(text)
        brief = merge_brief(existing_brief, incoming)

        if event_code and event_code in EVENTS:
            EVENTS[event_code]["organizer_dump"] = text
            EVENTS[event_code]["brief"] = brief

        await state.update_data(organizer_dump=text, brief=brief)
        await state.set_state(FlowState.organizer_clarify)

        missing = missing_brief_fields(brief)

        # Build a compact summary of what we recognized
        summary_parts: list[str] = []
        if brief.get("adults") or brief.get("kids_count"):
            a = brief.get("adults")
            k = brief.get("kids_count")
            if a and k:
                summary_parts.append(f"Кто едет: {a} взр., {k} дет.")
            elif a:
                summary_parts.append(f"Кто едет: {a} взр.")
            elif k:
                summary_parts.append(f"Кто едет: {k} дет.")
        if brief.get("months"):
            summary_parts.append("Даты: " + ", ".join(brief["months"]))
        if brief.get("budget_rub_max"):
            summary_parts.append(f"Бюджет: до {brief['budget_rub_max']:,} ₽".replace(",", " "))
        if brief.get("flight_hours_max"):
            summary_parts.append(f"Перелёт: до {brief['flight_hours_max']} ч.")
        if "visa_required" in brief:
            summary_parts.append("Визы: " + ("нужна" if brief["visa_required"] else "без визы"))
        if brief.get("climate"):
            summary_parts.append(f"Климат: {brief['climate']}")
        if brief.get("trip_type"):
            summary_parts.append(f"Тип отдыха: {brief['trip_type']}")

        summary_text = "\n".join(f"- {p}" for p in summary_parts) if summary_parts else "- (пока не удалось распознать детали, ок — уточним вручную)"

        if not missing:
            await message.answer(
                "Принято, спасибо! Я распознал вводные:\n"
                f"{summary_text}\n\n"
                "Данных достаточно, двигаемся дальше.",
                reply_markup=main_menu_keyboard(),
            )
            return

        missing_text = "\n".join(f"- {m}" for m in missing)
        await message.answer(
            "Принято, спасибо! Я распознал вводные:\n"
            f"{summary_text}\n\n"
            "Чтобы не переспрашивать лишнее, уточните, пожалуйста, только это (можно одним сообщением):\n"
            f"{missing_text}",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as err:
        logging.exception("organizer_dump_handler failed: %s", err)
        await message.answer(
            "Я столкнулся с ошибкой и не смог обработать сообщение.\n"
            "Попробуйте отправить вводные ещё раз одним сообщением.",
            reply_markup=main_menu_keyboard(),
        )


async def organizer_clarify_handler(message: Message, state: FSMContext) -> None:
    try:
        # Any follow-up message in clarify state merges into brief and asks only remaining missing fields
        data = await state.get_data()
        event_code = data.get("event_code")
        brief = data.get("brief") or {}

        incoming = extract_brief_from_text(message.text or "")
        brief = merge_brief(brief, incoming)

        if event_code and event_code in EVENTS:
            EVENTS[event_code]["brief"] = brief

        await state.update_data(brief=brief)

        missing = missing_brief_fields(brief)
        if not missing:
            await message.answer("Отлично, спасибо! Данных достаточно — двигаемся дальше.", reply_markup=main_menu_keyboard())
            return

        missing_text = "\n".join(f"- {m}" for m in missing)
        await message.answer(
            "Спасибо! Осталось уточнить:\n"
            f"{missing_text}\n\n"
            "Можно одним сообщением.",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as err:
        logging.exception("organizer_clarify_handler failed: %s", err)
        await message.answer(
            "Похоже, я не смог обработать уточнение.\n"
            "Попробуйте написать проще (например: «до 250к, июль, 2 взрослых, без визы»).",
            reply_markup=main_menu_keyboard(),
        )


async def text_fallback_handler(message: Message) -> None:
    logging.info("Received text from chat_id=%s: %s", message.chat.id, message.text)
    if message.text == "Что умеет бот":
        await capabilities_handler(message)
        return
    await message.answer("Выберите действие в меню или отправьте /help.", reply_markup=main_menu_keyboard())


async def main() -> None:
    load_dotenv()
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Missing BOT_TOKEN in environment")

    bot = Bot(token=token)
    dp = Dispatcher(storage=MemoryStorage())

    # Handle both plain /start and /start <payload> deep-links.
    dp.message.register(start_payload_handler, CommandStart())
    dp.message.register(help_handler, Command("help"))
    dp.message.register(new_event_handler, Command("new"))
    dp.message.register(new_event_handler, F.text == "Создать событие")
    dp.message.register(capabilities_handler, F.text == "Что умеет бот")
    dp.message.register(organizer_dump_handler, FlowState.organizer_dump, F.text)
    dp.message.register(organizer_clarify_handler, FlowState.organizer_clarify, F.text)
    dp.message.register(text_fallback_handler, F.text)

    dp.callback_query.register(role_callback_handler, F.data.startswith("role:"))
    dp.callback_query.register(event_create_callback_handler, F.data == "event:create")

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Запуск бота"),
            BotCommand(command="help", description="Что умеет бот"),
            BotCommand(command="new", description="Создать событие"),
        ]
    )

    global BOT_USERNAME
    BOT_USERNAME = (await bot.get_me()).username

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
