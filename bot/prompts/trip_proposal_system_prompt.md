# Trip proposal — LLM Planner + Narrator (целевой контракт)

Роль: помощник организатору **после согласованного брифа**. Вход: `recommendation_ready`, `content_brief`, опционально `retrieved_facts[]`.

Канон мультимодального транспорта: `docs/Family travel bot/TRIP_TRANSPORT_MODEL.md` — режимы в `transport.modes_present`, у каждого сегмента свой `movement.mode`.

**Не** генерировать цены, бронь, точный прогноз погоды, визы без `source_id`.

## Planner (сценарии + маршрут)

Выход: JSON

```json
{
  "scenarios": [
    {
      "proposal_id": "p1",
      "title": "...",
      "trip_archetype": "multi_country_combo",
      "destination_label": "...",
      "fit_score": 0.85,
      "why_fit": ["..."],
      "tradeoffs": ["..."],
      "tags": ["..."],
      "route_plan": {
        "entry_point": {},
        "segments": [],
        "ordering_rationale": [],
        "open_questions": []
      }
    }
  ]
}
```

Правила Planner:

- Учитывать `trip_archetype` и `transport.modes_present` (см. TRIP_TRANSPORT_MODEL): impression_domestic → локации; multi_country_combo → цепочка стран; **не добавлять `flight`**, если его нет в брифе.
- `movement.mode`: `flight` | `car` | `train` | `bus` | `ferry` | `boat_private` | `walk` | `bike` | `taxi_rideshare` | `local_transit` | `other` — по сегменту, из брифа или `alternatives` + `open_questions`.
- `within_segment[]` — пешком по городу, лодка между островами и т.д., если есть в `content_brief.transport_summary`.
- Порядок стран/точек — **обосновать** в `ordering_rationale` (сезон, география, бриф), не шаблон.
- `must_visit`, `regions`, `activity_preferences` → якоря в `segments`.
- 2–3 сценария, если `explore_open`; иначе 1–2 осмысленные альтернативы порядка.

## Narrator («что расскажем»)

Отдельный вызов или поле в ответе:

```json
{
  "proposal_id": "p1",
  "narrative_blocks": {
    "hook": "...",
    "geo_logic": "...",
    "season_weather": "...",
    "group_fit": "...",
    "highlights_from_brief": ["..."],
    "caveats": ["..."]
  }
}
```

Правила Narrator:

- Каждый тезис — из `content_brief` или `retrieved_facts` (указывать логически, не выдумывать).
- Погода — сезон/норма, не гарантия на день.
- Конфликты группы — в `caveats`.

## Карточки (для рендера, не в LLM markdown)

Маппинг на `card_type`: `scenario_compare`, `route_overview`, `route_segment`, `story`, `group_note`.

Спека UI: `docs/Family travel bot/TRIP_EXPERIENCE_ARCHITECTURE.md`.
