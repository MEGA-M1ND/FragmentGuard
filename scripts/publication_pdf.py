"""Render the canonical Pandoc Markdown AST as a searchable, linked PDF."""

import json
import subprocess
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
INK = colors.HexColor("#142b3b")
TEAL = colors.HexColor("#176b80")
MUTED = colors.HexColor("#526473")


def inlines(items):
    out = []
    for item in items:
        tag, value = item["t"], item.get("c")
        if tag == "Str":
            out.append(escape(value))
        elif tag in ("Space", "SoftBreak"):
            out.append(" ")
        elif tag == "LineBreak":
            out.append("<br/>")
        elif tag == "Strong":
            out.append("<b>" + inlines(value) + "</b>")
        elif tag == "Emph":
            out.append("<i>" + inlines(value) + "</i>")
        elif tag == "Code":
            out.append('<font face="FGMono">' + escape(value[1]) + "</font>")
        elif tag == "Link":
            out.append(
                '<a color="#176b80" href="' + escape(value[2][0], quote=True) + '">' + inlines(value[1]) + "</a>"
            )
        elif tag == "Span":
            out.append(inlines(value[1]))
        else:
            raise ValueError("Unsupported inline: " + tag)
    return "".join(out)


def build_pdf(output):
    font_dir = Path("/usr/share/fonts/truetype/dejavu")
    for name, file in [
        ("FG", "DejaVuSans.ttf"),
        ("FGBold", "DejaVuSans-Bold.ttf"),
        ("FGItalic", "DejaVuSans-Oblique.ttf"),
        ("FGBoldItalic", "DejaVuSans-BoldOblique.ttf"),
        ("FGSerif", "DejaVuSerif.ttf"),
        ("FGMono", "DejaVuSansMono.ttf"),
    ]:
        pdfmetrics.registerFont(TTFont(name, str(font_dir / file)))
    pdfmetrics.registerFontFamily("FG", normal="FG", bold="FGBold", italic="FGItalic", boldItalic="FGBoldItalic")
    body = ParagraphStyle(
        "FGBody", fontName="FG", fontSize=9.5, leading=14.3, textColor=INK, spaceAfter=7, allowWidows=0, allowOrphans=0
    )
    title = ParagraphStyle("FGTitle", parent=body, fontName="FGSerif", fontSize=23, leading=27, spaceAfter=12)
    heading = ParagraphStyle(
        "FGHeading",
        parent=body,
        fontName="FGBold",
        fontSize=13,
        leading=17,
        spaceBefore=15,
        spaceAfter=7,
        keepWithNext=True,
    )
    small = ParagraphStyle("FGSmall", parent=body, fontSize=8, leading=11, textColor=MUTED)
    cell = ParagraphStyle("FGCell", parent=body, fontSize=8, leading=11, spaceAfter=0)
    cell_head = ParagraphStyle("FGCellHead", parent=cell, fontName="FGBold", textColor=colors.white)
    code = ParagraphStyle(
        "FGCode",
        parent=body,
        fontName="FGMono",
        fontSize=7.5,
        leading=11,
        backColor=colors.HexColor("#f1f5f7"),
        borderPadding=8,
        spaceAfter=10,
    )
    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=48,
        leftMargin=48,
        topMargin=42,
        bottomMargin=44,
        title="FragmentGuard: when a simple baseline was enough",
        author="FragmentGuard project",
        subject="Final project report on provenance and multi-agent oversight",
    )
    width = A4[0] - 96
    ast = json.loads(
        subprocess.check_output(
            ["pandoc", str(ROOT / "docs/final_report.md"), "-f", "gfm-tex_math_dollars", "-t", "json"]
        )
    )
    blocks = ast["blocks"]
    story = [Paragraph("FRAGMENTGUARD · FINAL PROJECT REPORT", small), Spacer(1, 8)]
    i = 0
    while i < len(blocks):
        block = blocks[i]
        tag = block["t"]
        value = block.get("c")
        if tag == "Header":
            story.append(Paragraph(inlines(value[2]), title if value[0] == 1 else heading))
        elif tag in ("Para", "Plain"):
            if len(value) == 1 and value[0]["t"] == "Image":
                src = value[0]["c"][2][0]
                path = (ROOT / "docs" / src).resolve().with_suffix(".png")
                img = Image(str(path))
                ratio = img.imageHeight / img.imageWidth
                figure = [Image(str(path), width=width, height=width * ratio)]
                if i + 1 < len(blocks) and blocks[i + 1]["t"] == "Para":
                    figure.append(Paragraph(inlines(blocks[i + 1]["c"]), small))
                    i += 1
                story.append(KeepTogether(figure))
                story.append(Spacer(1, 7))
            else:
                story.append(Paragraph(inlines(value), body))
        elif tag == "BulletList":
            for entry in value:
                for sub in entry:
                    story.append(Paragraph("• " + inlines(sub["c"]), body))
        elif tag == "OrderedList":
            for n, entry in enumerate(value[1], start=value[0][0]):
                for sub in entry:
                    story.append(Paragraph(f"{n}. " + inlines(sub["c"]), small))
        elif tag == "CodeBlock":
            story.append(Preformatted(value[1], code, maxLineLength=92, splitChars=" /"))
        elif tag == "Table":
            headers = value[3][1]
            rows = list(headers)
            for table_body in value[4]:
                rows.extend(table_body[2])
                rows.extend(table_body[3])
            data = []
            for n, row in enumerate(rows):
                data.append(
                    [
                        Paragraph("<br/>".join(inlines(b["c"]) for b in c[4]), cell_head if n < len(headers) else cell)
                        for c in row[1]
                    ]
                )
            ncols = len(data[0])
            widths = [width * 0.29, width * 0.71] if ncols == 2 else [width * 0.20, width * 0.40, width * 0.40]
            table = Table(data, colWidths=widths, repeatRows=len(headers), hAlign="LEFT", spaceBefore=5, spaceAfter=10)
            commands = [
                ("BACKGROUND", (0, 0), (-1, len(headers) - 1), INK),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -1), 0.35, colors.HexColor("#d5e0e5")),
            ]
            for n in range(len(headers), len(data)):
                if n % 2 == 0:
                    commands.append(("BACKGROUND", (0, n), (-1, n), colors.HexColor("#f3f7f8")))
            table.setStyle(TableStyle(commands))
            story.append(table)
        else:
            raise ValueError("Unsupported block: " + tag)
        i += 1

    def page(canvas, doc):
        canvas.saveState()
        canvas.setFont("FG", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(48, 25, "FragmentGuard · 28 October 2026 · github.com/MEGA-M1ND/FragmentGuard")
        canvas.drawRightString(A4[0] - 48, 25, str(doc.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=page, onLaterPages=page)
