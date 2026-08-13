"""Renderer for the Fashion Trendz database specification.

Produces a print-ready landscape PDF in the same style as the reference
document: a cover, a numbered table inventory, module sections with column
grids, an ERD, stored procedures, index and partition strategy, a
normalisation report and closing statistics.

Data lives in ``spec.py``. This module only draws it.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

INK = colors.HexColor("#14171F")
MUTED = colors.HexColor("#5B6472")
RULE = colors.HexColor("#C9D0DA")
HEAD_BG = colors.HexColor("#1F2A44")
BAND = colors.HexColor("#EEF1F6")
PK_BG = colors.HexColor("#FFF4CC")
FK_BG = colors.HexColor("#DFF3E3")
UQ_BG = colors.HexColor("#E4ECFB")
PROPOSED = colors.HexColor("#FCE9DC")
ACCENT = colors.HexColor("#B0451E")

PAGE = landscape(A4)
MARGIN = 12 * mm

_styles = getSampleStyleSheet()


def _st(name: str, **kw: Any) -> ParagraphStyle:
    base = dict(fontName="Helvetica", fontSize=7.2, leading=8.6, textColor=INK)
    base.update(kw)
    return ParagraphStyle(name, **base)


S_CELL = _st("cell")
S_CELL_B = _st("cellb", fontName="Helvetica-Bold")
S_MONO = _st("mono", fontName="Courier", fontSize=6.9, leading=8.4)
S_HEAD = _st("head", fontName="Helvetica-Bold", fontSize=7.2, textColor=colors.white)
S_NOTE = _st("note", fontSize=6.6, leading=8.0, textColor=MUTED)
S_H1 = _st("h1", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=HEAD_BG)
S_H2 = _st("h2", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=ACCENT)
S_H3 = _st("h3", fontName="Helvetica-Bold", fontSize=8.6, leading=11)
S_BODY = _st("body", fontSize=7.6, leading=10)
S_TITLE = _st("title", fontName="Helvetica-Bold", fontSize=26, leading=30,
              alignment=TA_CENTER, textColor=HEAD_BG)
S_SUB = _st("sub", fontSize=11, leading=15, alignment=TA_CENTER, textColor=MUTED)
S_ERD = _st("erd", fontName="Courier", fontSize=6.6, leading=8.0)


def P(text: Any, style: ParagraphStyle = S_CELL) -> Paragraph:
    """Return a paragraph, escaping the characters ReportLab treats as markup."""
    s = "" if text is None else str(text)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(s, style)


# ---------------------------------------------------------------------------
# Page furniture
# ---------------------------------------------------------------------------

DOC_TITLE = "FASHION TRENDZ E-COMMERCE PLATFORM — DATABASE SCHEMA"
_section = {"name": ""}


def set_section(name: str) -> None:
    """Set the running header shown at the top of subsequent pages."""
    _section["name"] = name


def _chrome(canvas: Any, doc: Any) -> None:
    """Draw the running header, footer and page number."""
    canvas.saveState()
    w, h = PAGE

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, h - 8 * mm, _section["name"])
    canvas.drawRightString(w - MARGIN, h - 8 * mm, DOC_TITLE)

    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(MARGIN, h - 10 * mm, w - MARGIN, h - 10 * mm)
    canvas.line(MARGIN, 10 * mm, w - MARGIN, 10 * mm)

    canvas.drawString(MARGIN, 6.5 * mm, "Fashion Trendz — Database Design Document")
    canvas.drawCentredString(w / 2, 6.5 * mm, "Confidential — Internal Engineering")
    canvas.drawRightString(w - MARGIN, 6.5 * mm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def _cover_chrome(canvas: Any, doc: Any) -> None:
    """Cover page: rules only, no running header."""
    canvas.saveState()
    w, h = PAGE
    canvas.setStrokeColor(HEAD_BG)
    canvas.setLineWidth(2)
    canvas.rect(MARGIN, MARGIN, w - 2 * MARGIN, h - 2 * MARGIN)
    canvas.restoreState()


def build_document(path: str, story: list[Any]) -> None:
    """Render ``story`` to ``path``."""
    doc = BaseDocTemplate(
        path,
        pagesize=PAGE,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=14 * mm,
        bottomMargin=13 * mm,
        title="Fashion Trendz Database Schema",
        author="Lead Database Architect",
        subject="Database Design Document",
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body",
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[frame], onPage=_cover_chrome),
        PageTemplate(id="body", frames=[frame], onPage=_chrome),
    ])
    doc.build(story)


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

USABLE = PAGE[0] - 2 * MARGIN


def grid(header: list[str], rows: list[list[Any]], widths: list[float],
         styles: list[ParagraphStyle] | None = None,
         shade: dict[int, colors.Color] | None = None,
         repeat: int = 1) -> Table:
    """Return a formatted data grid.

    ``shade`` maps a row index (1-based, excluding the header) to a background
    colour — used to tint primary-key and foreign-key rows the way the
    reference document does.
    """
    styles = styles or [S_CELL] * len(header)
    data = [[P(h, S_HEAD) for h in header]]
    for r in rows:
        data.append([P(c, styles[i] if i < len(styles) else S_CELL)
                     for i, c in enumerate(r)])

    total = sum(widths)
    scaled = [w / total * USABLE for w in widths]

    cmd = [
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BAND]),
    ]
    for idx, colour in (shade or {}).items():
        cmd.append(("BACKGROUND", (0, idx), (-1, idx), colour))

    t = Table(data, colWidths=scaled, repeatRows=repeat, hAlign="LEFT")
    t.setStyle(TableStyle(cmd))
    return t


class SectionMarker(Flowable):
    """A zero-height flowable that names the running header as it is drawn.

    Setting the header while the story is *built* would leave every page
    carrying the last section in the document, because building happens before
    any page is painted. Flowables draw in page order, so doing it here makes
    the header track the content.
    """

    width = 0
    height = 0

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    def draw(self) -> None:
        """Point the running header at this section."""
        set_section(self.name)

    def wrap(self, aw: float, ah: float) -> tuple[float, float]:
        """Occupy no space."""
        return 0, 0


def h1(text: str) -> list[Any]:
    """Return a module heading block."""
    bar = Table([[P(text.upper(), _st("bar", fontName="Helvetica-Bold",
                                      fontSize=12, textColor=colors.white))]],
                colWidths=[USABLE])
    bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HEAD_BG),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return [SectionMarker(text.title()), bar, Spacer(1, 4 * mm)]


def h2(text: str, status: str = "") -> Any:
    """Return a table heading, optionally carrying an IMPLEMENTED/PROPOSED tag."""
    label = f"{text}"
    if status:
        label += f"   [{status}]"
    return Paragraph(label, S_H2)
