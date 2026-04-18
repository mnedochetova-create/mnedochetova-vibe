#!/usr/bin/env python3
"""Сборка стилизованного HTML из Предложение_аудит_Travel_Lifestyle_FO.md (тот же контент, что и PDF)."""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MD_PATH = ROOT / "Предложение_аудит_Travel_Lifestyle_FO.md"
OUT_PATH = ROOT / "Предложение_аудит_Travel_Lifestyle_FO.html"


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def inline_bold(s: str) -> str:
    parts = re.split(r"(\*\*.+?\*\*)", s)
    buf: list[str] = []
    for part in parts:
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            buf.append("<strong>" + esc(part[2:-2]) + "</strong>")
        else:
            buf.append(esc(part))
    return "".join(buf)


def md_to_html_body(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    in_ul = False
    in_ol = False

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    while i < len(lines):
        raw = lines[i].rstrip()
        s = raw.strip()
        if not s:
            close_lists()
            i += 1
            continue

        if s == "---":
            close_lists()
            out.append("<hr />")
            i += 1
            continue

        if s.startswith("|"):
            close_lists()
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                sep = all(re.match(r"^[-:\s]+$", c) for c in cells if c)
                if not sep:
                    rows.append(cells)
                i += 1
            if rows:
                out.append('<table><thead><tr>')
                for c in rows[0]:
                    out.append(f"<th>{inline_bold(c)}</th>")
                out.append("</tr></thead><tbody>")
                for r in rows[1:]:
                    out.append("<tr>")
                    for c in r:
                        out.append(f"<td>{inline_bold(c)}</td>")
                    out.append("</tr>")
                out.append("</tbody></table>")
            continue

        if s.startswith("# "):
            close_lists()
            out.append(f"<h1>{inline_bold(s[2:])}</h1>")
            i += 1
            continue
        if s.startswith("## "):
            close_lists()
            out.append(f"<h2>{inline_bold(s[3:])}</h2>")
            i += 1
            continue
        if s.startswith("### "):
            close_lists()
            out.append(f"<h3>{inline_bold(s[4:])}</h3>")
            i += 1
            continue

        if s.startswith("- "):
            if not in_ul:
                close_lists()
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline_bold(s[2:])}</li>")
            i += 1
            continue

        if re.match(r"^\d+\.\s", s):
            if not in_ol:
                close_lists()
                out.append("<ol>")
                in_ol = True
            item = re.sub(r"^\d+\.\s", "", s)
            out.append(f"<li>{inline_bold(item)}</li>")
            i += 1
            continue

        if s.startswith("*") and s.endswith("*") and len(s) > 2:
            close_lists()
            out.append(f'<p class="footnote">{inline_bold(s.strip("*").strip())}</p>')
            i += 1
            continue

        close_lists()
        buf = [s]
        i += 1
        while i < len(lines) and lines[i].strip():
            nxt = lines[i].strip()
            if nxt.startswith(("#", "-", "|", "---")) or re.match(r"^\d+\.\s", nxt):
                break
            buf.append(nxt)
            i += 1
        out.append(f"<p>{inline_bold(' '.join(buf))}</p>")

    close_lists()
    return "\n".join(out)


