# Parsing Spec — Family Travel Bot

Цель: сделать парсинг пользовательских сообщений предсказуемым, без додумывания, с прозрачным списком уточнений.

**План улучшений (wow, подбор поездок, фазы работ):** см. [`BRIEF_PARSING_ROADMAP.md`](BRIEF_PARSING_ROADMAP.md).

## 0) Режимы парсинга (актуально)

### 0.0 Целевая архитектура (вариант B, код)

Один пользовательский путь: **сообщение → rules → (опц.) LLM по роли → плоский `brief` → карточка в чате**.

| `PARSER_MODE` | Поведение |
|---------------|-----------|
| `rules` (default) | Только rule-based |
| `role_llm` | Rules + organizer/participant LLM → `brief_flat_mapper` → flat |

Переменная: `PARSER_MODE` на Railway. Алиас: `USE_STRUCTURED_BRIEF_PIPELINE=true` → `role_llm` (если `PARSER_MODE` не задан).

**Merger** (`brief_merger_system_prompt.md`) вызывается **только после вклада участника**. Результат: `group_conflicts` в карточке брифа.

Код: `parser_mode.py`, `brief_flat_mapper.py`, `brief_parser.parse_message_to_brief()`.  
Промпты (3): см. `bot/prompts/README.md`.

### 0.0.1 Детали

- При сбое LLM основной сценарий остаётся работоспособным (fallback на rules).
- Rule-based (всегда): страны, города, даты → `stay_experience` через `brief_stay_enrich.py`.
- LLM (`role_llm`): `preferences.stay_experience` и/или `location_preferences` + `accommodation_preferences` → flat `stay_experience` в `brief_flat_mapper.py`, затем enrich.

### 0.1 Live responses (формулировки, не парсинг)

- Флаг: `USE_LLM_LIVE_RESPONSES=true` (также `TRUE`, `yes`, `1`).
- Обязателен `LLM_API_KEY`; модель: `LLM_LIVE_MODEL` (fallback: `LLM_PARSER_MODEL`).
- Промпты: `bot/prompts/live_response_system_prompt.md`, `live_response_user_prompt_template.md`.
- **Область:** только короткий intro при обработке текста организатора/участника (`organizer_dump`, `organizer_clarify`, `participant_contribute`). Меню, приглашение, sharing, help — статические тексты.
- Диагностика: логи Railway `Runtime flags: live_responses=...`; при успехе — `Live response from LLM`. Подробнее: `LIVE_RESPONSE.md`, `SCENARIO_AUDIT.md` §2.

## 1) Единая схема полей

- `context_raw` (`string`) — исходный текст пользователя (всегда сохраняется).
- `budget_rub_max` (`int`) — верхняя граница бюджета в рублях.
- `budget_eur_max` (`int`) — бюджет в евро, если указан явно.
- `budget_amount_max` (`int`) — сумма при бюджете в иностранной валюте (USD, GBP, TRY, AED и т.д.).
- `budget_currency` (`string`) — код валюты (`EUR`, `USD`, …) при `budget_amount_max` или валютных полях `budget_*_max`.
- `budget_usd_max`, `budget_gbp_max`, … (`int`) — валютные алиасы из rule-based парсера.
- `budget_rub_min` (`int`) — нижняя граница при диапазоне («400–600к»).
- `budget_flexible` (`bool`) — бюджет без жёсткой суммы («гибкий»).
- `flight_preferences` (`string[]`) — класс/формат перелёта (эконом, бизнес и т.п.).
- `adults` (`int`) — число взрослых.
- `kids_count` (`int`) — число детей.
- `kid_age` (`int`) — возраст ребенка, если указан.
- `months` (`string[]`) — месяцы/окна поездки.
- `date_range_raw` (`string`) — диапазон дат как в тексте.
- `trip_duration_days_raw` (`string`) — длительность поездки (например, `5-7 дней`).
- `flight_hours_max` (`int`) — желаемый лимит часов в пути.
- `transfers_allowed` (`bool`) — допустимость пересадок.
- `visa_required` (`bool`) — нужна ли виза.
- `visa_status` (`string`) — статус (есть/оформляется и т.д.).
- `visa_notes` (`string[]`) — уточняющие визовые заметки.
- `documents_discussed` (`bool`) — тема документов явно обсуждена.
- `passports_status` (`string`) — статус загранпаспортов.
- `passports_notes` (`string[]`) — заметки по загранпаспортам.
- `trip_title` (`string`) — короткое имя поездки для карточки (2–4 слова). Пересчитывается в `brief_display.sync_trip_title()` после парсинга и merge: страна из `stay_experience` / направления → «Во/В …» + уточнение состава («с семьёй», «вдвоём», «с компанией») или только направление. Пример: `Во Францию с семьёй`.
- `stay_experience` (`object`) — сценарий отдыха: `setting`, `accommodation_style`, `trip_style`, `season_note` (собирается из текста, направления и дат; см. `brief_stay_enrich.py`).
- `climate` (`string`) — legacy, дублируется из `stay_experience` для совместимости.
- `trip_type` (`string`) — legacy, формат отдыха.
- `activity_preferences` (`string[]`) — доп. пожелания.
- `constraints_notes` (`string[]`) — ограничения/важные рамки.
- `party_preferences` (`object`) — пожелания по ролям/участникам.

