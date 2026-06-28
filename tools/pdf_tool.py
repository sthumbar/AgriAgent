"""PDF report generation using ReportLab."""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

# ── Colour palette ───────────────────────────────────────────────────────────
DARK_GREEN = colors.HexColor("#1B5E20")
MID_GREEN = colors.HexColor("#388E3C")
LIGHT_GREEN = colors.HexColor("#C8E6C9")
AMBER = colors.HexColor("#FF8F00")
RED = colors.HexColor("#C62828")
LIGHT_GREY = colors.HexColor("#F5F5F5")
MID_GREY = colors.HexColor("#9E9E9E")
WHITE = colors.white
BLACK = colors.black

URGENCY_COLOUR = {
    "Low": MID_GREEN,
    "Medium": AMBER,
    "High": colors.HexColor("#E65100"),
    "Critical": RED,
}


# ── Style helpers ────────────────────────────────────────────────────────────

def _build_styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "AgriTitle",
            parent=base["Title"],
            fontSize=22,
            textColor=WHITE,
            spaceAfter=4,
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
        ),
        "subtitle": ParagraphStyle(
            "AgriSubtitle",
            parent=base["Normal"],
            fontSize=11,
            textColor=LIGHT_GREEN,
            spaceAfter=0,
            alignment=TA_CENTER,
        ),
        "h1": ParagraphStyle(
            "AgriH1",
            parent=base["Heading1"],
            fontSize=14,
            textColor=DARK_GREEN,
            spaceBefore=14,
            spaceAfter=6,
            fontName="Helvetica-Bold",
        ),
        "h2": ParagraphStyle(
            "AgriH2",
            parent=base["Heading2"],
            fontSize=12,
            textColor=MID_GREEN,
            spaceBefore=8,
            spaceAfter=4,
            fontName="Helvetica-Bold",
        ),
        "body": ParagraphStyle(
            "AgriBody",
            parent=base["Normal"],
            fontSize=10,
            leading=15,
            textColor=BLACK,
            spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "AgriBullet",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            leftIndent=18,
            firstLineIndent=-12,
            spaceAfter=3,
        ),
        "caption": ParagraphStyle(
            "AgriCaption",
            parent=base["Normal"],
            fontSize=8,
            textColor=MID_GREY,
            alignment=TA_RIGHT,
        ),
        "disclaimer": ParagraphStyle(
            "AgriDisclaimer",
            parent=base["Normal"],
            fontSize=8,
            textColor=MID_GREY,
            leftIndent=8,
            rightIndent=8,
            alignment=TA_CENTER,
        ),
    }


