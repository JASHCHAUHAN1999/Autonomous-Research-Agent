# app/export/exporter.py
import os
from io import BytesIO

import markdown
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xhtml2pdf import pisa


def to_markdown(run: dict) -> str:
    """Compose a standalone Markdown document from a run dict.

    Layout:
        # <query>
        *Model: <model> — Generated: <created_at>*

        <report_markdown>

        ## Sources
        - [<title>](<url>)
        ...
    """
    query = run.get("query") or "Research Report"
    model = run.get("model") or "unknown"
    created_at = run.get("created_at") or ""
    report = run.get("report_markdown") or ""
    sources = run.get("sources") or []

    lines: list[str] = []
    lines.append(f"# {query}")
    lines.append("")
    lines.append(f"*Model: {model} — Generated: {created_at}*")
    lines.append("")
    lines.append(report.strip())
    lines.append("")
    lines.append("## Sources")
    lines.append("")
    if sources:
        for src in sources:
            title = src.get("title") or src.get("url") or "Untitled"
            url = src.get("url") or ""
            lines.append(f"- [{title}]({url})")
    else:
        lines.append("_No sources recorded._")
    lines.append("")

    return "\n".join(lines)


# --- PDF rendering -----------------------------------------------------------

# Characters absent from the PDF base-14 (WinAnsi) fonts that render as black
# boxes ("tofu"). Mapped to safe equivalents so a report never shows boxes even
# on the Helvetica fallback path.
_CHAR_FIX = {
    "‑": "-",   # non-breaking hyphen (culprit in "Solid-State", "2024-2025")
    "‐": "-",   # hyphen
    "‒": "-",   # figure dash
    "−": "-",   # minus sign
    " ": " ",   # thin space
    " ": " ",   # hair space
    " ": " ",   # narrow no-break space
    " ": " ",   # punctuation space
    "​": "",    # zero-width space
    "﻿": "",    # BOM / zero-width no-break space
}

# Unicode TTF font sets tried in order: (regular, bold, italic, bold-italic).
# The first set whose regular file exists is embedded so all glyphs render and
# the document looks nicer than the base-14 Helvetica.
_FONT_SETS = [
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf",
     "C:/Windows/Fonts/segoeuii.ttf", "C:/Windows/Fonts/segoeuiz.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf",
     "C:/Windows/Fonts/ariali.ttf", "C:/Windows/Fonts/arialbi.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf",
     "/Library/Fonts/Arial Italic.ttf", "/Library/Fonts/Arial Bold Italic.ttf"),
]


def _fix_chars(text: str) -> str:
    for bad, good in _CHAR_FIX.items():
        text = text.replace(bad, good)
    return text


def _register_report_font() -> str:
    """Register a Unicode TTF family with reportlab; return its font-family name.

    Registering directly with reportlab (rather than via CSS @font-face) avoids
    xhtml2pdf misreading a Windows ``C:`` path as a URL scheme. Falls back to
    the base-14 ``Helvetica`` (with _fix_chars covering the common gaps) when no
    system font is available, so rendering never crashes.
    """
    for reg, bold, ital, bital in _FONT_SETS:
        if not os.path.isfile(reg):
            continue
        pick = lambda p: p if os.path.isfile(p) else reg  # noqa: E731
        try:
            pdfmetrics.registerFont(TTFont("ReportSans", reg))
            pdfmetrics.registerFont(TTFont("ReportSans-Bold", pick(bold)))
            pdfmetrics.registerFont(TTFont("ReportSans-Italic", pick(ital)))
            pdfmetrics.registerFont(TTFont("ReportSans-BoldItalic", pick(bital)))
            pdfmetrics.registerFontFamily(
                "ReportSans",
                normal="ReportSans",
                bold="ReportSans-Bold",
                italic="ReportSans-Italic",
                boldItalic="ReportSans-BoldItalic",
            )
            return "ReportSans"
        except Exception:
            return "Helvetica"
    return "Helvetica"


