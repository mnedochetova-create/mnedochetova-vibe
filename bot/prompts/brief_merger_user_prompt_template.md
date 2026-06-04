# Merge: сравнение брифа и вклада участника

Проверь **все способы передвижения** в `flat_brief_json`: `trip_transport`, `flight_*`, `ground_transport_notes`, `activity_preferences`, `participant_preferences`. Расхождения по режимам (перелёт vs машина vs паром vs пешком) — `transport_mode_difference`.

Данные (JSON):
{{merge_payload_json}}

---
Верни только JSON по system prompt (conflicts, open_questions, organizer_update_text, …). Не меняй flat brief.
