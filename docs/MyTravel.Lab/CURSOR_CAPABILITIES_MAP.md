# MyTravel.Lab — skills и субагенты в Cursor

Как мы используем **Cursor** для развития платформы: не часть продукта для конечного пользователя, а **операционная система** команды (исследования, контент, код, будущие дайджесты).

См. общую карту: [PLATFORM_VISION.md](./PLATFORM_VISION.md).

---

## Где что лежит

| Тип | Путь в проекте | Путь личное (все проекты) |
|-----|----------------|---------------------------|
| **Skill** | `.cursor/skills/<name>/SKILL.md` | `~/.cursor/skills/<name>/SKILL.md` |
| **Субагент** | `.cursor/agents/<name>.md` | `~/.cursor/agents/<name>.md` |
| **Правила** | `.cursor/rules/*.mdc` | — |
| Устаревшие копии промптов | `docs/agents/*.md` → указатели на skills | — |

**Не путать:** `~/.cursor/skills-cursor/` — встроенные skills Cursor, не редактировать.

---

## Skill vs субагент — когда что

| Задача | Лучше |
|--------|--------|
| Повторяемый формат (дайджест, пост, чеклист PR) | **Skill** |
| Долгий обход 10+ URL / большой ресёрч | **Skill** + опционально **субагент** (изоляция контекста) |
| Ревью кода, деплой, explore репо | встроенные subagent types / rules |
| «Всегда так пиши контент» | **Skill** с явным `@` или описанием в `description` |

---

## Реестр capabilities

### Есть в репозитории (project skills)

| Skill | Назначение | Вызов |
|-------|------------|--------|
| [marketing-content-creator](../../.cursor/skills/marketing-content-creator/SKILL.md) | Стратегия и копирайт: журнал, соцсети, кампании, repurposing | `@marketing-content-creator` или задача про контент |
| [product-trend-researcher](../../.cursor/skills/product-trend-researcher/SKILL.md) | Рынок, тренды, конкуренты, TAM, сигналы | `@product-trend-researcher` или задача про рынок |

### Планируется (под платформу)

| ID | Назначение | Формат | Зависимости от основателя |
|----|------------|--------|---------------------------|
| `content-curation` | Подборка статей по whitelist сайтов и темам | Skill (+ опционально `sources.yaml`) | Список URL/тем, период, язык |
| `design-system-author` | Foundations, токены, гайды по каналам | Skill + `docs/design-system/` | Референсы, палитра, каналы v1 |
| `brief-ux-copy` | Согласованность текстов бота с BOT_PERSONA | Rule уже частично; skill при росте сценариев | UX-апрув в `.cursor/rules/ux-ui-approval.mdc` |
| `b2b-cx-auditor` | Разбор CX-скриптов агентства по B2B PRD | Skill | Примеры переписок, регламент |

### Субагенты (планируется)

Папка `.cursor/agents/` пока **не создана**. Кандидаты:

| Субагент | Когда делегировать |
|----------|-------------------|
| `research-scout` | Много источников за один запрос (дайджест недели) |
| `competitive-scan` | Обход конкурентов из `Анализ_рынка_и_конкурентов.md` |

Создание: по [create-subagent](https://cursor.com) / skill `create-subagent` во встроенных skills.

### Встроенные (Cursor), не в репо

`babysit`, `canvas`, `explore`, `create-skill`, … — из `~/.cursor/skills-cursor/`.

---

## Связь capabilities с поверхностями платформы

| Поверхность платформы | Skills / агенты |
|----------------------|-----------------|
| Журнал + соцсети | `marketing-content-creator`, будущий `content-curation` |
| Стратегия / roadmap | `product-trend-researcher`, этот документ |
| Telegram-бот | `.cursor/rules/telegram-bot.mdc`, `vibe-core`, код в `bot/` |
| B2B | `product-trend-researcher`, будущий `b2b-cx-auditor`, `docs/B2B bot agencies/` |
| Design system | будущий `design-system-author` |

---

## Как добавить новый skill (чеклист)

1. Создать `.cursor/skills/<kebab-name>/SKILL.md`.
2. Frontmatter: `name` = имя папки, `description` — что + когда (третье лицо).
3. При необходимости: `reference.md`, `sources.yaml`, скрипт в `scripts/`.
4. Указатель в `docs/agents/` только если нужна ссылка из старых мест.
5. Строка в таблице **Реестр** выше.
6. Reload Window в Cursor → проверить Settings → Skills.

---

## История изменений

| Дата | Изменение |
|------|-----------|
| 2026-06-04 | Первый реестр; vision в PLATFORM_VISION.md |