_REPORT_FONT = _register_report_font()


def _sources_markdown(sources: list[dict]) -> str:
    if not sources:
        return "_No sources recorded._"
    rows = []
    for src in sources:
        title = src.get("title") or src.get("url") or "Untitled"
        url = src.get("url") or ""
        rows.append(f"- [{title}]({url})")
    return "\n".join(rows)


def to_pdf(run: dict) -> bytes:
    """Render the run to a designed, glyph-complete PDF and return the bytes."""
    query = _fix_chars(run.get("query") or "Research Report")
    model = _fix_chars(run.get("model") or "unknown")
    created_at = _fix_chars(run.get("created_at") or "")
    report = run.get("report_markdown") or ""
    sources = run.get("sources") or []

    body_md = report.strip() + "\n\n## Sources\n\n" + _sources_markdown(sources)
    body_html = _fix_chars(markdown.markdown(body_md, extensions=["extra"]))

    n_sources = len(sources)
    src_word = "source" if n_sources == 1 else "sources"
    font = _REPORT_FONT

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
    @page {{
        size: a4 portrait;
        margin: 1.6cm 1.7cm 2.0cm 1.7cm;
        @frame footer_frame {{
            -pdf-frame-content: footerContent;
            left: 1.7cm; right: 1.7cm; bottom: 1.1cm; height: 0.8cm;
        }}
    }}
    body {{ font-family: "{font}"; font-size: 10.5pt; line-height: 1.5; color: #1f2937; }}

    .header {{
        background-color: #312e81;
        color: #ffffff;
        padding: 16pt 18pt 14pt 18pt;
    }}
    .kicker {{ font-size: 8pt; letter-spacing: 2pt; color: #c7d2fe; margin-bottom: 6pt; }}
    .title {{ font-size: 19pt; font-weight: bold; line-height: 1.25; color: #ffffff; }}
    .accentbar {{ background-color: #6366f1; height: 4pt; margin-bottom: 12pt; }}
    .meta {{ font-size: 8.5pt; color: #6b7280; margin-bottom: 16pt; }}
    .meta b {{ color: #4338ca; }}

    h2 {{
        font-size: 12.5pt; color: #3730a3; font-weight: bold;
        border-bottom: 1pt solid #e5e7eb;
        padding-bottom: 3pt; margin-top: 16pt; margin-bottom: 6pt;
    }}
    h3 {{ font-size: 11pt; color: #374151; margin-top: 10pt; margin-bottom: 4pt; }}
    p {{ margin-top: 0; margin-bottom: 7pt; }}
    ul, ol {{ margin-top: 2pt; margin-bottom: 8pt; }}
    li {{ margin-bottom: 4pt; }}
    strong {{ color: #111827; }}
    em {{ color: #4b5563; }}
    a {{ color: #4f46e5; text-decoration: none; }}

    .sources {{
        background-color: #f8fafc;
        border: 1pt solid #e5e7eb;
        padding: 8pt 12pt 4pt 12pt;
        margin-top: 4pt;
    }}

    #footerContent {{ font-size: 8pt; color: #9ca3af; text-align: center; }}
</style>
</head>
<body>
    <div class="header">
        <div class="kicker">AUTONOMOUS RESEARCH AGENT</div>
        <div class="title">{query}</div>
    </div>
    <div class="accentbar"></div>
    <div class="meta">Model <b>{model}</b> &nbsp;&middot;&nbsp; Generated {created_at} &nbsp;&middot;&nbsp; {n_sources} {src_word}</div>

    {body_html}

    <div id="footerContent">
        Autonomous Research Agent &nbsp;&middot;&nbsp; page <pdf:pagenumber/> of <pdf:pagecount/>
    </div>
</body>
</html>"""

    buffer = BytesIO()
    pisa.CreatePDF(src=html, dest=buffer, encoding="utf-8")
    return buffer.getvalue()
