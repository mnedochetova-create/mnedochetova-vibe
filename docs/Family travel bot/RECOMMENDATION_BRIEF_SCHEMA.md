# Recommendation-ready brief — схема для вариантов поездки

Нормализованный слой поверх плоского `event.brief`. **Жёсткий контракт — только бриф;** снимок и `route_plan` — вход для **LLM + HTML-карточек** (см. [`TRIP_EXPERIENCE_ARCHITECTURE.md`](TRIP_EXPERIENCE_ARCHITECTURE.md)).

Код: `bot/src/trip_from_brief.py` → `build_recommendation_ready()` (v0; `content_brief` и `route_plan` — по спеке, в коде постепенно).

Связанные документы: [`TRIP_FROM_BRIEF_SPEC.md`](TRIP_FROM_BRIEF_SPEC.md), [`TRIP_ROUTE_COMPOSITION.md`](TRIP_ROUTE_COMPOSITION.md), [`TRIP_DATA_SOURCES.md`](TRIP_DATA_SOURCES.md), [`PARSING_SPEC.md`](PARSING_SPEC.md).

## 1) Назначение

| Вход | Выход |
|------|--------|
| `event.brief` + метаданные события | `recommendation_ready` (JSON) |
| `recommendation_ready` | 2–3 `trip_proposals` (черновик → short-list) |

Парсинг сообщений **не** дублируется — только чтение уже собранного брифа.

## 2) Корневой объект `recommendation_ready`

```json
{
  "schema_version": "1",
  "built_at": 1717000000,
  "event_code": "abc123",
  "trip_title": "Во Францию с семьёй",
  "trip_mode": "single_destination | combo_route | domestic_ground | explore",
  "trip_archetype": "single_resort | multi_country_combo | impression_domestic | road_trip | hub_and_spoke | explore_open",
  "destinations": {
    "primary": "Франция",
    "alternatives": ["Италия"],
    "combo_countries": [],
    "regions": ["Ивановская область"],
    "must_visit": ["Городец"],
    "labels": []
  },
  "dates": {
    "months": ["июль"],
    "date_range_raw": "в середине июля",
    "trip_duration_days_raw": "10 дней",
    "flexible": false
  },
  "group": {
    "adults": 6,
    "kids_count": 1,
    "kid_ages": [6]
  },
  "budget": {
    "rub_max": null,
    "eur_max": 15000,
    "currency": "EUR",
    "flexible": false
  },
  "transport": {
    "modes_present": ["flight", "car", "ferry", "walk"],
    "modes_primary": ["flight", "car"],
    "legacy_trip_transport": "ground",
    "requires_international_flight": false,
    "flight": {
      "hours_max": null,
      "transfers_allowed": true,
      "hours_unrestricted": false,
      "preferences": []
    },
    "ground": {
      "drive_hours_max": null,
      "notes": []
    },
    "other_modes": [
      {"mode": "boat_private", "notes": ["частная лодка"]}
    ],
    "segment_hints": [],
    "open_transport_questions": []
  },
  "stay_experience": {
    "setting": ["Юг Франции"],
    "accommodation_style": [],
    "trip_style": ["пляж"],
    "season_note": ""
  },
  "constraints": {
    "hard": [],
    "soft": ["перелёт: эконом"]
  },
  "participants_summary": [
    {"name": "Анна", "highlights": ["перелёт до 4 ч"]}
  ],
  "group_signals": {
    "conflicts": ["..."],
    "open_questions": ["..."],
    "organizer_accepted_summary": "..."
  },
  "provenance": {
    "organizer_dump_present": true,
    "brief_confirmed_at": 1716999999
  }
}
```

### `trip_mode` и `trip_archetype`

| `trip_mode` | Когда |
|----------|--------|
| `combo_route` | комбинация стран в activity |
| `domestic_ground` | РФ / `trip_transport=ground` |
| `single_destination` | одна страна/база |
| `explore` | альтернативы без выбора |

| `trip_archetype` | Когда | См. |
|----------------|--------|-----|
| `impression_domestic` | регионы, must_visit, впечатления по РФ | [`TRIP_ROUTE_COMPOSITION.md`](TRIP_ROUTE_COMPOSITION.md) §3.1 |
| `multi_country_combo` | FR/IT/HR и т.д. | §3.2 |
| `road_trip` | авто, ground_notes | §3.3 |
| `hub_and_spoke` | город входа + выезды | — |
| `single_resort` / `explore_open` | курорт / выбор направления | — |

Полная модель режимов (пешком, лодка, поезд, …): [`TRIP_TRANSPORT_MODEL.md`](TRIP_TRANSPORT_MODEL.md).

`requires_international_flight`: `true` только если в `modes_present` есть `flight` и поездка не чисто domestic без зарубежья.  
Readiness — **по заявленным режимам**, не один блокер «перелёт» на всех (см. §4).

