# Версионирование репозитория

## Источник истины

| Артефакт | Назначение |
|----------|------------|
| [`VERSION`](../VERSION) | Semver релиза монорепо (`MAJOR.MINOR.PATCH`) |
| [`CHANGELOG.md`](../CHANGELOG.md) | История релизов для людей и GitHub Releases |
| [`.release-please-manifest.json`](../.release-please-manifest.json) | Текущая версия для Release Please |
| Git-тег `vX.Y.Z` | Снимок релиза на GitHub |

**Build-строка в боте** (`build: …` в `/start`): читает `VERSION`, если в Railway не задан `BOT_UI_VERSION`.

Код: `bot/src/app_version.py` → `ui_feedback.BOT_UI_VERSION`.

## Semver (упрощённо)

- **PATCH** — исправления без смены сценария для пользователя.
- **MINOR** — новые возможности бота/парсинга, обратно совместимые.
- **MAJOR** — ломающие изменения формата данных, сценария или API событий.

Продуктовый MVP бота живёт в том же номере версии, что и репозиторий (отдельного `bot/VERSION` нет).

## Релизный процесс

1. Коммиты в `main` с [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`…).
2. Workflow [**Release Please**](../.github/workflows/release-please.yml) открывает PR «Release X.Y.Z» с обновлением `VERSION`, `CHANGELOG`, manifest.
3. После merge PR — GitHub Release и тег `vX.Y.Z` (если настроены права Actions, см. [README](../README.md)).

**Ручной релиз** (если Release Please недоступен):

```bash
# VERSION и CHANGELOG уже обновлены
git tag -a v0.4.0 -m "v0.4.0"
git push origin v0.4.0
```

## Деплой (Railway / Docker)

- В образ копируется [`VERSION`](../VERSION) → в runtime подставляется в `build:`.
- **Не задавайте** `BOT_UI_VERSION` в Railway без необходимости — иначе в чате останется старая строка при новом коде. См. [`bot/RAILWAY_PROJECT.md`](../bot/RAILWAY_PROJECT.md).

Проверка после деплоя: `/start` → внизу `build: 0.4.0` (или текущий `VERSION`).

## Что не версионируется отдельно

- Промпты и `bot/data/events.json` — часть того же релиза.
- Документация в `docs/` — в том же CHANGELOG по смыслу, без отдельного номера.

## Текущая версия

См. файл [`VERSION`](../VERSION).
