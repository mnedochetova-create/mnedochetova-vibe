# Состав маршрута и типы поездок

Как из брифа собирается **не «название страны»**, а **маршрут**: сегменты, перемещения, наполнение, порядок точек.  
Для LLM Planner + HTML-карточек `route_segment` / `route_overview`.

См. также: [`TRIP_EXPERIENCE_ARCHITECTURE.md`](TRIP_EXPERIENCE_ARCHITECTURE.md), [`RECOMMENDATION_BRIEF_SCHEMA.md`](RECOMMENDATION_BRIEF_SCHEMA.md), [`TRIP_TRANSPORT_MODEL.md`](TRIP_TRANSPORT_MODEL.md).

---

## 1) `trip_archetype` (продуктовый тип)

Дополняет `trip_mode` из снимка — задаёт **логику composition** и readiness.

| `trip_archetype` | Описание | Перелёт в readiness |
|------------------|----------|---------------------|
| `single_resort` | одна база, минимум переездов | только если `flight` ∈ `modes_present` |
| `multi_country_combo` | несколько стран, связная цепочка | по брифу (часто входной `flight` + `ferry`/`train`/`car` на стыках) |
| `impression_domestic` | РФ/регионы, впечатления (Иваново, Городец…) | **нет** |
| `road_trip` | авто/поезд/пешком, гибкий порядок | **нет**, если нет `flight` в брифе |
| `hub_and_spoke` | город входа + выезды | по заявленным режимам на каждом плече |
| `explore_open` | 2–3 гипотезы направления | по гипотезе |

Определение (эвристики → позже LLM-классификатор):

- `impression_domestic` — `domestic_ground` + `regions` / `must_visit` / setting без зарубежного primary.
- `multi_country_combo` — `combo_route` или 2+ стран в `combo_countries` / activity «комбинация стран».
- `road_trip` — `trip_transport=ground`, `ground_transport_notes`, «на машине».

---

## 2) Объект `route_plan` (целевая схема)

Хранится внутри `trip_proposal` или отдельно на event после выбора сценария.

```json
{
  "proposal_id": "p1",
  "archetype": "multi_country_combo",
  "entry_point": {"country": "Италия", "reason": "удобный вылет в конце августа"},
  "segments": [
    {
      "segment_id": "s1",
      "label": "Италия · Север/Лигурия",
      "days_hint": "5–7",
      "transport_in": {"mode": "flight", "note": "вход в Милан/Геную"},
      "within_segment": [{"mode": "walk", "note": "старый город пешком"}],
      "experiences": ["пляж", "гастрономия"],
      "must_visit": [],
      "movement_out": {"mode": "ferry", "to_segment": "s2", "alternatives": ["car", "train"]}
    },
    {
      "segment_id": "s2",
      "label": "Хорватия · побережье",
      "days_hint": "4–5",
      "transport_in": {"mode": "ferry", "from_segment": "s1", "alternatives": ["car"]},
      "experiences": ["море", "старые города"],
      "movement_out": {"mode": "train", "to_segment": "s3", "alternatives": ["flight", "car"]}
    },
    {
      "segment_id": "s3",
      "label": "Франция · Прованс/Лазурный берег",
      "days_hint": "5–7",
      "transport_in": {"mode": "train", "from_segment": "s2", "alternatives": ["flight", "car"]},
      "experiences": ["культура", "природа"]
    }
  ],
  "ordering_rationale": [
    "конец августа: комфортный вход в Италию",
    "Хорватия логично между Италией и Францией по морю/суше",
    "Франция — финальный блок перед вылетом домой"
  ],
  "open_questions": ["точка вылета из РФ", "аренда авто vs поезда"]
}
```

**Важно:** порядок и `ordering_rationale` — вывод LLM из брифа + фактов, не захардкоженный шаблон «Турция → Греция».

---

## 3) Реальные кейсы из продукта

### 3.1 Впечатления: Ивановская область, Городец

| Вход из брифа | Composition |
|---------------|-------------|
| `regions`, `must_visit`, `activity_preferences` («впечатления», «родина», ремёсла) | `impression_domestic` |
| `modes_present`: `car`, `walk` | сегменты = **локации**; переходы `car`, внутри — `walk` |
| Нет `flight` в брифе | **не блокировать** `missing_flight_constraints` |

**Карточки:** `route_overview` «маршрут по впечатлениям» → несколько `route_segment` (Иваново → Городец → …) → `story` «что увидим/расскажем».

### 3.2 Комбо: Франция, Италия, Хорватия

| Вход | Composition |
|------|-------------|
| Несколько стран / комбо в activity | `multi_country_combo` |
| `months`: конец августа | Narrator: сезон, море, жара/комфорт |
| Богатый `stay_experience` + пожелания группы | наполнение **по сегментам**, не дублировать одним абзацем |

**Продуктовая ценность:** не «3 карточки стран», а **1–2 сценария цепочки** (напр. IT→HR→FR vs FR→IT→HR) с объяснением tradeoffs (перелёты, усталость детей, бюджет).

### 3.3 Авто-путешествие без перелёта

- Readiness: направление + даты + бюджет + уточнения по **заявленным** режимам (`car`, `train`, …), не перелёт.
- Сегменты: дистанции, ночёвки; `movement.mode` из словаря TRIP_TRANSPORT_MODEL.
- Карточка `story`: дорога как часть отдыха, остановки.

---

## 4) Связь полей брифа → сегменты

| Поле | Роль в composition |
|------|---------------------|
| `destination_primary` / `alternatives` | якоря или ветвления сценариев |
| `regions` | domestic / hub сегменты |
| `must_visit_places` | обязательные stops в `segments[]` |
| `activity_preferences` | теги `experiences`, комбо-строка |
| `stay_experience.*` | стиль сегмента (пляж/культура/спокойный) |
| `trip_duration_days_raw` | бюджет дней на сегмент |
| `budget_*` | tradeoffs (меньше перелётов vs дороже база) |
| `participant_preferences` | разный комфорт → разные `movement_out` или предупреждения |

Парсер должен по возможности выносить **имена локаций** в `must_visit` / `regions`, а не только в свободный текст — см. фаза D в [`BRIEF_PARSING_ROADMAP.md`](BRIEF_PARSING_ROADMAP.md).

---

## 5) «Что рассказываем» (`narrative_blocks`)

Отдельный выход LLM (этап D), привязан к `route_plan`:

```json
{
  "hook": "Поездка в конце августа — окно для Средиземноморья без пика жары",
  "geo_logic": "Вход через Италию, дальше вдоль побережья к Франции",
  "season_weather": "В августе на побережье … (source: open_meteo_climate)",
  "group_fit": "С детьми меньше перелётов — больше наземных переездов между сегментами",
  "highlights_from_brief": ["цитата или перефраз из activity_preferences"],
  "caveats": ["расхождение по часам перелёта у участников"]
}
```

Правила Narrator:

- Каждый сильный тезис — **привязка к полю брифа** или `retrieved_facts`.
- Нет фактов «из головы» про цены, визы, расписание рейсов без API.
- Погода — **диапазон/сезон**, не «будет +25» как гарантия.

---

## 6) Отличие от `trip_proposal` v0

| v0 (rules) | Цель |
|------------|------|
| `title` + `destination_label` | `route_plan` + `narrative_blocks` |
| `why_fit` буллеты | `story` карточка + `ordering_rationale` |
| один `trip_mode` | `trip_archetype` + сегменты |

Миграция схемы: `schema_version` 2 в `recommendation_ready` — см. [`RECOMMENDATION_BRIEF_SCHEMA.md`](RECOMMENDATION_BRIEF_SCHEMA.md).