## 2b) `content_brief` (для LLM Narrator, план)

Агрегат «богатого» контекста (не дублировать сырой dump):

```json
{
  "impressions": ["ремёсла", "родина"],
  "places_named": ["Городец", "Иваново"],
  "combo_intent": "Франция, Италия, Хорватия",
  "season_phrases": ["конец августа"],
  "style_tags": ["пляж", "спокойный"],
  "participant_quotes": [{"name": "Ann", "text": "перелёт до 4 ч"}],
  "transport_summary": "машина по регионам, в Городце пешком",
  "modes_named": ["car", "walk"],
  "organizer_accepted_summary": "..."
}
```

Сбор: из `activity_preferences`, `must_visit`, `regions`, `stay_experience`, `ground_transport_notes`, `constraints_notes`, `participant_preferences`, merger.

## 3) Объект `trip_proposal` (сценарий поездки)

```json
{
  "proposal_id": "p1",
  "status": "draft",
  "title": "Франция · спокойный пляжный отдых",
  "destination_label": "Франция, Юг",
  "trip_mode": "single_destination",
  "fit_score": 0.82,
  "why_fit": ["совпадает с stay_experience", "даты июль"],
  "tradeoffs": ["без проверки цен на этапе черновика"],
  "tags": ["спокойный", "семейный"],
  "next_steps_human": "Уточнить город вылета и сравнить перелёт",
  "route_plan": null,
  "narrative_blocks": null,
  "data_sources": ["llm_draft"],
  "retrieved_facts": [],
  "external_links": []
}
```

**Целевой объект** (после шага 15–16): `route_plan` — см. [`TRIP_ROUTE_COMPOSITION.md`](TRIP_ROUTE_COMPOSITION.md); `narrative_blocks` — hook, geo_logic, season_weather, highlights_from_brief.

**Запрещено на этапе draft:** выдуманные цены, бронь, гарантия погоды на дату, визы без ссылки на источник.

## 4) Готовность к генерации (`trip_readiness`)

Зависит от `trip_archetype` (не один список для всех).

| Код блокера | Смысл | Не применять когда |
|-------------|--------|---------------------|
| `brief_not_confirmed` | нет подтверждения брифа | — |
| `missing_dates` | нет окна поездки | — |
| `missing_budget` | нет бюджета | `budget_flexible` |
| `missing_direction` | нет стран/регионов/точек | `impression_domestic` с `regions`+`must_visit` |
| `missing_flight_constraints` | в брифе есть `flight`, нет часов/пересадок/ограничений | `flight` ∉ `modes_present` |
| `missing_drive_constraints` | в брифе есть `car`, нет заметок/`drive_hours_max` | `car` ∉ `modes_present` |
| `missing_marine_notes` | `ferry` / `boat_private` без пояснений | режим не заявлен |
| `missing_rail_preferences` | `train` критичен для маршрута (часто warning) | нет `train` |
| `missing_walk_scope` | `walk` между удалёнными точками без контекста | прогулки внутри города |
| `missing_must_visit` | impression без точек | опционально |

Устаревший код `missing_transport` в v0-коде → заменить на таблицу выше ([`TRIP_TRANSPORT_MODEL.md`](TRIP_TRANSPORT_MODEL.md) §5).

| Warning | Смысл |
|---------|--------|
| `hard_conflicts_unresolved` | `group_conflicts` — карточка `group_note` |
| `open_questions` | вопросы merger |
| `facts_partial` | retrieval не ответил — не блокировать сценарии |

## 4b) `retrieved_facts` (из открытых API)

```json
{"fact": "~280 км, ~4 ч на авто", "source_id": "osrm", "confidence": 0.7}
```

См. [`TRIP_DATA_SOURCES.md`](TRIP_DATA_SOURCES.md).

## 5) Поля события (`event.json`)

| Поле | Тип | Описание |
|------|-----|----------|
| `recommendation_ready` | object | снимок §2 |
| `trip_proposals_status` | string | `idle` \| `blocked` \| `scenarios` \| `route_draft` \| `narrative` \| `draft` \| `ready` \| `shortlist` \| `price_watch` (см. lifecycle в TRIP_FROM_BRIEF_SPEC) |
| `content_brief` | object | §2b для LLM |
| `trip_proposals` | array | варианты §3 |
| `trip_proposals_generated_at` | int | unix |
| `trip_proposals_blockers` | string[] | человекочитаемые причины `blocked` |
| `selected_trip_proposal_id` | string \| null | фиксация short-list (этап 2) |

## 6) Версионирование схемы

- `schema_version` в `recommendation_ready` — при ломающих изменениях увеличивать.
- Плоский `brief` остаётся каноном для парсинга; `recommendation_ready` — производный снимок на момент генерации.