CSS = r"""    /* Styrene ALC Light: локальный файл (лицензия у правообладателя) или системная установка */
    @font-face {
      font-family: "Styrene ALC";
      src:
        local("Styrene ALC Light"),
        local("StyreneALC-Light"),
        url("./assets/fonts/StyreneALC-Light.woff2") format("woff2"),
        url("./assets/fonts/StyreneALC-Light.otf") format("opentype"),
        url("./assets/fonts/StyreneALC-Light.ttf") format("truetype");
      font-weight: 300;
      font-style: normal;
      font-display: swap;
    }
    :root {
      --bg: #ffffff;
      --bg-subtle: #fafafa;
      --text: #0d0d0d;
      --muted: #5c5c5c;
      --rule: #0d0d0d;
      --line: #e0e0e0;
      --table-head: #f3f3f4;
      --maxw: 680px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Styrene ALC", "Styrene ALC Web", -apple-system, BlinkMacSystemFont,
        "Helvetica Neue", "Segoe UI", Roboto, Arial, sans-serif;
      font-weight: 300;
      background: var(--bg);
      color: var(--text);
      line-height: 1.62;
      font-size: 16px;
      -webkit-font-smoothing: antialiased;
    }
    .hero {
      position: relative;
      padding: 3rem 1.5rem 2.25rem;
      border-bottom: 3px solid var(--rule);
      background: var(--bg-subtle);
    }
    .hero-inner { position: relative; max-width: var(--maxw); margin: 0 auto; }
    .kicker {
      font-family: "Styrene ALC", "Helvetica Neue", Arial, sans-serif;
      font-size: 0.68rem;
      font-weight: 600;
      letter-spacing: 0.22em;
      text-transform: uppercase;
      color: var(--muted);
      margin: 0 0 1.1rem;
    }
    .kicker span { color: var(--text); margin-right: 0.35em; }
    .hero-title {
      margin: 0;
      font-family: "Styrene ALC", "Helvetica Neue", Arial, sans-serif;
      font-size: clamp(2rem, 5vw, 2.75rem);
      font-weight: 600;
      letter-spacing: -0.035em;
      line-height: 1.08;
      color: var(--text);
      max-width: 28ch;
    }
    main { max-width: var(--maxw); margin: 0 auto; padding: 2.5rem 1.5rem 4rem; }
    main h1 {
      margin: 2rem 0 1rem;
      font-family: "Styrene ALC", "Helvetica Neue", Arial, sans-serif;
      font-size: clamp(1.65rem, 3.5vw, 2rem);
      font-weight: 600;
      letter-spacing: -0.03em;
      line-height: 1.12;
      color: var(--text);
    }
    h2 {
      margin: 2.75rem 0 0.85rem;
      font-family: "Styrene ALC", "Helvetica Neue", Arial, sans-serif;
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: var(--text);
      break-after: avoid;
      page-break-after: avoid;
    }
    h2::after {
      content: "";
      display: block;
      width: 100%;
      max-width: 4.5rem;
      height: 4px;
      background: var(--rule);
      margin-top: 0.75rem;
    }
    h3 {
      margin: 2rem 0 0.6rem;
      font-family: "Styrene ALC", "Helvetica Neue", Arial, sans-serif;
      font-size: 1.2rem;
      font-weight: 600;
      letter-spacing: -0.02em;
      line-height: 1.25;
      color: var(--text);
      break-after: avoid;
      page-break-after: avoid;
    }
    /* не отрывать первый блок после подзаголовка от самого подзаголовка (печать/PDF) */
    h2 + p, h2 + ul, h2 + ol, h2 + table,
    h3 + p, h3 + ul, h3 + ol, h3 + table {
      break-before: avoid;
      page-break-before: avoid;
    }
    p { margin: 0 0 1rem; color: var(--text); font-weight: 300; }
    strong { font-weight: 600; }
    ul, ol { margin: 0 0 1.1rem; padding-left: 1.25rem; color: var(--text); font-weight: 300; }
    li { margin-bottom: 0.4rem; }
    hr {
      border: none;
      height: 1px;
      background: var(--line);
      margin: 2.25rem 0;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
      margin: 1.25rem 0 1.75rem;
      background: var(--bg);
      border: 1px solid var(--line);
    }
    th, td {
      padding: 0.7rem 0.85rem;
      text-align: left;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }
    th {
      font-family: "Styrene ALC", "Helvetica Neue", Arial, sans-serif;
      background: var(--table-head);
      color: var(--text);
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.68rem;
    }
    td { font-weight: 300; }
    tr:last-child td { border-bottom: none; }
    .footnote {
      margin-top: 2.5rem;
      padding-top: 1.25rem;
      border-top: 1px solid var(--line);
      font-size: 0.85rem;
      color: var(--muted);
      font-style: italic;
      font-weight: 300;
    }
    @media print {
      body { font-size: 11pt; }
      .hero { background: #fff; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      th { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    }
"""


def build() -> None:
    if not MD_PATH.is_file():
        sys.stderr.write(f"Нет файла: {MD_PATH}\n")
        sys.exit(1)
    md = MD_PATH.read_text(encoding="utf-8")
    body = md_to_html_body(md)
    # Первый # вынести в hero (если есть)
    first_h1 = re.search(r"<h1>(.+?)</h1>", body, re.S)
    hero_title = "Предложение"
    rest = body
    if first_h1:
        hero_title = re.sub(r"<[^>]+>", "", first_h1.group(1))
        rest = body[first_h1.end() :].lstrip()

    out = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(hero_title)}</title>
  <style>
{CSS}
  </style>
</head>
<body>
  <header class="hero">
    <div class="hero-inner">
      <p class="kicker"><span>●</span> Family office · Travel &amp; Lifestyle</p>
      <h1 class="hero-title">{esc(hero_title)}</h1>
    </div>
  </header>
  <main>
{rest}
  </main>
</body>
</html>
"""
    OUT_PATH.write_text(out, encoding="utf-8")
    print(f"HTML сохранён: {OUT_PATH}")


if __name__ == "__main__":
    build()
