# Family Travel Bot (Python + aiogram)

Текущая версия — прототип Telegram-бота для сбора вводных от организатора и участников, с формированием структурированного черновика брифа.

## Что уже реализовано

- Приветствие и старт сценария через `/start`.
- Создание события организатором.
- Генерация deeplink-ссылки для участников (`/start join_<code>`).
- Ссылка для участников показывается после формирования базового брифа (не на первом шаге создания события).
- Сбор и доуточнение вводных организатора (пока не заполнен минимальный бриф).
- Парсинг ключевых полей: бюджет, состав, даты, перелет, визы/документы, климат/тип отдыха.
- Парсинг длительности поездки (например, 5-7 дней) и логики пересадок (допустимы/без пересадок).
- Парсинг доп. пожеланий участников: песчаный пляж, поездки к достопримечательностям (в т.ч. на машине), рестораны/локальная еда.
- Участник после ввода видит обновленную сводку и подтверждает свой вклад кнопкой.
- После подтверждения участника бот отправляет уведомление организатору.
- `/start`: приветствие с именем, одна inline «Создать поездку» (без нижнего меню на старте).
- Нижнее меню (после создания поездки): `📂 Мои поездки`, `✨ Новая поездка`.
- «Что умеет бот» — в `/help`.
- Burger-команды: `/start`, `/help`, `/cancel` (без дубля «новая поездка» в burger).
- Сценарий приглашения: поделиться текстом, показать ссылку, «Я отправила ссылку».
- Подтверждение финального брифа организатором (в т.ч. без участников) и sharing текста брифа.
- `/help`: контекстная диагностика, восстановление шага, подсказки по вводу и ссылкам.
- Форматированный вывод черновика брифа (HTML-разметка).
- Персона: женский род бота, обращение на «ты» — см. `docs/Family travel bot/BOT_PERSONA.md`.
- Регрессионная проверка качества парсинга на golden-наборе (`bot/tests/fixtures/brief_parsing_golden.jsonl`).

## Что пока не реализовано

- LLM-генерация 2-3 направлений.
- Подтверждение/фиксация short-list.
- Автонапоминания и дедлайны этапов.
- Полноценное БД-хранилище и продвинутая история событий (сейчас файловое хранилище прототипа).

## Быстрый старт

1. Установить зависимости:
   - `cd bot`
   - `python3 -m pip install -r requirements.txt`
2. Создать локальный env:
   - `cp .env.example .env`
   - заполнить `BOT_TOKEN`
   - при необходимости заполнить `LLM_API_KEY` (для следующих этапов)
   - чтобы включить LLM-парсинг брифа (рекомендуется вместе с `LLM_API_KEY`): `USE_LLM_BRIEF_PARSER=true`
   - при необходимости выбрать модель: `LLM_PARSER_MODEL=gpt-4o-mini`
   - чтобы включить "живые" ответы в текущем сценарии: `USE_LLM_LIVE_RESPONSES=true`
   - при необходимости выбрать модель живых ответов: `LLM_LIVE_MODEL=gpt-4o-mini`
   - чтобы включить pipeline parser/merger (organizer+participant+merge): `USE_STRUCTURED_BRIEF_PIPELINE=true`
   - при необходимости выбрать модель structured pipeline: `LLM_BRIEF_STRUCTURED_MODEL=gpt-4o-mini`
3. Запуск:
   - `python3 src/main.py`

## Деплой на Railway (GitHub → Railway)

Справка по вашему проекту Railway (ID, сервис, **без секретов**): `bot/RAILWAY_PROJECT.md`.

Репозиторий собирается из **`Dockerfile` в корне** (контекст — весь репозиторий). В корне также **`railway.json`** — явная сборка через Dockerfile.

### Переменные в Railway (Variables)

- `BOT_TOKEN` (обязательно)
- `USE_LLM_BRIEF_PARSER` (`true/false`)
- `LLM_API_KEY` (если включён LLM-парсер)
- `LLM_PARSER_MODEL` (например, `gpt-4o-mini`)
- `USE_LLM_LIVE_RESPONSES` (`true/false`)
- `LLM_LIVE_MODEL` (например, `gpt-4o-mini`)
- `USE_STRUCTURED_BRIEF_PIPELINE` (`true/false`)
- `LLM_BRIEF_STRUCTURED_MODEL` (например, `gpt-4o-mini`)

Важно:

- `bot/.env` в проде не используется и не должен попадать в образ.
- Файловое хранилище (`bot/data/events.json`) подходит для прототипа; для стабильного прод-режима лучше перейти на БД/volume.

### Автодеплой: выберите один способ (не оба сразу)

**Вариант A — только Railway (проще всего)**  

1. В Railway: **New Project** → **Deploy from GitHub repo** → выберите этот репозиторий и ветку `main`.  
2. Убедитесь, что сервис собирается по **`Dockerfile`** (root directory — корень репозитория, без `bot/` как root, если у вас не отдельный монорепо-сервис).  
3. На каждый push в `main` Railway сам пересоберёт и задеплоит сервис.

**Вариант B — GitHub Actions (тесты, затем `railway up`)**  