## 2) Правила: извлекаем / не извлекаем / когда уточняем

### 2.1 Извлекаем

- Извлекаем поле только если в тексте есть явный сигнал.
- Для числовых полей используем только валидный контекст (деньги отдельно от часов/дней).
- Для списков добавляем уникальные значения без дублей.
- Для `party_preferences` фиксируем только реально упомянутые роли/людей.

### 2.2 Не извлекаем (анти-додумывание)

- Не заполняем поле по косвенным догадкам.
- Не подставляем “типичные” значения по умолчанию.
- Не делаем вывод “виза не нужна” только по факту “есть загранпаспорт”.
- Не классифицируем автоматически `сын/дочь/брат/сестра/внук/внучка` как взрослые/дети без явного контекста.

### 2.3 Когда уточняем

Если поле критично для принятия решения и явного сигнала нет, добавляем в список уточнений:

- бюджет;
- состав поездки (взрослые/дети);
- даты/окна дат;
- перелет (часы или пересадки);
- сценарий отдыха (если после обогащения контекста нет ни локации, ни формата).

Визы/документы на этапе MVP **извлекаем**, но **не добавляем в missing** (уточнение отложено).

## 3) Приоритеты белых пятен (gap priorities)

Приоритет P1 (обязательные для качественного брифа):
- бюджет;
- состав;
- даты/гибкость;
- перелет;
- визы/документы.

Приоритет P2 (влияют на релевантность и компромисс):
- климат;
- формат отдыха;
- направление;
- длительность.

Приоритет P3 (дополнительные уточнения):
- активности на месте;
- личные ограничения отдельных участников;
- транспорт на месте (аренда/трансферы/свой авто).

## 4) Критерии качества парсинга

- `No hallucinations`: нет полей без явного основания в тексте.
- `Field precision`: минимум ложных заполнений по критичным полям.
- `Field recall`: максимум корректно извлеченных явных фактов.
- `Gap quality`: в уточнениях только реально недостающие и значимые поля.

## 5) Рабочий цикл улучшения

1. Дополняем `brief_parsing_golden.jsonl` реальными кейсами.
2. Прогоняем `test_brief_parsing.py`.
3. Анализируем:
   - где модель додумала,
   - где пропустила,
   - где неверно структурировала.
4. Обновляем правила/промпт/валидацию.
5. Повторяем до достижения целевых метрик.

## 6) LLM-слои при `PARSER_MODE=role_llm`

Индекс промптов: `bot/prompts/README.md`.

| Слой | Промпт | Когда |
|------|--------|--------|
| Organizer parser | `brief_parser_organizer_system_prompt.md` | Каждое сообщение организатора с вводными |
| Participant parser | `brief_parser_participant_system_prompt.md` | Вклад участника |
| Merger | `brief_merger_system_prompt.md` | **Только** после вклада участника |

Merger не парсит свободный текст. Типы расхождений: `preference_difference`, `hard_conflict`, `harmless_addition`, `unclear`. В чате организатору — блок `group_conflicts` в карточке брифа.

Доп. поля события (аудит, подбор): `base_brief_structured`, `participant_inputs_structured`, `merged_brief_structured`.

## 7) Задел под подбор поездок (следующий этап)

Поверх плоского `brief` планируется слой recommendation-ready: нормализованное направление, hard vs soft constraints, provenance/confidence, типы конфликтов из merger. `context_raw` сохранять всегда. Детали — в roadmap фаза D (`BRIEF_PARSING_ROADMAP.md`).