def _bullet(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(f"• {text}", style)


def _section_rule() -> HRFlowable:
    return HRFlowable(width="100%", thickness=0.5, color=LIGHT_GREEN, spaceAfter=4)


# ── Main PDF generator ───────────────────────────────────────────────────────

def generate_pdf_report(
    data: Dict[str, Any],
    output_path: str,
) -> str:
    """
    Generate a formatted A4 PDF report from the analysis data.

    Args:
        data: Combined analysis dict containing vision_result, recommendations,
              report_summary, and rag_context.
        output_path: Destination file path (must end in .pdf).

    Returns:
        Absolute path to the saved PDF.

    Raises:
        OSError: If the output directory cannot be created.
        ValueError: If required keys are missing from data.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    styles = _build_styles()
    story: List[Any] = []

    vision: Dict = data.get("vision_result", {})
    recs: Dict = data.get("recommendations", {})
    summary: Dict = data.get("report_summary", {})
    rag_context: str = data.get("rag_context", "")
    timestamp: str = data.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    crop_name = vision.get("crop", "Unknown Crop")
    disease_name = vision.get("disease", "Unknown")
    confidence = vision.get("confidence", 0)
    severity = vision.get("severity", "Unknown")
    urgency = recs.get("urgency", summary.get("key_metrics", {}).get("urgency_level", "Medium"))

    # ── Header banner (coloured table) ──────────────────────────────────────
    header_data = [
        [Paragraph("🌿 Agri AI Assistant", styles["title"])],
        [Paragraph("Crop Health Analysis Report", styles["subtitle"])],
        [Paragraph(f"Generated: {timestamp}", styles["subtitle"])],
    ]
    header_table = Table(header_data, colWidths=[18 * cm])
    header_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), DARK_GREEN),
            ("TOPPADDING", (0, 0), (0, 0), 16),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 16),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ])
    )
    story.append(header_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Key metrics summary table ────────────────────────────────────────────
    urgency_colour = URGENCY_COLOUR.get(urgency, AMBER)
    metrics_data = [
        ["Crop Identified", "Disease / Condition", "Confidence", "Severity", "Urgency"],
        [
            crop_name,
            disease_name,
            f"{confidence}%",
            severity,
            urgency,
        ],
    ]
    metrics_table = Table(metrics_data, colWidths=[3.2 * cm, 4.5 * cm, 2.8 * cm, 2.8 * cm, 2.8 * cm])
    metrics_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), MID_GREEN),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 1), (-1, 1), LIGHT_GREY),
            ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 1), (-1, 1), 10),
            ("TEXTCOLOR", (4, 1), (4, 1), urgency_colour),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [LIGHT_GREY]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ])
    )
    story.append(metrics_table)
    story.append(Spacer(1, 0.3 * cm))

    # ── Executive Summary ────────────────────────────────────────────────────
    exec_summary = summary.get(
        "executive_summary",
        recs.get("disease_explanation", "Analysis complete. See details below."),
    )
    story.append(Paragraph("Executive Summary", styles["h1"]))
    _section_rule()
    story.append(_section_rule())
    story.append(Paragraph(exec_summary, styles["body"]))

    # ── Analysis Narrative ───────────────────────────────────────────────────
    narrative = summary.get("analysis_narrative", "")
    if narrative:
        story.append(Paragraph("Detailed Analysis", styles["h1"]))
        story.append(_section_rule())
        story.append(Paragraph(narrative, styles["body"]))

    # ── Disease Explanation ──────────────────────────────────────────────────
    disease_exp = recs.get("disease_explanation", "")
    if disease_exp and disease_name not in ("Healthy", "Unknown"):
        story.append(Paragraph("Disease / Condition Overview", styles["h1"]))
        story.append(_section_rule())
        story.append(Paragraph(disease_exp, styles["body"]))
        story.append(Spacer(1, 0.2 * cm))

        additional_notes = vision.get("additional_notes", "")
        if additional_notes:
            story.append(Paragraph(f"<i>Field observations: {additional_notes}</i>", styles["body"]))

    # ── Fertilizer Recommendations ───────────────────────────────────────────
    fertilizer = recs.get("fertilizer", {})
    if fertilizer:
        story.append(Paragraph("Fertilizer Programme", styles["h1"]))
        story.append(_section_rule())
        fert_rows = [
            ["Parameter", "Recommendation"],
            ["Primary Fertilizer", fertilizer.get("primary", "—")],
            ["Secondary Supplement", fertilizer.get("secondary", "—")],
            ["Application Rate", fertilizer.get("application_rate", "—")],
            ["Frequency", fertilizer.get("frequency", "—")],
            ["Notes", fertilizer.get("notes", "—")],
        ]
        fert_table = Table(fert_rows, colWidths=[5 * cm, 13 * cm])
        fert_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), MID_GREEN),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BACKGROUND", (0, 1), (0, -1), LIGHT_GREEN),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
            ])
        )
        story.append(fert_table)
        story.append(Spacer(1, 0.2 * cm))

    # ── Irrigation Schedule ──────────────────────────────────────────────────
    irrigation = recs.get("irrigation", {})
    if irrigation:
        story.append(Paragraph("Irrigation Schedule", styles["h1"]))
        story.append(_section_rule())
        irr_rows = [
            ["Parameter", "Recommendation"],
            ["Frequency", irrigation.get("frequency", "—")],
            ["Amount per Session", irrigation.get("amount", "—")],
            ["Best Timing", irrigation.get("timing", "—")],
            ["Method", irrigation.get("method", "—")],
            ["Notes", irrigation.get("notes", "—")],
        ]
        irr_table = Table(irr_rows, colWidths=[5 * cm, 13 * cm])
        irr_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), MID_GREEN),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BACKGROUND", (0, 1), (0, -1), LIGHT_GREEN),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
            ])
        )
        story.append(irr_table)
        story.append(Spacer(1, 0.2 * cm))

    # ── Treatment Steps ──────────────────────────────────────────────────────
    treatment_steps: List[str] = recs.get("treatment_steps", [])
    if treatment_steps:
        story.append(Paragraph("Treatment Protocol", styles["h1"]))
        story.append(_section_rule())
        for step in treatment_steps:
            story.append(Paragraph(f"• {step}", styles["bullet"]))
        story.append(Spacer(1, 0.2 * cm))

    # ── Prioritised Action Plan ──────────────────────────────────────────────
    action_plan: List[Dict] = summary.get("action_plan", [])
    if action_plan:
        story.append(Paragraph("Prioritised Action Plan", styles["h1"]))
        story.append(_section_rule())
        ap_rows = [["Priority", "Action", "Timeline", "Urgency"]]
        for item in action_plan:
            u = item.get("urgency", "Medium")
            ap_rows.append([
                str(item.get("priority", "")),
                item.get("action", ""),
                item.get("timeline", ""),
                u,
            ])
        ap_table = Table(ap_rows, colWidths=[1.5 * cm, 9 * cm, 4 * cm, 3 * cm])
        ap_styles = [
            ("BACKGROUND", (0, 0), (-1, 0), MID_GREEN),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (3, 0), (3, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
        ]
        for row_idx, item in enumerate(action_plan, 1):
            u = item.get("urgency", "Medium")
            uc = URGENCY_COLOUR.get(u, AMBER)
            ap_styles.append(("TEXTCOLOR", (3, row_idx), (3, row_idx), uc))
            ap_styles.append(("FONTNAME", (3, row_idx), (3, row_idx), "Helvetica-Bold"))
        ap_table.setStyle(TableStyle(ap_styles))
        story.append(ap_table)
        story.append(Spacer(1, 0.2 * cm))

    # ── Prevention & Organic Alternatives ───────────────────────────────────
    prevention: List[str] = recs.get("prevention", [])
    organics: List[str] = recs.get("organic_alternatives", [])

    if prevention or organics:
        story.append(Paragraph("Prevention & Organic Alternatives", styles["h1"]))
        story.append(_section_rule())
        if prevention:
            story.append(Paragraph("Preventive Measures:", styles["h2"]))
            for item in prevention:
                story.append(_bullet(item, styles["bullet"]))
        if organics:
            story.append(Paragraph("Organic Alternatives:", styles["h2"]))
            for item in organics:
                story.append(_bullet(item, styles["bullet"]))
        story.append(Spacer(1, 0.2 * cm))

    # ── RAG Knowledge Context ────────────────────────────────────────────────
    if rag_context and rag_context.strip():
        story.append(Paragraph("Supporting Agricultural Knowledge", styles["h1"]))
        story.append(_section_rule())
        story.append(
            Paragraph(
                "<i>The following information was retrieved from the agricultural knowledge base "
                "and informed this analysis:</i>",
                styles["body"],
            )
        )
        story.append(Spacer(1, 0.2 * cm))
        rag_para = Paragraph(rag_context.replace("\n", "<br/>"), styles["body"])
        rag_box = Table([[rag_para]], colWidths=[18 * cm])
        rag_box.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ])
        )
        story.append(rag_box)
        story.append(Spacer(1, 0.2 * cm))

    # ── Risk Summary ─────────────────────────────────────────────────────────
    risk = summary.get("risk_summary", recs.get("estimated_yield_impact", ""))
    if risk:
        story.append(Paragraph("Risk Assessment", styles["h1"]))
        story.append(_section_rule())
        story.append(Paragraph(risk, styles["body"]))
        story.append(Spacer(1, 0.2 * cm))

    # ── Disclaimer ───────────────────────────────────────────────────────────
    disclaimer = summary.get(
        "disclaimer",
        "This AI-generated report should be reviewed by a certified agronomist before applying chemical treatments.",
    )
    story.append(Spacer(1, 0.4 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GREY))
    story.append(Spacer(1, 0.1 * cm))
    story.append(Paragraph(f"⚠ {disclaimer}", styles["disclaimer"]))
    story.append(Paragraph(f"Report generated by Agri AI Assistant — {timestamp}", styles["caption"]))

    # ── Build PDF ────────────────────────────────────────────────────────────
    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"Agri AI — {crop_name} Analysis Report",
        author="Agri AI Assistant",
        subject="Crop Health Analysis",
    )
    doc.build(story)

    logger.info("PDF report saved to %s", output)
    return str(output.absolute())
