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

**Не задавайте** переменную `BOT_UI_VERSION` в Railway, если не нужно явно — иначе она **перебивает** [`VERSION`](../VERSION) из образа, и в `/start` останется старый `build:` при новом коде. См. [`docs/VERSIONING.md`](../docs/VERSIONING.md).

## Persistent Volume для `events.json` (обязательно на проде)

Бот хранит поездки в файле **`/app/bot/data/events.json`** (в коде: `bot/src/storage.py`, в контейнере `WORKDIR /app`).

Без volume файловая система контейнера **эфемерная**: после **redeploy** или смены образа файл часто **пустой** — пропадают поездки, брифы, `invite_link`. В репозитории `events.json` в `.gitignore` и в `.dockerignore`, в образ он **не попадает**.

### Где создать Volume (не в Settings)

В **Project Settings** и в **Service Settings** (`Source`, `Networking`, `Scale`, `Build`…) пункта **Volumes в боковом меню часто нет** — так задумано в актуальном UI Railway.

Том создаётся **с канвы проекта** или через **Command Palette**:

**Способ A — Command Palette (рекомендуется)**

1. Откройте [канву проекта](https://railway.com/project/fd6fa7a4-26e6-4add-b9b1-bd5e78f318f2).
2. **`Cmd+K`** (Mac) или **`Ctrl+K`** (Windows/Linux).
3. Введите **Volume** → **Create Volume** (или аналог).
4. Выберите сервис **`mnedochetova-vibe`**.
5. **Mount path:** `/app/bot/data` → сохранить → **Redeploy** сервиса.

**Способ B — контекстное меню на канве**

1. На канве **правый клик** по пустому месту или по сервису.
2. Пункт вроде **Add Volume** / **Create Volume** (если доступен).
3. Привязать к `mnedochetova-vibe`, mount `/app/bot/data`.

После создания том может отображаться **отдельной карточкой** на канве (куб/диск), связанной с сервисом. Настройки тома — **клик по этой карточке volume**, не вкладка в Settings сервиса.

Документация: [Using Volumes](https://docs.railway.com/volumes).

### Если Volume не предлагается (частые причины)

| Причина | Что сделать |
|--------|-------------|
| **Replicas > 1** | **Settings → Scale** → **1 replica**. Volumes несовместимы с несколькими репликами одного сервиса. |
| **Runtime Metal** | В настройках сервиса (Deploy / runtime) переключить с **Metal** на обычный runtime, если есть выбор — на Metal volumes пока недоступны. |
| У сервиса уже есть volume | Один сервис — один volume; второй не добавится. |
| Поиск в Settings | Использовать **Cmd+K → Volume**, не меню Settings. |

### Настройка mount path

- **Абсолютный путь:** `/app/bot/data` (не `/app/data`).
- Совпадает с `Dockerfile`: `WORKDIR /app`, `RUN mkdir -p /app/bot/data`.
- Размер для MVP: **1 GB**.
- После привязки — **Redeploy** `mnedochetova-vibe`.

### Как проверить, что volume подключён

**На канве:** отдельный блок volume, связанный с `mnedochetova-vibe`, mount `/app/bot/data`.

**В Variables** (runtime, Railway подставляет сам):

| Переменная | Если volume есть |
|------------|------------------|
| `RAILWAY_VOLUME_NAME` | не пусто |
| `RAILWAY_VOLUME_MOUNT_PATH` | `/app/bot/data` (или ваш mount path) |

**Практический тест:**

1. Создайте поездку в боте, запомните `#N`.
2. **Redeploy** последнего деплоя.
3. «📂 Текущая поездка» / «📂 Мои поездки» — поездка `#N` на месте.

Если после redeploy поездки **исчезли** — volume не смонтирован или неверный путь.

### Если бот не пишет в volume

Volume монтируется от имени **root**. Образ `python:3.11-slim` по умолчанию под root — обычно достаточно. При `Permission denied` в логах добавьте Variable: `RAILWAY_RUN_UID=0` (см. Railway docs).

### Что volume не решает

- **FSM** (`MemoryStorage` в aiogram) после рестарта процесса сбрасывается; поездки восстанавливаются из `events.json` + `chat_id`, шаг диалога может сброситься.
- **Несколько реплик** одного сервиса — один файл на диске не синхронизируется между инстансами; держите **один** инстанс или переходите на БД.
- Volume доступен только **в runtime**, не на этапе build.

В `railway.json` volume **не описан** — только настройка в UI (или CLI). Зафиксируйте здесь факт подключения, когда сделаете.

## Если в Telegram «старый» бриф после push

1. В **Помощь** (`/help`) внизу: `build: …` — иначе крутится старый контейнер (в карточке брифа версия не показывается).
2. Railway → **Deployments**: последний деплой с коммитом `6c89d87` или новее.
3. Если включён **Deploy from GitHub** и **GitHub Actions** (`deploy-railway.yml`) — оставьте **один** канал (см. `bot/README.md`), иначе может победить не та сборка.
4. Старое сообщение в чате **не обновляется** — отправьте вводные заново или «Текущая поездка».

## GitHub Actions → Railway

В секретах репозитория достаточно **`RAILWAY_TOKEN`** (Project Token: Project → Settings → Tokens).  
Имя сервиса для `railway up` по умолчанию — **`mnedochetova-vibe`** (переопределение: variable `RAILWAY_SERVICE_NAME` в GitHub).
