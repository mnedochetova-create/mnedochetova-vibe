# Changelog

## 0.4.0

### Bot

- Corner-сценарии: defer брифа, скрытие полей, supplement, LLM corner guidance с контекстом поездок.
- Голосовые сообщения: Whisper → единый текстовый путь (`ingest_user_text`).
- Язык ответов LLM по `language_code` Telegram (live + corner).
- VOC после готового брифа: оценка 1–5 и открытый отзыв.
- Merger: только conflicts / open_questions / сводка организатору; кнопка «Принять сводку» (без автозаписи в плоский бриф).
- Парсер участника и rules-by-role; накопление `organizer_structured_history`.
- Индикатор «Думаю…» на долгих путях; правки invite/share (лимит 512 байт).
- Версия в `/start`: `build:` из файла `VERSION` (`app_version.py`).

### Docs

- Синхронизация `BRIEF_PARSING_ROADMAP.md`, `MVP_BOT_SPEC.md`, `PRODUCT_CARD.md`.
- [`docs/VERSIONING.md`](docs/VERSIONING.md) — политика версий и релизов.

## 0.3.0

- Family travel bot: новая архитектура меню (нижнее меню, burger `/start` `/help` `/cancel`, inline по сценарию).
- Family travel bot: сценарий приглашения участников (поделиться текстом, «Я отправила ссылку»).
- Family travel bot: подтверждение финального брифа организатором (в т.ч. без участников) и sharing текста брифа.
- Документация: `MENU_ARCHITECTURE.md`, `BOT_PERSONA.md`, `BRIEF_SHARING_UX_COPY.md`; обновлены `MVP_BOT_SPEC.md`, `USER_FLOWS.md`, `PRODUCT_CARD.md`.
- Tone of voice: обращение на «ты», женский род персоны бота.

## 0.2.0

- Family travel bot: проблемные интервью (TASK_2) — пять респондентов, вопросы и инсайты.
- Family travel bot: откалибрована `PRODUCT_CARD.md` по VoC — приоритеты P0/P1/P2, MVP, монетизация, метрики, волны запуска.
- Синхронизирован манифест версии Release Please.

## 0.1.0

- Initial project structure and documentation.
