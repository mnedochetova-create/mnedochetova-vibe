# Family Travel Bot — документация

Карта файлов и связей (актуально для релиза **0.4.0**).

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
| [RECOMMENDATION_BRIEF_SCHEMA.md](RECOMMENDATION_BRIEF_SCHEMA.md) | Снимок `recommendation_ready`, `trip_proposal`, поля event |
| [TRIP_FROM_BRIEF_SPEC.md](TRIP_FROM_BRIEF_SPEC.md) | Поездка из брифа: gates, lifecycle, код |
| [TRIP_EXPERIENCE_ARCHITECTURE.md](TRIP_EXPERIENCE_ARCHITECTURE.md) | **Бриф = контракт; дальше LLM + HTML-карточки**, воронка без быстрой брони |
| [TRIP_TRANSPORT_MODEL.md](TRIP_TRANSPORT_MODEL.md) | Мультимодальный бриф: перелёт, машина, поезд, лодка, пешком, … + readiness |
| [TRIP_ROUTE_COMPOSITION.md](TRIP_ROUTE_COMPOSITION.md) | Сегменты маршрута, комбо EU, impression РФ, авто |
| [TRIP_DATA_SOURCES.md](TRIP_DATA_SOURCES.md) | Открытые API (OSM, Wikidata, OSRM, Open-Meteo…) + Travelpayouts позже |
| [TRIP_PROPOSAL_USER_FLOW.md](TRIP_PROPOSAL_USER_FLOW.md) | UX шаги 13–18 (за `TRIP_PROPOSALS_ENABLED`) |
| [LIVE_RESPONSE.md](LIVE_RESPONSE.md) | Живые формулировки (system + user prompt) |
| [../bot/README.md](../bot/README.md) | Запуск, env, деплой Railway |

## Исследования и логи

- `Рынок и исследования/` — интервью, рынок
- `Рынок и исследования/Логи_взаимодействия_в_Telegram-группу.md` — parse/session логи

## Код (ключевые модули)

- `bot/src/main.py` — сценарии, handlers, карточка брифа, callbacks `trip:*` (флаг)
- `bot/src/trip_from_brief.py` — `recommendation_ready`, readiness, черновики вариантов
- `bot/src/brief_parser.py` — rules + `parse_message_to_brief()`
- `bot/src/parser_mode.py`, `brief_flat_mapper.py`, `brief_pipeline.py` — `PARSER_MODE`, mapper, LLM
- `bot/src/live_response.py` — живые формулировки (отдельно от парсинга)
- `bot/prompts/README.md` — какой промпт когда
