# Аудит сценариев и документации (0.3.0)

Дата: 2026-05-28.

## 1. Карта документов — связи

| Документ | Ссылается на | Статус |
|----------|--------------|--------|
| PRODUCT_CARD | MENU_ARCHITECTURE, BRIEF_SHARING, BOT_PERSONA | OK |
| MVP_BOT_SPEC | MENU, PERSONA, PARSING, BRIEF_SHARING | OK (state machine обновлён ниже) |
| USER_FLOWS | — | Были устаревшие «Мои события» / «Помощь» в меню — исправлено |
| MENU_ARCHITECTURE | USER_FLOWS, MVP, BOT_PERSONA | OK |
| PARSING_SPEC | BRIEF_PARSING_ROADMAP | Канон `PARSER_MODE`, §6 без дубля |
| BRIEF_PARSING_ROADMAP | PARSING_SPEC | Только чеклисты, без копии архитектуры |
| bot/README | docs + env | Убран устаревший `/new` |
| README (этот индекс) | все ключевые файлы | NEW |

## 2. Где живой LLM реально работает

**Важно:** `USE_LLM_LIVE_RESPONSES` не переписывает весь чат. Меняется только **короткая вводная строка** (1–2 предложения) в четырёх местах:

| Шаг | Когда |
|-----|--------|
| Организатор — первый ввод | После парсинга: «бриф собран» или блок уточнений |
| Организатор — уточнение | То же при `organizer_clarify` |
| Участник — пожелания | Intro перед карточкой брифа |

**Не через live LLM:** `/start`, меню, приглашение, sharing, подтверждение брифа, help, карточка брифа (HTML) — там **фиксированные** тексты.

### Чеклист Railway Variables

```
PARSER_MODE=role_llm
LLM_API_KEY=sk-...
LLM_BRIEF_STRUCTURED_MODEL=gpt-4o-mini   # опционально
USE_LLM_LIVE_RESPONSES=true                # опционально
LLM_LIVE_MODEL=gpt-4o-mini                 # опционально
```

После деплоя в логах Railway при старте должна быть строка:

`Runtime flags: live_responses=True ... llm_api_key=set`

При успешном ответе LLM: `Live response from LLM (model=...)`.

Если `llm_api_key=MISSING` или `live_responses=False` — будут только fallback-тексты (визуально похожи на штатные).

## 3. Инвентарь inline-кнопок (код)

### Навигация / старт
- `event:create`, `event:how`
- `help:continue`, `help:parser`, `help:clarify`, `help:link`, `help:report`
- `help:myevents` — **есть в коде, убрана из help-keyboard** (мертвый callback, если не вызвать иначе)

### Приглашение
- `event:invite_share`, `event:invite_link`, `event:invite_sent`, `event:invite_done`
- `event:show_brief`

### Финал брифа (организатор)
- `brief:confirm_prep` — с экрана приглашения
- `brief:confirm`, `brief:edit` — экран A
- `brief:share`, `brief:share_text`, `brief:share_done` — экраны B/C

### Участник
- `participant:confirm`, `participant:edit`

### Список поездок
- `event:open:{code}`

### Нижнее меню (не inline)
`📂 Мои поездки` · `✨ Новая поездка` (после создания поездки; «Что умеет бот» — в `/help`)

### Burger
`/start` · `/help` · `/cancel`

## 4. Разрывы и риски сценария

| # | Разрыв | Серьёзность | Рекомендация |
|---|--------|-------------|--------------|
| 1 | **Две кнопки «✅ Подтвердить бриф»** — у участника (`participant:confirm`) и у организатора (`brief:confirm`) | Средняя | Переименовать участнику: «✅ Всё верно» (UX-апрув) |
| 2 | **До 4 inline-кнопок** на экране приглашения и финала (правило «макс. 3» в MENU_ARCHITECTURE) | Низкая | Зафиксировать исключение для value-экранов или схлопнуть ряды |
| 3 | **После `brief:edit`** статус `organizer_brief_confirmed_at` не сбрасывается | Средняя | При дополнении сбрасывать подтверждение или блокировать edit |
| 4 | Расхождения merger — блок в карточке брифа; отдельная inline `brief:conflicts` не сделана | Низкая | Backlog при необходимости |
| 5 | **Карточки «Мои поездки»** — по `#номер`, не по смыслу поездки | Низкая | Backlog: заголовок из брифа |
| 6 | **`/cancel`** сбрасывает FSM, но не объясняет, на каком шаге был пользователь | Низкая | Доп. строка в ответе cancel |
| 7 | **MVP state machine** в спеке не включала `brief_confirmed` / sharing | Док | Обновлено в MVP_BOT_SPEC §3 |
| 8 | **Живой LLM** легко не заметить — меняется только intro, не блок брифа | Ожидания | Объяснить тестировщикам (§2) |

## 5. Рекомендуемый порядок теста

1. Проверить логи Railway (`Runtime flags`, `Live response from LLM`).
2. Полный бриф организатором → заметить **отличие intro** от fallback (или сравнить с `USE_LLM_LIVE_RESPONSES=false`).
3. Пройти кнопки приглашения → участник → подтверждение → организатор «Подтвердить бриф» → sharing.
4. Ветка без участников: «Подтвердить бриф» сразу после приглашения.

См. также примеры сообщений в чате с ассистентом (TEST_SCENARIOS — при добавлении в репо).
