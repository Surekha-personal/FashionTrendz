"""PDF invoice rendering.

ReportLab rather than an HTML-to-PDF converter: WeasyPrint and wkhtmltopdf both
need system libraries (Cairo, Pango, or a headless Qt), which turns a `pip
install` into a Dockerfile problem and breaks the Windows dev setup this
project runs on. ReportLab is pure Python and renders identically everywhere.

The layout is deliberately plain. An invoice is a legal document that has to be
readable in ten years, not a marketing surface.
"""

from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

from django.core.files.base import ContentFile

from apps.core.constants import CURRENCY_SYMBOLS, PROJECT_NAME

#: Page geometry, in points (1 pt = 1/72 inch).
PAGE_MARGIN = 40
LINE_HEIGHT = 14


def _money(amount: Decimal | float | int, currency: str) -> str:
    """Format an amount for the invoice.

    Uses the plain currency code rather than the symbol: ReportLab's built-in
    Type-1 fonts are Latin-1, and the rupee sign is not in Latin-1 — it would
    render as a black box on every Indian invoice.
    """
    return f"{currency} {Decimal(str(amount)):,.2f}"


def render_invoice_pdf(context: dict[str, Any]) -> ContentFile:
    """Render an invoice and return it as an in-memory file."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN,
        bottomMargin=PAGE_MARGIN,
        title=f"Invoice {context['invoice_number']}",
        author=PROJECT_NAME,
    )

    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "InvoiceHeading", parent=styles["Heading1"], fontSize=18, spaceAfter=4
    )
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, leading=11)
    normal = styles["Normal"]

    order = context["order"]
    currency = context["currency"]
    story: list[Any] = []

    # -- Header -------------------------------------------------------------

    story.append(Paragraph(PROJECT_NAME, heading))
    story.append(Paragraph("Tax Invoice", styles["Heading3"]))
    story.append(Spacer(1, 6))

    meta = Table(
        [
            ["Invoice number", context["invoice_number"]],
            ["Invoice date", context["invoice_date"].strftime("%d %b %Y")],
            ["Order number", order.order_number],
            ["Payment method", context["payment_method"]],
            ["Payment status", context["payment_status"]],
        ],
        colWidths=[110, 200],
    )
    meta.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#6b7280")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(meta)
    story.append(Spacer(1, 12))

    # -- Addresses ----------------------------------------------------------

    addresses = Table(
        [
            [
                Paragraph("<b>Shipping address</b>", small),
                Paragraph("<b>Billing address</b>", small),
            ],
            [
                Paragraph(_format_address(context["shipping_address"]), small),
                Paragraph(_format_address(context["billing_address"]), small),
            ],
        ],
        colWidths=[250, 250],
    )
    addresses.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(addresses)
    story.append(Spacer(1, 14))

    # -- Line items ---------------------------------------------------------

    rows: list[list[Any]] = [
        ["#", "Item", "SKU", "Qty", "MRP", "Price", "Total"]
    ]
    for index, item in enumerate(context["items"], start=1):
        label = item.product_name
        if item.display_variant:
            label = f"{label}<br/><font size=7 color='#6b7280'>{item.display_variant}</font>"
        rows.append(
            [
                str(index),
                Paragraph(label, small),
                Paragraph(item.sku, small),
                str(item.quantity),
                _money(item.mrp, currency),
                _money(item.selling_price, currency),
                _money(item.grand_total, currency),
            ]
        )

    table = Table(rows, colWidths=[18, 170, 90, 28, 60, 60, 70], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e5e7eb")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 12))

    # -- Totals -------------------------------------------------------------

    total_rows = [["Subtotal", _money(context["subtotal"], currency)]]
    if context["discount"]:
        total_rows.append(["Discount", f"- {_money(context['discount'], currency)}"])
    if context["coupon_discount"]:
        total_rows.append(
            ["Coupon discount", f"- {_money(context['coupon_discount'], currency)}"]
        )
    total_rows.append(["Shipping", _money(context["shipping_charge"], currency)])
    total_rows.append(["Platform fee", _money(context["platform_fee"], currency)])
    total_rows.append(["GST (included)", _money(context["tax"], currency)])
    total_rows.append(["Grand total", _money(context["grand_total"], currency)])

    totals = Table(total_rows, colWidths=[120, 100], hAlign="RIGHT")
    totals.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor("#111827")),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(totals)
    story.append(Spacer(1, 18))

    story.append(
        Paragraph(
            "GST is included in the item prices shown. "
            "This is a computer-generated invoice and needs no signature.",
            small,
        )
    )

    document.build(story)
    buffer.seek(0)
    return ContentFile(buffer.read(), name=f"{context['invoice_number']}.pdf")


def _format_address(address: dict[str, Any]) -> str:
    """Return an address snapshot as invoice-ready HTML."""
    parts = [
        address.get("full_name", ""),
        address.get("address_line_1", ""),
        address.get("address_line_2", ""),
        f"{address.get('city', '')}, {address.get('state', '')} {address.get('postal_code', '')}".strip(", "),
        address.get("country", ""),
        f"Mobile: {address.get('mobile', '')}" if address.get("mobile") else "",
    ]
    return "<br/>".join(part for part in parts if part and part.strip(", "))
