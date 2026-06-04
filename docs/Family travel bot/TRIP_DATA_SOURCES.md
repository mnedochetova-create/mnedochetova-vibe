# Источники данных для маршрута и нарратива

Откуда бот берёт **проверяемые факты** (не цены брони) для этапа после брифа.  
LLM синтезирует текст; **retrieval** даёт опору и `source_id` для карточек.

См. [`TRIP_EXPERIENCE_ARCHITECTURE.md`](TRIP_EXPERIENCE_ARCHITECTURE.md).

---

## 1) Принцип

| Источник | Используем для | Не используем для |
|----------|----------------|-------------------|
| **Согласованный бриф** | состав, желания, конфликты, must-visit | точных цен, расписания рейсов |
| **Открытые API/библиотеки** | гео, расстояния, сезон, описания POI, часовые пояса | брони, оплаты |
| **Travelpayouts / OTA** (v2+, с токеном) | ориентиры цен перелёта, deeplink | черновик маршрута без дисклеймера |

**Политика:** в промпт LLM попадают только `retrieved_facts[]` с полями `{fact, source_id, confidence}`. Сырой веб в чат не льём.

---

## 2) Открытые и условно-бесплатные источники (рекомендуемый стек)

### Геокодирование и места

| Источник | Что даёт | Доступ | Примечание |
|----------|----------|--------|------------|
| [Nominatim](https://nominatim.org/) (OSM) | координаты, границы, «Городец» → объект | API, лимиты, User-Agent | кэш в боте, не спамить |
| [OpenStreetMap](https://www.openstreetmap.org/) | POI, дороги | ODbL | атрибуция при публичном экспорте карт |
| [GeoNames](https://www.geonames.org/) | города, альтернативные имена | регистрация username | полезно для RU регионов |
| [Wikidata](https://www.wikidata.org/) | связи «город — регион — страна» | SPARQL / API | нормализация «Ивановская область» |
| [Wikipedia API](https://www.mediawiki.org/wiki/API:Main_page) | краткие описания (extract) | открытый | только extract + ссылка, не полная статья в промпт |

### Расстояния и маршруты (по `movement_mode`)

| Источник | Режимы | Ограничение |
|----------|--------|-------------|
| OSRM / [OpenRouteService](https://openrouteservice.org/) | `car`, `walk` (profile foot), частично `bike` | свой инстанс или API key; не для `boat_private` |
| — | `train`, `ferry`, `boat_private` | расписание в v1 **не** из API — заметки из брифа + `open_questions` |
| — | `flight` | Travelpayouts после short-list |

Для **impression_domestic** (Иваново ↔ Городец): OSRM/ORS → «~N км, ~X ч» в `route_segment`, с дисклеймером «оценка».

### Сезон и погода (нарратив, не прогноз брони)

| Источник | Что даёт |
|----------|----------|
| [Open-Meteo](https://open-meteo.com/) | климатические нормы по месяцу, исторические диапазоны |
| [seasonal данные Wikipedia/Wikidata](https://www.wikidata.org/) | средние условия курортного сезона |

В карточке `story`: «в конце августа обычно…», не «завтра будет дождь».

### Визы и безопасность (осторожно)

| Источник | Примечание |
|----------|------------|
| Официальные сайты МИД / консульств | только ссылка «проверьте актуальные правила», не вывод LLM как факт |
| [Timatic-подобные](https://www.iata.org/) | платные; в v1 не обещать автоматическую визовую проверку |

---

## 3) Коммерческие (этап F воронки, не черновик)

| Источник | Env | См. |
|----------|-----|-----|
| Travelpayouts Data API | `TRAVELPAYOUTS_TOKEN` | [`archive/TRAVELPAYOUTS_AVIASALES_FIELDS.md`](archive/TRAVELPAYOUTS_AVIASALES_FIELDS.md) |

Подключать **после** short-list сценария: «примерные цены на перелёт в окно дат», partner deeplink, без полей багажа/возврата как факт из API.

---

## 4) Архитектура retrieval в боте (план)

```
recommendation_ready + content_brief
    → normalize_places()     # Nominatim + Wikidata id
    → fetch_distance_matrix() # OSRM/ORS для ground сегментов
    → fetch_climate_snippets() # Open-Meteo по месяцам из брифа
    → pack retrieved_facts[]
    → LLM Planner / Narrator
    → HTML cards (+ source footnotes)
```

| Модуль (план) | Роль |
|---------------|------|
| `trip_facts_retrieval.py` | HTTP-клиенты, кэш, rate limit |
| `trip_place_resolver.py` | must_visit / regions → geo ids |
| `trip_proposal_pipeline.py` | LLM с facts в JSON |

**Кэш:** disk/redis по `place_id + month`, TTL 7–30 дней для климат/гео.

**Секреты:** только env; в репозиторий не коммитить. Для Nominatim — корректный `User-Agent` с контактом.

---

## 5) Что показываем пользователю

- В HTML-карточке: «Оценка расстояния: ~320 км (OSRM)».
- В `story`: «По климатическим данным для августа… (Open-Meteo)».
- Ссылка «Подробнее» → Wikipedia/Wikidata, не голый LLM.
- Если retrieval failed — честно: «не удалось подтянуть расстояние, уточним на этапе планирования».

---

## 6) Флаг и этапы

| Этап | Данные |
|------|--------|
| v0 (сейчас) | только бриф + LLM без retrieval |
| v1 | Nominatim + Wikidata нормализация |
| v2 | OSRM/ORS для ground + Open-Meteo |
| v3 | Travelpayouts на short-list |

`TRIP_EXTERNAL_FACTS_ENABLED=true` — включает v1+.

---

## 7) Юридическое и качество

- Соблюдать ToS каждого API (Nominatim: max 1 req/s, кэш).
- Не хранить персональные данные в кэше гео дольше сессии без необходимости.
- Логировать `source_id` в parse/session логах для разбора ошибок фактов.
