#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_HTML = ROOT / "Правый_ТБС_психосоматика_и_исповедь.html"
DUP_HTML = ROOT / "Правый_ТБС_психосоматика_и_исповедь_дубль.html"
OUT_PDF = ROOT / "Правый_ТБС_психосоматика_и_исповедь.pdf"

_FOOTER_HTML = (
    '<div style="width:100%;font-size:9px;line-height:1.2;font-family:system-ui,-apple-system,Segoe UI,sans-serif;'
    'color:#555;text-align:center;padding:4px 0 0;">Стр.&nbsp;<span class="pageNumber"></span>'
    '&nbsp;/&nbsp;<span class="totalPages"></span></div>'
)


def main() -> None:
    if not SRC_HTML.is_file():
        sys.stderr.write(f"Нет файла: {SRC_HTML}\n")
        sys.exit(1)

    shutil.copyfile(SRC_HTML, DUP_HTML)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.stderr.write(
            "Установите: pip install playwright && python3 -m playwright install chromium\n"
        )
        sys.exit(1)

    url = DUP_HTML.resolve().as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="load", timeout=60_000)
        page.emulate_media(media="print")
        page.pdf(
            path=str(OUT_PDF),
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template="<span></span>",
            footer_template=_FOOTER_HTML,
            margin={"top": "8mm", "right": "8mm", "bottom": "14mm", "left": "8mm"},
        )
        browser.close()

    print(f"PDF: {OUT_PDF} ({OUT_PDF.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main()
