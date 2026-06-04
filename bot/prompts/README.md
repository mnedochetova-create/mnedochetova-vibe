# Промпты бота — индекс

| Файл | Когда | Мультимодальный транспорт |
|------|--------|---------------------------|
| `brief_parser_organizer_system_prompt.md` | `PARSER_MODE=role_llm`, организатор | § «Передвижение (мультимодально)» |
| `brief_parser_participant_system_prompt.md` | вклад участника | § «Передвижение (мультимодально)» |
| `brief_merger_system_prompt.md` | после вклада участника | § расхождения по режимам, `transport_mode_difference` |
| `live_response_system_prompt.md` | живой диалог | не навязывать перелёт; приоритет missing_fields |
| `corner_guidance_system_prompt.md` | corner / без поездки | вводные: как едете, не только «куда» |
| `trip_proposal_system_prompt.md` | post-brief, `TRIP_PROPOSALS_LLM_ENABLED` | `modes_present`, `movement.mode` по сегментам |
| `brief_parser_organizer_user_prompt_template.md` | user для LLM-парсера организатора | `transport_context_json` из брифа |
| `brief_parser_participant_user_prompt_template.md` | user для парсера участника | база передвижения организатора |
| `brief_merger_user_prompt_template.md` | user для merger | JSON + напоминание про режимы |
| `live_response_user_prompt_template.md` | шаблон user для live | контекст из main (бриф с ground_notes) |
| `corner_guidance_user_prompt_template.md` | шаблон user для corner | `trips_json` / brief как есть |

Справочник режимов: `docs/Family travel bot/TRIP_TRANSPORT_MODEL.md`.

Спека: `docs/Family travel bot/PARSING_SPEC.md`, live: `docs/Family travel bot/LIVE_RESPONSE.md`, поездка из брифа: `TRIP_FROM_BRIEF_SPEC.md`, `TRIP_EXPERIENCE_ARCHITECTURE.md`.
