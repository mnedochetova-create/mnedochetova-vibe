# Railway: привязка к проекту (справка)

Этот файл — **справочные идентификаторы** для настройки деплоя и CLI. Сюда **не** кладите секреты (`BOT_TOKEN`, `LLM_API_KEY`, project token).

| Поле | Значение |
|------|----------|
| Project (slug) | `vibrant-respect` |
| Project ID | `fd6fa7a4-26e6-4add-b9b1-bd5e78f318f2` |
| Environment | `production` |
| Environment ID | `e69226cb-398b-470d-bc79-cc6f85d55cb3` |
| Service | `mnedochetova-vibe` |
| Service ID | `e2d1feda-7547-474f-b656-f2a9311228ec` |
| Private domain | `mnedochetova-vibe.railway.internal` |

Ссылка в дашборд: `https://railway.com/project/fd6fa7a4-26e6-4add-b9b1-bd5e78f318f2`

## Что может сделать ассистент в Cursor

Только правки в **репозитории** (`Dockerfile`, `railway.json`, workflow, код). Управлять Variables в облаке и смотреть логи деплоя ассистент **не может** без вашего токена и без того, что вы вставите сюда вывод ошибки.

## Что нужно вам в Railway (Variables)

Минимум для бота: `BOT_TOKEN`. Парсинг: `PARSER_MODE=role_llm`, `LLM_API_KEY` — см. `bot/README.md`, `PARSING_SPEC.md`.

## GitHub Actions → Railway

В секретах репозитория достаточно **`RAILWAY_TOKEN`** (Project Token: Project → Settings → Tokens).  
Имя сервиса для `railway up` по умолчанию — **`mnedochetova-vibe`** (переопределение: variable `RAILWAY_SERVICE_NAME` в GitHub).
