#!/usr/bin/env python3
"""
Сборка PDF из Предложение_аудит_Travel_Lifestyle_FO.md.
Стиль: белый фон, чёрный текст, выразительная иерархия заголовков.
Шрифт: Styrene ALC Light (если найден в assets/fonts или системных каталогах), иначе Arial Unicode.
"""
from __future__ import annotations

import inspect
import os
import re
import sys
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import TextEmphasis
from fpdf.fonts import FontFace


ROOT = Path(__file__).resolve().parent
MD_PATH = ROOT / "Предложение_аудит_Travel_Lifestyle_FO.md"
OUT_PATH = ROOT / "Предложение_аудит_Travel_Lifestyle_FO.pdf"

FALLBACK_FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]


def find_styrene_light() -> str | None:
    roots = [
        ROOT / "assets" / "fonts",
        Path.home() / "Library" / "Fonts",
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts/Supplemental"),
    ]
    for base in roots:
        if not base.is_dir():
            continue
        try:
            for f in base.rglob("*"):
                if f.suffix.lower() not in (".otf", ".ttf"):
                    continue
                n = f.name.lower()
                if "styrene" in n and "alc" in n and "light" in n:
                    return str(f)
        except OSError:
            continue
    return None


def find_font() -> str:
    sty = find_styrene_light()
    if sty:
        print(f"PDF: используется Styrene ALC Light — {sty}", file=sys.stderr)
        return sty
    for p in FALLBACK_FONT_PATHS:
        if os.path.isfile(p):
            print(
                f"PDF: Styrene ALC Light не найден, используется запасной шрифт — {p}",
                file=sys.stderr,
            )
            return p
    sys.stderr.write(
        "Не найден шрифт: положите StyreneALC-Light.otf в assets/fonts/ "
        "или установите Arial Unicode.ttf.\n"
    )
    sys.exit(1)


