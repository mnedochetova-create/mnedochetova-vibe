# Контекст парсинга (organizer)

role: {{role}}
source: {{source}}
message_text:
{{message_text}}

Уже в брифе по передвижению (не перезаписывай без явного сигнала в message_text; дополняй и согласуй режимы):
{{transport_context_json}}

---
Извлеки structured JSON по system prompt. Учти **мультимодальность**: перелёт, машина, поезд, паром, лодка, пешком — отдельно, не своди всё к flight_hours_max.
Верни только JSON.
