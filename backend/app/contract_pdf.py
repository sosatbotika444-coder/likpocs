"""Server-side PDF template for an already signed hostel agreement."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from html import escape
from os.path import exists
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.config import settings


def _format_datetime(value: datetime | None) -> str:
    if not value:
        return "—"
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    return aware.astimezone(ZoneInfo(settings.timezone)).strftime("%d.%m.%Y %H:%M")


def _styles() -> tuple[dict[str, ParagraphStyle], str]:
    styles = getSampleStyleSheet()
    font_name = "Helvetica"
    for path in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if exists(path):
            try:
                pdfmetrics.registerFont(TTFont("RSBestContract", path))
                font_name = "RSBestContract"
                break
            except Exception:
                pass
    styles.add(ParagraphStyle("ContractTitle", parent=styles["Title"], fontName=font_name, fontSize=13, leading=16, alignment=TA_CENTER, spaceAfter=5))
    styles.add(ParagraphStyle("ContractMeta", parent=styles["Normal"], fontName=font_name, fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=colors.HexColor("#52645a")))
    styles.add(ParagraphStyle("ContractHeading", parent=styles["Heading2"], fontName=font_name, fontSize=9.5, leading=12, spaceBefore=9, spaceAfter=4, keepWithNext=True))
    styles.add(ParagraphStyle("ContractBody", parent=styles["Normal"], fontName=font_name, fontSize=8.6, leading=12, spaceAfter=4))
    styles.add(ParagraphStyle("ContractSmall", parent=styles["Normal"], fontName=font_name, fontSize=7.8, leading=10))
    return styles, font_name


def contract_pdf(
    *, contract: dict[str, object], tenant_signature: str, signed_at: datetime | None, signed_via: str,
    signed_version: str, signed_hash: str, hash_matches: bool, operator_signature: str,
    operator_signed_at: datetime | None,
) -> bytes:
    """Create a selectable-text PDF from the stored agreement, never from a page screenshot."""
    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, leftMargin=42, rightMargin=42, topMargin=38, bottomMargin=40)
    styles, font_name = _styles()
    story = [
        Paragraph(escape(str(contract["title"])), styles["ContractTitle"]),
        Paragraph(escape(f"{contract['number']} · {contract['date']} · {contract['city']}"), styles["ContractMeta"]),
        Spacer(1, 10),
    ]
    for section in contract["sections"]:  # type: ignore[index]
        story.append(Paragraph(escape(str(section["title"])), styles["ContractHeading"]))
        story.extend(Paragraph(escape(str(clause)), styles["ContractBody"]) for clause in section["clauses"])

    channel = "Telegram" if signed_via == "TELEGRAM" else "Sayt" if signed_via else "—"
    verification = "Mos keldi" if hash_matches else "Mos kelmadi"
    details = [
        ["Yashovchi imzosi", tenant_signature or "—"],
        ["Imzolangan vaqt", _format_datetime(signed_at)],
        ["Imzolash kanali", channel],
        ["Shartnoma versiyasi", signed_version or "—"],
        ["Xesh tekshiruvi", verification],
        ["SHA-256 xesh", signed_hash or "—"],
        ["Operator F.I.Sh.", operator_signature or "Imzo belgilanmagan"],
        ["Operator imzolagan vaqt", _format_datetime(operator_signed_at)],
    ]
    details_table = Table([[Paragraph(escape(a), styles["ContractSmall"]), Paragraph(escape(b), styles["ContractSmall"])] for a, b in details], colWidths=(145, 365))
    details_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd7ce")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eff5ef")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    signature_table = Table([
        [Paragraph("YASHOVCHI", styles["ContractSmall"]), Paragraph("OPERATOR", styles["ContractSmall"])],
        [Paragraph(escape(tenant_signature or "________________________"), styles["ContractBody"]), Paragraph(escape(operator_signature or "________________________"), styles["ContractBody"])],
        [Paragraph("Imzo uchun joy", styles["ContractSmall"]), Paragraph("Imzo uchun joy · Muhr uchun joy", styles["ContractSmall"])],
    ], colWidths=(255, 255), rowHeights=(18, 33, 18))
    signature_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#9aada0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd7ce")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eff5ef")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.extend([Spacer(1, 12), KeepTogether([
        Paragraph("IMZO VA TEKSHIRUV MA’LUMOTLARI", styles["ContractHeading"]), details_table,
        Spacer(1, 12), signature_table,
    ])])
    document.build(story)
    return output.getvalue()
