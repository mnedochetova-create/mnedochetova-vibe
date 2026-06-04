# Контекст парсинга (participant)

role: {{role}}
source: {{source}}
participant_name: {{participant_name}}
message_text:
{{message_text}}

База поездки — передвижение организатора (личный вклад не отменяет; фиксируй расхождения в constraints/activity):
{{transport_context_json}}

---
Извлеки structured JSON по system prompt. Личные режимы: перелёт, машина, поезд, паром, лодка, пешком — не подменяй всё перелётом.
Верни только JSON.
