# Telegram Bot Project

Базовая структура проекта для разработки Telegram-бота.

## Структура

- `bot/` — код и техническая часть разработки
- `docs/` — продуктовая документация, требования и спецификация
- `docs/B2B bot agencies/` — PRD/SPEC B2B‑бота для агентств и отелей
- `docs/Family travel bot/` — PRD/SPEC семейного travel‑бота‑ассистента
- `docs/agents/` — полезные агент-профили для исследования и стратегии
- `.cursor/rules/` — правила Cursor для этого репозитория (доки, бот, git, UX)

## Быстрый старт

1. Заполни документы в `docs/`:
   - `PRD.md` (продуктовое описание)
   - `SPEC.md` (техническая спецификация)
2. (Опционально) Используй готовые агент-профили из `docs/agents/`:
   - `docs/agents/product-trend-researcher.md` — тренды и рынок
   - `docs/agents/marketing-content-creator.md` — маркетинговый контент и стратегия
3. Выбери стек для бота и создай рабочий код внутри `bot/`.
4. Добавь запуск, тесты и CI по мере развития проекта.

## Автоматические релизы (Release Please)

Релизы собирает workflow [`.github/workflows/release-please.yml`](.github/workflows/release-please.yml): открывается PR с версией и `CHANGELOG`, после мержа PR создаётся GitHub Release.

Чтобы `GITHUB_TOKEN` мог **создавать PR** (иначе в логах: `not permitted to create or approve pull requests`):

1. **Через API (с вашей машины):** создайте [PAT](https://github.com/settings/tokens) (classic: scope `repo`, либо fine-grained: *Administration* — Read and write на этом репозитории), затем:
   ```bash
   export GITHUB_TOKEN=...   # ваш PAT, не коммитьте в репозиторий
   ./scripts/configure-github-actions-release-automation.sh
   ```
2. **Через веб:** [Settings → Actions → General](https://github.com/mnedochetova-create/mnedochetova-vibe/settings/actions) → блок **Workflow permissions**:
   - включите **Read and write permissions**;
   - включите **Allow GitHub Actions to create and approve pull requests**.  
   Если пункт с чекбоксом недоступен (серый), сначала включите то же на уровне [организации](https://docs.github.com/en/organizations/managing-organization-settings/disabling-or-limiting-github-actions-for-your-organization) или enterprise.

Альтернатива без смены настроек репозитория: секрет **`RELEASE_PLEASE_TOKEN`** (PAT с правами на содержимое репо и pull requests) — см. комментарий в workflow.

После смены настроек запустите workflow вручную: **Actions → Release Please → Run workflow**.

