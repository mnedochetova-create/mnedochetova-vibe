# Bot Development Workspace

Эта папка предназначена для разработки Telegram-бота.

## Рекомендуемая структура

- `src/` — исходный код
- `tests/` — тесты
- `.env.example` — шаблон переменных окружения
- `README.md` — локальные инструкции по запуску

## Чеклист запуска разработки

- [x] Выбран стек: Python + aiogram
- [x] Создан минимальный проект и зависимости
- [x] Подключение токена через переменные окружения
- [ ] Для цен Aviasales: скопировать `.env.example` в `.env`, задать `TRAVELPAYOUTS_TOKEN`; поля ответов API — `docs/Family travel bot/TRAVELPAYOUTS_AVIASALES_FIELDS.md`
- [x] Добавлено базовое логирование и обработка команд

## Быстрый старт (текущий каркас)

1. Установить зависимости:
   - `cd bot`
   - `python3 -m pip install -r requirements.txt`
2. Создать локальный env:
   - `cp .env.example .env`
   - заполнить `BOT_TOKEN`
3. Запуск:
   - `python3 src/main.py`

## Минимальные требования к боту

- Команда `/start`
- Команда `/help`
- Обработка неизвестных сообщений
- Базовые логи

