# Family Travel Bot — документация

Карта файлов и связей (актуально для релиза **0.3.0**).

## Продукт

| Документ | Назначение |
|----------|------------|
| [PRODUCT_CARD.md](PRODUCT_CARD.md) | Ценность, роли, сценарий MVP |
| [BACKLOG_NEXT_STAGES.md](BACKLOG_NEXT_STAGES.md) | Что после MVP (направления, short-list, …) |
| [USER_FLOWS.md](USER_FLOWS.md) | Пошаговые user flows |
| [SCENARIO_AUDIT.md](SCENARIO_AUDIT.md) | Разрывы сценариев, кнопки, LLM — аудит |

## UX и тексты

| Документ | Назначение |
|----------|------------|
| [MENU_ARCHITECTURE.md](MENU_ARCHITECTURE.md) | Нижнее меню, burger, inline по состояниям |
| [BRIEF_SHARING_UX_COPY.md](BRIEF_SHARING_UX_COPY.md) | Финал брифа и sharing (согласовано) |
| [BOT_PERSONA.md](BOT_PERSONA.md) | Женский род бота, обращение на «ты» |

## Разработка

| Документ | Назначение |
|----------|------------|
| [MVP_BOT_SPEC.md](MVP_BOT_SPEC.md) | Спека бота, state machine, фичефлаги |
| [PARSING_SPEC.md](PARSING_SPEC.md) | **Канон:** парсинг, `PARSER_MODE`, поля, LLM-слои |
| [BRIEF_PARSING_ROADMAP.md](BRIEF_PARSING_ROADMAP.md) | План работ по качеству парсера (чеклисты) |
| [LIVE_RESPONSE.md](LIVE_RESPONSE.md) | Живые формулировки (system + user prompt) |
| [../bot/README.md](../bot/README.md) | Запуск, env, деплой Railway |

## Исследования и логи

- `Рынок и исследования/` — интервью, рынок
- `Рынок и исследования/Логи_взаимодействия_в_Telegram-группу.md` — parse/session логи

## Код (ключевые модули)

- `bot/src/main.py` — сценарии, handlers, карточка брифа
- `bot/src/brief_parser.py` — rules + `parse_message_to_brief()`
- `bot/src/parser_mode.py`, `brief_flat_mapper.py`, `brief_pipeline.py` — `PARSER_MODE`, mapper, LLM
- `bot/src/live_response.py` — живые формулировки (отдельно от парсинга)
- `bot/prompts/README.md` — какой промпт когда
