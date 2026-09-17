"""Build the public, fully synthetic curriculum PDF fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "fixtures" / "public" / "synthetic_curriculum_spec.json"
DEFAULT_OUTPUT = ROOT / "fixtures" / "public" / "synthetic_curriculum.pdf"


class InvariantCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        kwargs["invariant"] = 1
        super().__init__(*args, **kwargs)


def _page_footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setFont("STSong-Light", 8)
    canvas.setFillColor(colors.HexColor("#59636E"))
    canvas.drawString(18 * mm, 10 * mm, "完全合成公开 fixture - 不代表真实课程标准")
    canvas.drawRightString(279 * mm, 10 * mm, f"第 {document.page} 页")
    canvas.restoreState()


def build_fixture(spec_path: Path = DEFAULT_SPEC, output_path: Path = DEFAULT_OUTPUT) -> Path:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

    document = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=13 * mm,
        bottomMargin=17 * mm,
        title=spec["title"],
        author="Knowledge Catalog public fixture generator",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ChineseTitle",
        parent=styles["Title"],
        fontName="STSong-Light",
        fontSize=18,
        leading=23,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#17324D"),
    )
    subtitle_style = ParagraphStyle(
        "ChineseSubtitle",
        parent=styles["Normal"],
        fontName="STSong-Light",
        fontSize=9,
        leading=13,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#59636E"),
    )
    cell_style = ParagraphStyle(
        "ChineseCell",
        parent=styles["Normal"],
        fontName="STSong-Light",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#17212B"),
    )
    header_style = ParagraphStyle(
        "ChineseHeader",
        parent=cell_style,
        alignment=TA_CENTER,
        textColor=colors.white,
    )

    story = []
    for term_index, term in enumerate(spec["terms"]):
        story.append(Paragraph(spec["title"], title_style))
        story.append(
            Paragraph(
                f"{term['name']}课程内容表 · fixture_id: {spec['fixture_id']}",
                subtitle_style,
            )
        )
        story.append(Spacer(1, 5 * mm))
        rows = [
            [
                Paragraph("学期", header_style),
                Paragraph("单元", header_style),
                Paragraph("知识点", header_style),
                Paragraph("课程范围原文", header_style),
            ]
        ]
        for unit in term["units"]:
            for topic in unit["topics"]:
                rows.append(
                    [
                        Paragraph(term["name"], cell_style),
                        Paragraph(unit["name"], cell_style),
                        Paragraph(topic["name"], cell_style),
                        Paragraph(topic["scope"], cell_style),
                    ]
                )
        table = Table(
            rows,
            colWidths=[31 * mm, 35 * mm, 52 * mm, 151 * mm],
            repeatRows=1,
            hAlign="CENTER",
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#24557A")),
                    ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#8896A3")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 1), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#F3F7FA")],
                    ),
                ]
            )
        )
        story.append(table)
        if term_index < len(spec["terms"]) - 1:
            story.append(PageBreak())

    document.build(
        story,
        onFirstPage=_page_footer,
        onLaterPages=_page_footer,
        canvasmaker=InvariantCanvas,
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = build_fixture(args.spec, args.output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