def strip_md_bold(s: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", s)


class ProposalPDF(FPDF):
    def __init__(self, font_path: str) -> None:
        super().__init__(unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=18)
        self.font_path = font_path
        self.add_font("DocFont", "", font_path)
        self.set_margins(18, 18, 18)

    def _render_footer(self) -> None:
        # fpdf вызывает _render_footer из add_page (колонтитул предыдущих страниц)
        # и из output() (финальный колонтитул последней страницы). Последний пропускаем.
        caller = inspect.currentframe().f_back.f_code.co_name
        if caller == "output":
            return
        super()._render_footer()

    def header(self) -> None:
        self.set_fill_color(255, 255, 255)
        self.rect(0, 0, self.w, self.h, "F")
        self.set_fill_color(13, 13, 13)
        self.rect(0, 0, self.w, 1.0, "F")

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("DocFont", size=8)
        self.set_text_color(110, 110, 115)
        self.cell(0, 4, f"Стр. {self.page_no()}", align="C")

    def body_text(self, size: float = 10.5) -> None:
        self.set_font("DocFont", size=size)
        self.set_text_color(13, 13, 13)

    def muted_text(self, size: float = 9.5) -> None:
        self.set_font("DocFont", size=size)
        self.set_text_color(92, 92, 92)

    def h1(self, text: str) -> None:
        self.ln(5)
        self.set_font("DocFont", size=20)
        self.set_text_color(13, 13, 13)
        self.multi_cell(0, 9, strip_md_bold(text))
        self.ln(3)
        self.set_draw_color(13, 13, 13)
        self.set_line_width(0.9)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(5)
        self.body_text()

    def h2(self, text: str) -> None:
        self.ln(7)
        self.set_font("DocFont", size=9.2)
        self.set_text_color(13, 13, 13)
        self.multi_cell(0, 5, strip_md_bold(text).upper())
        y = self.get_y()
        self.set_fill_color(13, 13, 13)
        self.rect(self.l_margin, y, 42, 1.4, "F")
        self.ln(5)
        self.body_text()

    def h3(self, text: str) -> None:
        self.ln(5)
        self.set_font("DocFont", size=12.5)
        self.set_text_color(13, 13, 13)
        self.multi_cell(0, 6.2, strip_md_bold(text))
        self.ln(2)
        self.body_text()

    def paragraph(self, text: str) -> None:
        t = strip_md_bold(text.strip())
        if not t:
            return
        self.body_text()
        self.multi_cell(0, 5.2, t)
        self.ln(1)

    def bullet(self, text: str) -> None:
        t = strip_md_bold(text.strip())
        self.body_text()
        self.set_x(self.l_margin + 2)
        self.multi_cell(self.epw - 2, 5.2, "•  " + t)
        self.ln(0.5)

    def rule(self) -> None:
        self.ln(3)
        self.set_draw_color(224, 224, 224)
        self.set_line_width(0.25)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def emit_table(self, rows: list[list[str]]) -> None:
        if not rows:
            return
        self.ln(2)
        w = self.epw
        c0 = w * 0.28
        c1 = w - c0
        self.set_text_color(13, 13, 13)
        with self.table(
            borders_layout="MINIMAL",
            text_align=("LEFT", "LEFT"),
            line_height=self.font_size * 1.25,
            col_widths=(c0, c1),
            gutter_width=2,
            headings_style=FontFace(
                emphasis=TextEmphasis.NONE,
                color=(13, 13, 13),
                fill_color=(243, 243, 244),
            ),
        ) as table:
            for row_cells in rows:
                tr = table.row()
                for cell in row_cells:
                    tr.cell(strip_md_bold(cell))
        self.body_text()
        self.ln(2)


def parse_table_row(line: str) -> list[str]:
    raw = line.strip()
    if raw.startswith("|"):
        raw = raw[1:]
    if raw.endswith("|"):
        raw = raw[:-1]
    return [c.strip() for c in raw.split("|")]


def is_table_sep(cells: list[str]) -> bool:
    return all(re.match(r"^[-:\s]+$", c) for c in cells if c) or not any(cells)


def render_md(md_text: str, pdf: ProposalPDF) -> None:
    lines = md_text.splitlines()
    i = 0
    first_h1 = True
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped == "---":
            pdf.rule()
            i += 1
            continue

        if stripped.startswith("|"):
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = parse_table_row(lines[i])
                if not is_table_sep(cells):
                    rows.append(cells)
                i += 1
            pdf.emit_table(rows)
            continue

        if stripped.startswith("# "):
            t = stripped[2:].strip()
            if first_h1:
                pdf.add_page()
                pdf.h1(t)
                first_h1 = False
            else:
                pdf.h1(t)
            i += 1
            continue

        if stripped.startswith("## "):
            pdf.h2(stripped[3:].strip())
            i += 1
            continue

        if stripped.startswith("### "):
            pdf.h3(stripped[4:].strip())
            i += 1
            continue

        if stripped.startswith("- "):
            pdf.bullet(stripped[2:])
            i += 1
            continue

        if re.match(r"^\d+\.\s", stripped):
            pdf.body_text()
            pdf.multi_cell(0, 5.2, strip_md_bold(stripped))
            pdf.ln(1)
            i += 1
            continue

        if stripped.startswith("*") and stripped.endswith("*"):
            pdf.muted_text(9)
            pdf.multi_cell(0, 5, strip_md_bold(stripped.strip("*").strip()))
            pdf.ln(2)
            pdf.body_text()
            i += 1
            continue

        # абзац: склеить последовательные непустые строки
        buf = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(("#", "-", "|", "---")):
            nxt = lines[i].strip()
            if re.match(r"^\d+\.\s", nxt):
                break
            buf.append(nxt)
            i += 1
        pdf.paragraph(" ".join(buf))


def main() -> None:
    font = find_font()
    if not MD_PATH.is_file():
        sys.stderr.write(f"Нет файла: {MD_PATH}\n")
        sys.exit(1)
    md = MD_PATH.read_text(encoding="utf-8")
    pdf = ProposalPDF(font)
    render_md(md, pdf)
    pdf.output(str(OUT_PATH))
    print(f"PDF сохранён: {OUT_PATH}")


if __name__ == "__main__":
    main()
