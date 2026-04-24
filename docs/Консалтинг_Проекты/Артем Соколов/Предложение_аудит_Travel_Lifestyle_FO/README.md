# Предложение: аудит Travel & Lifestyle в FO

Все файлы по этому предложению лежат в этой папке.

## Файлы

| Файл | Назначение |
|------|------------|
| [Предложение_аудит_Travel_Lifestyle_FO.md](./Предложение_аудит_Travel_Lifestyle_FO.md) | **Финальное предложение / состав работ** (без указания стоимости) |
| [Предложение_аудит_Travel_Lifestyle_FO.html](./Предложение_аудит_Travel_Lifestyle_FO.html) | Версия для браузера (светлая вёрстка, Styrene ALC при наличии; из `.md`) |
| [Предложение_аудит_Travel_Lifestyle_FO_дубль.html](./Предложение_аудит_Travel_Lifestyle_FO_дубль.html) | Копия HTML перед сборкой PDF (перезаписывается скриптом) |
| [Предложение_аудит_Travel_Lifestyle_FO.pdf](./Предложение_аудит_Travel_Lifestyle_FO.pdf) | PDF из HTML (Playwright/Chromium), колонтитул «Стр. N / M» |
| [Аудит_Travel_Lifestyle_2недели.md](./Аудит_Travel_Lifestyle_2недели.md) | Рабочие заметки: разбор ТЗ, scope, ориентиры по стоимости |
| `build_proposal_html.py` | Сборка HTML из `.md` |
| `build_proposal_pdf_from_html.py` | Дубль HTML → PDF (рекомендуется) |
| `build_proposal_pdf.py` | Упрощённый PDF из `.md` через fpdf2 (без Playwright) |
| [assets/fonts/README.txt](./assets/fonts/README.txt) | Куда положить Styrene ALC Light |

## Пересборка HTML и PDF

Из **этой** папки:

```bash
cd docs/Family\ office/Предложение_аудит_Travel_Lifestyle_FO
python3 build_proposal_html.py
python3 build_proposal_pdf_from_html.py
```

Нужны: `pip install playwright` и `python3 -m playwright install chromium`.

Шрифт **Styrene ALC Light**: `@font-face` в HTML и каталог `assets/fonts/` (см. README в `assets/fonts/`).

## Контекст

Запрос: **~2 недели**, аудит организации **путешествий и lifestyle** в family office UHNW; на выходе — описание процессов, работы команд и предложение по оптимизации, автоматизации и структуре команд.

Исходное ТЗ во внешнем файле: `Состав работ аудита family office.docx` (логика перенесена в основной `.md` выше).
