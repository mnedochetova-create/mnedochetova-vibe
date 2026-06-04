# Модель передвижения в брифе и маршруте

В брифе может быть **любая комбинация** способов передвижения — не только «перелёт vs наземка».  
Снимок `recommendation_ready` и `route_plan` описывают **что зафиксировали**, а readiness спрашивает **только недостающие параметры для уже упомянутых режимов**.

Связано: [`RECOMMENDATION_BRIEF_SCHEMA.md`](RECOMMENDATION_BRIEF_SCHEMA.md), [`TRIP_ROUTE_COMPOSITION.md`](TRIP_ROUTE_COMPOSITION.md), [`TRIP_EXPERIENCE_ARCHITECTURE.md`](TRIP_EXPERIENCE_ARCHITECTURE.md).

---

## 1) Принцип

| Правило | Смысл |
|---------|--------|
| **Бриф = всё что угодно** | Пешком, машина, поезд, паром, частная лодка, автобус, перелёт, такси, велосипед, канатка, «как получится» — фиксируем как факты, не схлопываем в один бинарный режим |
| **Не навязывать перелёт** | Нет сигнала «летим» → нет блокера `missing_flight_constraints` |
| **Сегмент ≠ вся поездка** | Между точками в `route_plan` у каждого перехода свой `movement.mode` |
| **LLM не придумывает транспорт** | Новый способ в маршруте только если бриф допускает или как гипотеза в `open_questions` |

Текущий парсер (`brief_transport`: `flight` \| `ground`) — **упрощение для карточки брифа**; целевая модель ниже. До расширения парсера режимы собираются из `activity_preferences`, `ground_transport_notes`, `constraints_notes`, `context_raw`, вклада участников.

---

## 2) Словарь `movement_mode`

Коды для `recommendation_ready.transport.modes_present[]` и для `route_plan.segments[].movement_*`.

| Код | Примеры в тексте брифа | Типичные поля / заметки в брифе |
|-----|------------------------|----------------------------------|
| `flight` | перелёт, авиа, вылет, рейс | `flight_hours_max`, `transfers_allowed`, `flight_preferences` |
| `car` | на машине, авто, аренда авто, автопутешествие | `drive_hours_max`, `ground_transport_notes`, `flight_not_needed` |
| `train` | поезд, РЖД, еврорейл | notes, «без пересадок», класс |
| `bus` | автобус, междугородний | notes |
| `ferry` | паром, переправа | notes, сегмент море |
| `boat_private` | частная лодка, яхта, катер | notes, сезон, лицензия/опыт — в `constraints_notes` |
| `walk` | пешком, пешие, трекинг, пешая прогулка | дистанция/сложность в preferences |
| `bike` | велосипед | notes |
| `taxi_rideshare` | такси, трансфер | notes |
| `cableway` | канатная дорога | точечно в сегменте |
| `local_transit` | метро, трамвай, «общественный» | в городских сегментах |
| `mixed_unspecified` | «как удобнее», несколько без выбора | не блокировать; вынести в `open_questions` |
| `other` | вертолёт, санки, и т.д. | свободная строка в `transport_notes` |

**Не исчерпывающий список:** новые коды добавляются в схему; LLM использует `other` + `note`, Planner не выдумывает расписание.

---

## 3) Поля брифа (канон + целевые)

### Уже в flat `brief` (использовать при сборе снимка)

| Поле | Связь с режимами |
|------|------------------|
| `trip_transport` | legacy: `flight` \| `ground` — **не единственный** источник истины |
| `flight_*`, `transfers_allowed` | `flight` |
| `ground_transport_notes`, `drive_hours_max`, `flight_not_needed` | `car`, `train`, `ferry`, `boat_private`, … |
| `activity_preferences`, `constraints_notes` | любой режим (текст «на лодке», «пешком по старому городу») |
| `participant_preferences` | разный комфорт по режимам (перелёт 4 ч vs «без самолёта») |

### Целевые поля (фаза D парсера, опционально)

```json
{
  "transport_modes_declared": ["flight", "car", "ferry"],
  "transport_notes": ["частная лодка между островами", "пешком по Городцу"],
  "segment_transport_hints": [
    {"from_hint": "Италия", "to_hint": "Хорватия", "modes": ["ferry", "car"]}
  ]
}
```

До появления в парсере — заполняет **`build_transport_profile()`** в `trip_from_brief` (эвристики по тексту) или LLM при Planner.

---

## 4) Блок `transport` в `recommendation_ready`

