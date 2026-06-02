# Roadmap: парсинг и бриф (killer feature)

**Статус:** вариант B в коде (`PARSER_MODE`, `brief_flat_mapper`, merger только для участников).  
**Канон по режимам и полям:** [`PARSING_SPEC.md`](PARSING_SPEC.md) — не дублировать здесь.

## Цель

- Wow в первые 30–60 с после вводных: точный бриф без додумывания.
- Данные пригодны для этапа **подбора поездок** (см. § «Мост к подбору» в `PARSING_SPEC` или отдельный черновик позже).

## Критерии успеха (кратко)

1. Понял с первого раза (P1-поля из `PARSING_SPEC` §3).
2. Умные уточнения (1–2 пункта, не анкета).
3. Карточка брифа сканируется за ~5 с.
4. Расхождения группы видны в карточке (`group_conflicts`).
5. Уточнения не затирают бриф (`merge_brief_clarify`, `organizer_dump`).

Live LLM (`USE_LLM_LIVE_RESPONSES`) — только intro; killer — парсер + HTML-бриф (`LIVE_RESPONSE.md`).

## Риски (актуальные)

- [x] Golden расширен (22 кейса, rules + enrich; `expected_nested` для stay/party).
- [ ] Направления в `activity_preferences` — нужна нормализация для подбора (фаза D).
- [x] `party_preferences` — базовые rules (split-отели, мама/муж/племянник); сложные фразы — LLM.
- [x] Метрики P1 в CI: `field_recall ≥ 0.97`, `case_pass_rate ≥ 0.95` (`test_brief_parsing.py`).

## План работ

### Фаза A — Диагностика

- [ ] 3–5 реальных вводных (организатор + участник) — **ручной ретест в боте**.
- [ ] Таблица: извлекли / потеряли / додумали.
- [ ] Railway: `PARSER_MODE=role_llm`, `LLM_API_KEY`.

### Фаза B — Качество извлечения

- [x] Расширить golden (`brief_parsing_golden.jsonl`, participant cases).
- [x] Правки `brief_parser.py` (party, stay enrich) и промпт participant (stay_experience).
- [x] `pytest bot/tests/test_brief_parsing.py` + пороги P1 + `test_brief_p1_organizer_flow.py`.

### Фаза C — Wow в чате (UX-апрув)

- [ ] `format_brief_unified` — направления, party.
- [ ] При необходимости блок «что поняла» перед карточкой.

### Фаза D — Подбор

- [ ] `RECOMMENDATION_BRIEF_SCHEMA.md` или § в `PARSING_SPEC`.

## Код (точки входа)

| Модуль | Назначение |
|--------|------------|
| `parser_mode.py` | `PARSER_MODE` |
| `brief_parser.py` | rules, `parse_message_to_brief()` |
| `brief_flat_mapper.py` | structured → flat |
| `brief_pipeline.py` | LLM organizer/participant/merger |
| `main.py` | handlers, `format_brief_unified`, `run_group_merger_for_event` |

## Не ломать

`merge_brief_clarify`, restore из `organizer_dump`, rules-first merge, `pick_best_organizer_event`.
