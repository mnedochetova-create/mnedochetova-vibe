# Промпты бота — индекс

| Файл | Когда |
|------|--------|
| `brief_parser_organizer_system_prompt.md` | `PARSER_MODE=role_llm`, сообщение организатора |
| `brief_parser_participant_system_prompt.md` | `PARSER_MODE=role_llm`, вклад участника |
| `brief_merger_system_prompt.md` | `PARSER_MODE=role_llm`, после вклада участника (conflicts / open_questions / сводка; **не** пишет в `event.brief`) |
| `live_response_system_prompt.md` | `USE_LLM_LIVE_RESPONSES` — живой диалог (conversation / mixed / voc_feedback) |
| `live_response_user_prompt_template.md` | шаблон user для live |
| `corner_guidance_system_prompt.md` | corner: ack, help, media, defer, autofill, visibility… |
| `corner_guidance_user_prompt_template.md` | шаблон user для corner |

Спека: `docs/Family travel bot/PARSING_SPEC.md`, live: `docs/Family travel bot/LIVE_RESPONSE.md`.