```json
{
  "transport": {
    "modes_present": ["flight", "car", "walk"],
    "modes_primary": ["flight", "car"],
    "legacy_trip_transport": "ground",
    "requires_international_flight": false,
    "flight": {
      "hours_max": 4,
      "transfers_allowed": true,
      "preferences": ["эконом"]
    },
    "ground": {
      "drive_hours_max": 6,
      "notes": ["на машине между городами"]
    },
    "other_modes": [
      {"mode": "boat_private", "notes": ["частная лодка — только в августе"]},
      {"mode": "walk", "notes": ["пешком по центру Городца"]}
    ],
    "segment_hints": [],
    "open_transport_questions": []
  }
}
```

- **`modes_present`** — всё, что извлекли из брифа (может быть 5+ режимов).
- **`requires_international_flight`** — `true` только если есть `flight` **и** поездка не чисто domestic impression без зарубежья.
- **`legacy_trip_transport`** — для совместимости с карточкой брифа; readiness **не** опирается только на него.

---

## 5) Readiness — только по заявленным режимам

| Блокер | Когда | Когда **не** спрашивать |
|--------|--------|-------------------------|
| `missing_flight_constraints` | `flight` ∈ `modes_present` и нет часов/пересадок/«без ограничений» | нет `flight` в брифе |
| `missing_drive_constraints` | `car` ∈ `modes_present`, нет ни `drive_hours_max`, ни явной заметки про авто | только поезд/лодка без машины |
| `missing_rail_preferences` | `train` ∈ `modes_present` и критично для маршрута (опционально warning) | нет поезда в брифе |
| `missing_marine_notes` | `boat_private` \| `ferry` и нет ни одной заметки | — |
| `missing_walk_scope` | `walk` как **основной** способ между удалёнными точками без дистанции | прогулки внутри города — warning, не блокер |

**Никогда:** «укажите часы перелёта» для поездки, где в брифе только машина + лодка + пешие прогулки.

**Смешанная поездка (FR/IT/HR):** readiness по **входному** `flight` (если есть) + заметки по **стыкам** (`ferry`/`train`/`car`) в `segment_hints` или `open_transport_questions`.

---

## 6) Сегменты маршрута

Каждый переход — отдельный режим (см. [`TRIP_ROUTE_COMPOSITION.md`](TRIP_ROUTE_COMPOSITION.md)):

```json
{
  "segment_id": "s2",
  "label": "Хорватия · острова",
  "transport_in": {"mode": "ferry", "from_segment": "s1", "note": "из Италии"},
  "within_segment": [
    {"mode": "boat_private", "note": "между островами — из брифа"},
    {"mode": "walk", "note": "старый город пешком"}
  ],
  "movement_out": {"mode": "flight", "to_segment": "s3", "note": "короткий перелёт или поезд — уточнить"}
}
```

Planner обязан:

- брать `modes_present` из снимка;
- не ставить `flight` между соседними точками Золотого кольца, если в брифе `car` + `walk`;
- для `boat_private` — tradeoff и caveat, не фейковое расписание.

---

## 7) Нарратив и открытые данные

| Режим | Retrieval (когда включён) |
|-------|---------------------------|
| `car` | OSRM/ORS расстояние/время |
| `train` | без расписания в v1 — «уточнить на этапе брони», опционально ссылки |
| `ferry` / `boat_private` | сезон, порт — Wikipedia/Wikidata; не «есть рейс в 10:00» без API |
| `walk` | дистанция пешком OSRM `foot` profile |
| `flight` | Travelpayouts **после** short-list |

---

## 8) `content_brief` — транспорт для Narrator

```json
{
  "transport_summary": "вход перелётом; между странами паром/машина; на островах лодка; в городах пешком",
  "modes_named": ["flight", "ferry", "car", "boat_private", "walk"],
  "quotes": ["без ночных перелётов", "не больше 4 ч в самолёте"]
}
```

---

## 9) Код и парсинг (roadmap)

| Сейчас | Цель |
|--------|------|
| `trip_transport` flight/ground | `transport.modes_present[]` |
| `missing_transport` один блокер | блокеры по таблице §5 |
| `brief_transport.infer_trip_transport` | + `extract_transport_modes_from_brief()` |
| Промпт organizer/participant | явно извлекать лодку, пешком, поезд (без подмены перелётом) |

Флаг: расширение парсера — отдельная задача в [`BRIEF_PARSING_ROADMAP.md`](BRIEF_PARSING_ROADMAP.md); post-brief LLM уже может использовать текстовые hints из `content_brief`.
