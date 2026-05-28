# Live responses — как устроено

## Два файла — не конфликт, а пара

| Файл | Роль в API |
|------|------------|
| `live_response_system_prompt.md` | **system** — правила, тон, JSON-формат |
| `live_response_user_prompt_template.md` | **user** — подставленные данные (бриф, missing, сообщение) |

Это стандартная схема OpenAI: инструкции в system, факты в user. Раньше оба файла повторяли правила — модель путалась; user-шаблон упрощён до данных.

## Где в чате виден результат

Live LLM **не заменяет весь ответ**. Меняется только **короткая строка** перед/рядом с HTML-брифом:

- после первого ввода организатора;
- при уточнении брифа;
- intro у участника после пожеланий.

Меню, кнопки, приглашение, sharing — **статические** тексты.

## Включение

```text
USE_LLM_LIVE_RESPONSES=true
LLM_API_KEY=sk-...
LLM_LIVE_MODEL=gpt-4o-mini
```

## Диагностика (Railway logs)

При старте: `Runtime flags: live_responses=True ... llm_api_key=set`

При ответе:
- `Live response from LLM` — работает;
- `Live response using fallback (source=fallback_*)` — LLM не использован;
- `invalid_json preview=...` — модель вернула не JSON (после правки парсера реже).

## Не путать с парсингом брифа

| Флаг | Задача |
|------|--------|
| `USE_LLM_BRIEF_PARSER` | Структура полей брифа |
| `USE_LLM_LIVE_RESPONSES` | Живая формулировка 1–2 предложений |

Для «Греция / климат / август» нужен **brief parser** (или rule-based), не live response.
