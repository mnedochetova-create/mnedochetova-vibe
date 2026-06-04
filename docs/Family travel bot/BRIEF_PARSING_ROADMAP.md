# Roadmap: парсинг и бриф (killer feature)

**Статус (2026-05):** вариант B в коде (`PARSER_MODE`, `brief_flat_mapper`, merger после участника).  
**Канон по режимам и полям:** [`PARSING_SPEC.md`](PARSING_SPEC.md) — не дублировать здесь.  
**Сводка «план / сделано / впереди»:** см. также [`MVP_BOT_SPEC.md`](MVP_BOT_SPEC.md) §4.0, §8.

## Цель

- Wow в первые 30–60 с после вводных: точный бриф без додумывания.
- Данные пригодны для этапа **подбора поездок** (см. § «Мост к подбору» в `PARSING_SPEC` или отдельный черновик позже).

## Критерии успеха (кратко)

1. Понял с первого раза (P1-поля из `PARSING_SPEC` §3).
2. Умные уточнения (1–2 пункта, не анкета).
3. Карточка брифа сканируется за ~5 с.
4. Расхождения группы видны в карточке (`group_conflicts`, `group_open_questions`).
5. Уточнения не затирают бриф (`merge_brief_clarify`, `organizer_dump`).

Live LLM (`USE_LLM_LIVE_RESPONSES`) — conversation / mixed / corner / voc_feedback; killer — парсер + HTML-бриф (`LIVE_RESPONSE.md`).

## Сделано в коде (вне исходных чекбоксов roadmap)

| Область | Реализация |
|---------|------------|
| Merger | Только `conflicts` + `open_questions` + `organizer_update_text`; **не** пишет в `event.brief` (`brief_merger.py`, `PARSING_SPEC` §6) |
| Вход merger | `flat_brief_json` + `organizer_structured_history` + structured участников |
| Организатор | Кнопка **«Принять сводку»** → `organizer_accepted_group_summary` (без автоправки полей брифа) |
| Участник | Промпт паритета с organizer; `extract_brief_rule_based(..., role=participant)` |
| Corner | defer, autofill, share_visibility, supplement, media; LLM + `trips_json` |
| Голос | Whisper → общий `ingest_user_text` (`voice_input.py`) |
| Локаль | `language_code` в live/corner (`user_locale.py`) |
| VOC | Оценка 1–5 + отзыв после invite (`voc_feedback`) |
| Видимость брифа | `field_visibility` для participant / plain-share |
| Invite | `brief_deferred_at`, invite с черновиком при gaps |
| CI | `test_brief_merger.py`, `test_participant_rule_based.py`, 138+ tests |

## Риски (актуальные)

- [x] Golden расширен (22 кейса, rules + enrich; `expected_nested` для stay/party).
- [ ] Направления в `activity_preferences` — нужна нормализация для подбора (фаза D).
- [x] `party_preferences` — базовые rules (split-отели, мама/муж/племянник); сложные фразы — LLM.
- [x] Метрики P1 в CI: `field_recall ≥ 0.97`, `case_pass_rate ≥ 0.95` (`test_brief_parsing.py`).

## План работ

### Фаза A — Диагностика

- [x] 5 кейсов P1 — **авторетест в CI** (`test_p1_manual_retest.py`, `bot-tests.yml`).
- [ ] Колонка «в боте» в [`P1_MANUAL_RETEST.md`](P1_MANUAL_RETEST.md) — ручной smoke в Telegram после Railway.
- [ ] Railway: `PARSER_MODE=role_llm`, `LLM_API_KEY`.

### Фаза B — Качество извлечения

- [x] Расширить golden (`brief_parsing_golden.jsonl`, participant cases).
- [x] Правки `brief_parser.py` (party, stay enrich).
- [x] Промпт participant: stay_experience, РФ/комбо, routing полей, связь с merger (`brief_parser_participant_system_prompt.md`).
- [x] Merger prompt + контракт «не трогать flat brief» (`brief_merger_system_prompt.md`).
- [x] `pytest bot/tests/test_brief_parsing.py` + пороги P1 + `test_brief_p1_organizer_flow.py` + merger/participant rules.

### Фаза C — Wow в чате (UX-апрув)

- [ ] `format_brief_unified` — направления, party.
- [ ] При необходимости блок «что поняла» перед карточкой.

### Фаза D — Подбор

- [x] `RECOMMENDATION_BRIEF_SCHEMA.md`, `TRIP_FROM_BRIEF_SPEC.md`, `TRIP_PROPOSAL_USER_FLOW.md`.
- [x] `TRIP_EXPERIENCE_ARCHITECTURE.md`, `TRIP_ROUTE_COMPOSITION.md`, `TRIP_DATA_SOURCES.md` — целевая модель (LLM+cards, маршрут, данные).
- [x] `trip_from_brief.py` — снимок, readiness (**временные** rules-черновики, не целевой продукт).
- [x] Интеграция в `main.py` за `TRIP_PROPOSALS_ENABLED` (по умолчанию выкл.).
- [ ] `TRIP_TRANSPORT_MODEL`: `modes_present`, readiness по режимам (не один `missing_transport`).
- [ ] Парсер: извлекать train/ferry/boat/walk из текста (`transport_modes_declared`).
- [x] Промпты: мультимодальность в organizer/participant/merger/live/corner/trip_proposal — см. `bot/prompts/README.md`.
- [ ] `content_brief` + LLM Planner/Narrator + HTML card renderer.
- [ ] `route_plan` / `narrative_blocks` на event.
- [ ] Retrieval: Nominatim/Wikidata → OSRM/Open-Meteo (`TRIP_EXTERNAL_FACTS_ENABLED`).
- [ ] Short-list UI; Travelpayouts **после** short-list only.

## Код (точки входа)

| Модуль | Назначение |
|--------|------------|
| `parser_mode.py` | `PARSER_MODE` |
| `brief_parser.py` | rules (`role=organizer\|participant`), `parse_message_to_brief()` |
| `brief_flat_mapper.py` | structured → flat |
| `brief_pipeline.py` | LLM organizer/participant/merger API |
| `brief_merger.py` | payload merger, apply result, notify organizer |
| `brief_visibility.py` | скрытие полей в карточке |
| `corner_guidance.py` | corner LLM |
| `voice_input.py` | Whisper |
| `main.py` | handlers, `format_brief_unified`, FSM, callbacks `merger:accept`, `trip:show_draft` |
| `trip_from_brief.py` | recommendation-ready, readiness, draft proposals |

Промпты: индекс [`bot/prompts/README.md`](../../bot/prompts/README.md).

## Не ломать

`merge_brief_clarify`, restore из `organizer_dump`, rules-first merge, `pick_best_organizer_event`.
