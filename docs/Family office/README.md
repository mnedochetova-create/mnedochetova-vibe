# Family office — проекты

Папка для материалов по консалтингу и аудиту family office (не путать с продуктом «Family travel bot» в `docs/Family travel bot/`).

## Текущие артефакты

| Файл | Назначение |
|------|----------------|
| [Предложение_аудит_Travel_Lifestyle_FO.md](./Предложение_аудит_Travel_Lifestyle_FO.md) | **Финальное предложение / состав работ** (без указания стоимости) |
| [Предложение_аудит_Travel_Lifestyle_FO.html](./Предложение_аудит_Travel_Lifestyle_FO.html) | Версия для браузера (светлая вёрстка, Styrene ALC при наличии; пересобирается из `.md`) |
| [Предложение_аудит_Travel_Lifestyle_FO_дубль.html](./Предложение_аудит_Travel_Lifestyle_FO_дубль.html) | Копия HTML перед сборкой PDF (перезаписывается скриптом) |
| [Предложение_аудит_Travel_Lifestyle_FO.pdf](./Предложение_аудит_Travel_Lifestyle_FO.pdf) | PDF из HTML через **Playwright/Chromium** (верстка как в браузере) |
| [Аудит_Travel_Lifestyle_2недели.md](./Аудит_Travel_Lifestyle_2недели.md) | Рабочие заметки: разбор ТЗ, scope, ориентиры по стоимости |

**Пересборка HTML и PDF** (из каталога `docs/Family office/`):

```bash
python3 build_proposal_html.py
python3 build_proposal_pdf_from_html.py
```

`build_proposal_pdf_from_html.py` копирует HTML в `Предложение_аудит_Travel_Lifestyle_FO_дубль.html` и печатает PDF с `print_background`, колонтитулом **«Стр. N / M»** и полями под нижний колонтитул (нужны: `pip install playwright`, затем `python3 -m playwright install chromium`).

Альтернатива без Playwright: `python3 build_proposal_pdf.py` (fpdf2, упрощённая вёрстка).

Шрифт **Styrene ALC Light**: в HTML — через `@font-face` и локальные файлы в `assets/fonts/`; в браузерном PDF подхватится, если шрифт доступен по URL файла.

## Контекст (кратко)

Запрос: **~2 недели**, аудит организации **путешествий и lifestyle** в family office UHNW; на выходе — описание процессов, работы команд и предложение по оптимизации, автоматизации и структуре команд.

Исходное ТЗ зафиксировано во внешнем файле: `Состав работ аудита family office.docx` (рабочая копия логики перенесена в markdown-файл выше).