В репозитории включён workflow `.github/workflows/deploy-railway.yml`: на push в `main` или ручной запуск (**Actions** → **Deploy bot (Railway)** → **Run workflow**) гоняется `pytest`, затем выкладка через Railway CLI.

1. В Railway: **Project → Settings → Tokens** — создайте **Project token** (не персональный API token с другого экрана).  
2. В GitHub: **Settings → Secrets and variables → Actions** — секрет **`RAILWAY_TOKEN`** (project token).  
   Имя сервиса для деплоя по умолчанию: **`mnedochetova-vibe`** (см. `bot/RAILWAY_PROJECT.md`). При переименовании сервиса задайте variable **`RAILWAY_SERVICE_NAME`** в GitHub.  
3. В Railway для этого сервиса **отключите** авто-деплой из GitHub (если он был включён), иначе на один push уйдут **две** сборки.

Файл `.railwayignore` уменьшает размер архива для `railway up` (документация и прочее не нужны рантайму бота). В корне репозитория **`railway.json`** явно задаёт сборку через **`Dockerfile`**.

### Если деплой упал (без ручного копирования в чат)

В workflow **Deploy bot (Railway)** при ошибке `railway up`:

1. Откройте запуск в **Actions** → вкладка **Summary** — там блок с хвостом лога и ссылкой на run.  
2. Скачайте артефакт **`railway-deploy-log`** (полный вывод).  
3. Опционально: variable **`RAILWAY_DEPLOY_OPEN_ISSUE=true`** — будет создан **Issue** с логом (удобно для трекинга).  
4. Опционально: secret **`RAILWAY_FAILURE_WEBHOOK_URL`** — POST с текстом и ссылкой на run (формат `{"content":"…"}` подходит для Discord; для Slack может понадобиться другой JSON — тогда используйте Issue или Summary).

## Минимальные команды

- `/start` — перезапуск / приветствие.
- `/help` — помощь и восстановление сценария.
- `/cancel` — прервать текущий ввод.
- Новая поездка — кнопка **✨ Новая поездка** (не дублируется в burger).

Документация UX: `docs/Family travel bot/README.md`, аудит сценариев: `SCENARIO_AUDIT.md`.

## Промпт парсинга брифа

- Файл prompt: `bot/prompts/brief_parser_system_prompt.md`
- Спецификация правил парсинга и белых пятен: `docs/Family travel bot/PARSING_SPEC.md`
- Логика:
  - базовый rule-based парсер работает всегда;
  - при `USE_LLM_BRIEF_PARSER=true` бот дополнительно вызывает LLM для структурирования;
  - при ошибке сети/LLM бот автоматически остается на rule-based парсинге.

## Живые ответы (LLM)

- System prompt: `bot/prompts/live_response_system_prompt.md`
- User template: `bot/prompts/live_response_user_prompt_template.md`
- Логика:
  - включается `USE_LLM_LIVE_RESPONSES=true` (принимаются также `TRUE`, `yes`, `1`) + обязателен `LLM_API_KEY`;
  - меняется только **короткий intro** при парсинге вводных (не весь чат и не HTML-бриф);
  - при старте в логах: `Runtime flags: live_responses=True ... llm_api_key=set`;
  - при ошибке сети/LLM — fallback на штатный текст.

## Structured brief pipeline (LLM)

- Organizer parser prompt: `bot/prompts/brief_parser_organizer_system_prompt.md`
- Participant parser prompt: `bot/prompts/brief_parser_participant_system_prompt.md`
- Merger prompt: `bot/prompts/brief_merger_system_prompt.md`
- Логика:
  - включается флагом `USE_STRUCTURED_BRIEF_PIPELINE=true`;
  - organizer/participant parser извлекают данные отдельно;
  - merger объединяет базовый бриф и личные вклады, подсвечивает расхождения;
  - результаты сохраняются как структурированные поля события (`base_brief_structured`, `participant_inputs_structured`, `merged_brief_structured`);
  - при сбое LLM текущий основной сценарий и legacy brief продолжают работать.

## Проверка качества парсинга

- Быстрый отчёт: `python3 bot/tests/test_brief_parsing.py`
- Тест-сюита: `python3 -m pytest -q bot/tests/test_brief_parsing.py`

## Логи в Telegram-группу

Два формата (модуль `bot/src/interaction_log.py`):

1. **Parser Quality Log** — сразу после разбора текста: ввод пользователя, бриф как в чате, пробелы после парсинга, snapshot JSON.
2. **Session Summary** — в конце сессии (пауза 5 мин или этап «приглашение» / подтверждение участника): таймлайн навигации.

Включение:

1. Создайте **приватную** группу, добавьте бота (право писать сообщения).
2. Узнайте `chat_id` группы (отрицательное число).
3. В `.env` / Railway Variables:
   - `LOG_GROUP_ENABLED=true`
   - `LOG_GROUP_CHAT_ID=-100xxxxxxxxxx`
   - `LOG_SESSION_IDLE_SEC=300` (опционально)

Если переменные не заданы — логи в группу не отправляются.

