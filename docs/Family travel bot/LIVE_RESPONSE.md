# Live responses и маршрутизация реплик

## Два режима на каждое текстовое сообщение

| Режим | Когда | Что делает бот |
|-------|--------|----------------|
| **brief_input** | Факты/пожелания по поездке (даты, бюджет, состав, направление…) | Парсер брифа + **фиксированные** тексты и HTML-бриф, кнопки сценария |
| **conversation** | Вопросы, сомнения, «что написать», помощь с формулировкой | **Полный** ответ live LLM; при явных фактах в реплике — опционально дозапись в бриф |
| **mixed** | Вопрос + факты в одном сообщении | Короткий live (до 500 символов) + бриф в **одном** ответе |

Классификация: `bot/src/message_intent.py` (правила; при спорных случаях — LLM, если включён `USE_LLM_LIVE_RESPONSES`).

Контекст диалога: последние 6 реплик в FSM (`dialog_history`), `dialog_summary` и `last_bot_message` в промпте; `typing` перед LLM.

## Где применяется

- организатор: `organizer_dump`, `organizer_clarify` → `route_organizer_text_message`;
- участник: `participant_contribute` → `route_participant_text_message`;
- recovery в `text_fallback_handler` — та же логика intent.

## Live LLM

| Файл | Роль в API |
|------|------------|
| `live_response_system_prompt.md` | **system** — правила, тон, JSON; режим `conversation` |
| `live_response_user_prompt_template.md` | **user** — данные (бриф, missing, сообщение) |

На шагах **brief_input** live **не вызывается** — только статические строки (`STATIC_*` в `main.py`).

На шаге **conversation** `assistant_text` — **весь** ответ пользователю (не одна строка-интро).

## Включение

```text
USE_LLM_LIVE_RESPONSES=true
LLM_API_KEY=sk-...
LLM_LIVE_MODEL=gpt-4o-mini
```

## Диагностика (Railway logs)

При старте: `Runtime flags: live_responses=True ...`

На сообщение:
- `Organizer message intent=brief_input|conversation` / `Participant message intent=...`
- `Live response from LLM` — conversation с LLM;
- `Live response using fallback` — LLM выключен или ошибка.

## Не путать с парсингом брифа

| Переменная | Задача |
|------------|--------|
| `PARSER_MODE` (`role_llm` рекомендуется) | Структура полей брифа — см. `PARSING_SPEC.md` |
| `USE_LLM_LIVE_RESPONSES` | Живой диалог (conversation) + tie-break классификатора |

Для «Греция / климат / август» нужен **парсер брифа** (`PARSER_MODE`), не live response.
