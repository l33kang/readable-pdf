from pathlib import Path
import json
import subprocess
import time
import fitz  # PyMuPDF
from PIL import Image, ImageFilter, ImageEnhance
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether
)

ROOT = Path("/data")
GROUND = ROOT / "ground_truth" / "benchmark"
SAMPLES = ROOT / "samples" / "benchmark"
PRED = ROOT / "predictions" / "benchmark"
RESULTS = ROOT / "results" / "benchmark"

for d in [GROUND, SAMPLES, PRED, RESULTS]:
    d.mkdir(parents=True, exist_ok=True)

styles = getSampleStyleSheet()

title = ParagraphStyle(
    "BenchTitle",
    parent=styles["Title"],
    alignment=TA_CENTER,
    fontSize=20,
    leading=24,
    spaceAfter=16,
)

body = ParagraphStyle(
    "BenchBody",
    parent=styles["BodyText"],
    fontSize=11,
    leading=16,
    spaceAfter=8,
)

small = ParagraphStyle(
    "BenchSmall",
    parent=styles["BodyText"],
    fontSize=7,
    leading=9,
    spaceAfter=4,
)

two_col = ParagraphStyle(
    "TwoCol",
    parent=styles["BodyText"],
    fontSize=9,
    leading=12,
)

def write_gt(name, text):
    (GROUND / f"{name}.txt").write_text(
        text.strip() + "\n",
        encoding="utf-8"
    )

def make_pdf(name, story):
    path = SAMPLES / f"{name}.pdf"

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=45,
        leftMargin=45,
        topMargin=45,
        bottomMargin=45,
    )

    doc.build(story)
    return path

def render_pdf(pdf_path, name, dpi=200):
    doc = fitz.open(pdf_path)

    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        out = SAMPLES / f"{name}_page_{i+1}.png"
        pix.save(str(out))

    doc.close()

def ocr_image(image_path, output_path, psm):
    cmd = [
        "tesseract",
        str(image_path),
        str(output_path.with_suffix("")),
        "-l",
        "eng",
        "--psm",
        str(psm),
    ]

    start = time.perf_counter()
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    elapsed = time.perf_counter() - start

    txt = output_path.with_suffix(".txt")

    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)

    return txt.read_text(encoding="utf-8", errors="ignore"), elapsed

def preprocess(image_path, output_path):
    img = Image.open(image_path).convert("L")

    img = ImageEnhance.Contrast(img).enhance(1.15)
    img = ImageEnhance.Sharpness(img).enhance(1.25)

    # Gentle denoising without aggressive thresholding.
    img = img.filter(ImageFilter.MedianFilter(size=3))

    img.save(output_path)

def create_normal():
    name = "01_normal"

    text = """
ReadablePDF is an OCR system designed to make scanned documents searchable,
editable, and accessible. The system processes a page image, detects text,
and produces a digital representation of the document.

A reliable OCR pipeline should preserve the meaning of the source while
minimizing character and word recognition errors. Evaluation should therefore
measure both character error rate and word error rate.
"""

    gt = " ".join(text.split())

    story = [
        Paragraph("ReadablePDF OCR Benchmark", title),
        Paragraph(text, body),
    ]

    make_pdf(name, story)
    write_gt(name, gt)

def create_small():
    name = "02_small_font"

    text = """
Small text is intentionally used in this benchmark. OCR systems often lose
accuracy when characters are tiny, tightly spaced, or printed with weak
contrast. A useful document pipeline should still recover the important words
without introducing large numbers of substitutions or omissions.
"""

    gt = " ".join(text.split())

    story = [
        Paragraph("Small Font OCR Test", title),
        Paragraph(text, small),
        Spacer(1, 8),
        Paragraph(
            "Additional validation sentence: searchable text should remain "
            "useful even when the original scan is difficult to read.",
            small,
        ),
    ]

    make_pdf(name, story)
    write_gt(name, gt)

def create_two_columns():
    name = "03_two_columns"

    left = """
OCR systems must handle different page layouts. Two-column pages are common
in books, reports, newspapers, and academic papers. Reading order becomes an
important part of document reconstruction.
"""

    right = """
A system that recognizes every word but returns them in the wrong order is
still inconvenient for users. This benchmark therefore checks whether text
from a multi-column page remains readable after extraction.
"""

    left = " ".join(left.split())
    right = " ".join(right.split())

    table = Table([
        [Paragraph(left, two_col), Paragraph(right, two_col)]
    ], colWidths=[230, 230])

    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("LINEBELOW", (0, 0), (-1, -1), 0, colors.white),
    ]))

    story = [
        Paragraph("Two Column Layout", title),
        table,
    ]

    make_pdf(name, story)
    write_gt(name, left + " " + right)

def create_grid_table():
    name = "04_grid_table"

    data = [
        ["ID", "Course", "Credits", "Grade"],
        ["001", "Database Systems", "15", "A"],
        ["002", "Computer Networks", "10", "B+"],
        ["003", "Operating Systems", "15", "A-"],
        ["004", "Artificial Intelligence", "20", "A"],
        ["005", "Software Engineering", "15", "B+"],
    ]

    gt = " ".join(" ".join(row) for row in data)

    table = Table(
        [[Paragraph(c, body) for c in row] for row in data],
        colWidths=[55, 170, 75, 70],
    )

    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))

    story = [
        Paragraph("Grid Table", title),
        table,
    ]

    make_pdf(name, story)
    write_gt(name, gt)

def create_borderless_table():
    name = "05_borderless_table"

    data = [
        ["Product", "Quantity", "Unit Price"],
        ["Notebook", "12", "4.50"],
        ["Pen", "30", "1.20"],
        ["Folder", "18", "2.75"],
        ["Marker", "9", "3.10"],
    ]

    gt = " ".join(" ".join(row) for row in data)

    table = Table(
        [[Paragraph(c, body) for c in row] for row in data],
        colWidths=[180, 100, 100],
    )

    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
    ]))

    story = [
        Paragraph("Borderless Table", title),
        table,
    ]

    make_pdf(name, story)
    write_gt(name, gt)

def create_mixed():
    name = "06_mixed"

    table_data = [
        ["Task", "Status", "Score"],
        ["OCR", "Complete", "92"],
        ["Layout", "Testing", "87"],
        ["Export", "Pending", "—"],
    ]

    gt = """
ReadablePDF combines paragraphs and structured information.
The OCR engine should recognize both normal prose and tabular content.
Task Status Score OCR Complete 92 Layout Testing 87 Export Pending —
"""

    table = Table(
        [[Paragraph(c, body) for c in row] for row in table_data],
        colWidths=[130, 120, 80],
    )

    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
    ]))

    story = [
        Paragraph("Mixed Document", title),
        Paragraph(
            "ReadablePDF combines paragraphs and structured information. "
            "The OCR engine should recognize both normal prose and tabular content.",
            body,
        ),
        Spacer(1, 10),
        table,
    ]

    make_pdf(name, story)
    write_gt(name, " ".join(gt.split()))

def create_noisy():
    name = "07_noisy"

    text = """
This page simulates a degraded document. OCR must tolerate mild blur,
reduced contrast, and image noise while retaining the original words.
The goal is not perfect visual restoration but dependable text recovery.
"""

    gt = " ".join(text.split())

    story = [
        Paragraph("Noisy Scan", title),
        Paragraph(text, body),
    ]

    pdf = make_pdf(name, story)

    render_pdf(pdf, name, dpi=200)

    src = SAMPLES / f"{name}_page_1.png"
    img = Image.open(src).convert("L")

    img = img.filter(ImageFilter.GaussianBlur(radius=0.8))
    img = ImageEnhance.Contrast(img).enhance(0.65)

    # Add deterministic light noise.
    import random
    random.seed(42)

    px = img.load()

    for _ in range(int(img.width * img.height * 0.003)):
        x = random.randrange(img.width)
        y = random.randrange(img.height)

        value = px[x, y]

        if random.random() < 0.5:
            value = max(0, value - 25)
        else:
            value = min(255, value + 25)

        px[x, y] = value

    noisy_path = SAMPLES / f"{name}_degraded.png"
    img.save(noisy_path)

    return True

def create_skewed():
    name = "08_skewed"

    text = """
Deskewing is important because photographed and scanned pages are not always
perfectly aligned. Even a small rotation can make text recognition harder,
especially for tables and small fonts.
"""

    gt = " ".join(text.split())

    story = [
        Paragraph("Skewed Document", title),
        Paragraph(text, body),
    ]

    pdf = make_pdf(name, story)

    render_pdf(pdf, name, dpi=200)

    src = SAMPLES / f"{name}_page_1.png"
    img = Image.open(src).convert("RGB")

    rotated = img.rotate(
        3.2,
        expand=True,
        fillcolor="white",
        resample=Image.Resampling.BICUBIC,
    )

    skew_path = SAMPLES / f"{name}_degraded.png"
    rotated.save(skew_path)

    return True

def main():
    print("Generating benchmark PDFs...")
    create_normal()
    create_small()
    create_two_columns()
    create_grid_table()
    create_borderless_table()
    create_mixed()
    create_noisy()
    create_skewed()

    # Render regular PDFs that were not already rendered.
    for pdf in SAMPLES.glob("*.pdf"):
        name = pdf.stem

        regular = SAMPLES / f"{name}_page_1.png"

        if not regular.exists():
            render_pdf(pdf, name, dpi=200)

    configs = {
        "baseline_psm6": 6,
        "psm4": 4,
        "psm11": 11,
    }

    documents = [
        ("01_normal", SAMPLES / "01_normal_page_1.png"),
        ("02_small_font", SAMPLES / "02_small_font_page_1.png"),
        ("03_two_columns", SAMPLES / "03_two_columns_page_1.png"),
        ("04_grid_table", SAMPLES / "04_grid_table_page_1.png"),
        ("05_borderless_table", SAMPLES / "05_borderless_table_page_1.png"),
        ("06_mixed", SAMPLES / "06_mixed_page_1.png"),
        ("07_noisy", SAMPLES / "07_noisy_degraded.png"),
        ("08_skewed", SAMPLES / "08_skewed_degraded.png"),
    ]

    report = {
        "benchmark": "ReadablePDF Synthetic OCR Benchmark",
        "documents": [],
        "summary": {},
    }

    print()
    print("Running OCR configurations...")

    for config_name, psm in configs.items():
        print(f"  {config_name}")

        for name, image in documents:
            out_dir = PRED / config_name
            out_dir.mkdir(parents=True, exist_ok=True)

            out = out_dir / f"{name}.txt"

            text, runtime = ocr_image(image, out, psm)

            report["documents"].append({
                "document": name,
                "configuration": config_name,
                "psm": psm,
                "runtime_seconds": round(runtime, 4),
                "prediction": str(out.relative_to(ROOT)),
            })

    # Preprocessed versions.
    print("  preprocess_psm6")

    prep_dir = PRED / "preprocess_psm6"
    prep_dir.mkdir(parents=True, exist_ok=True)

    for name, image in documents:
        preprocessed = SAMPLES / f"{name}_preprocessed.png"

        preprocess(image, preprocessed)

        out = prep_dir / f"{name}.txt"

        text, runtime = ocr_image(
            preprocessed,
            out,
            6,
        )

        report["documents"].append({
            "document": name,
            "configuration": "preprocess_psm6",
            "psm": 6,
            "runtime_seconds": round(runtime, 4),
            "prediction": str(out.relative_to(ROOT)),
            "preprocessed_image": str(preprocessed.relative_to(ROOT)),
        })

    report_path = RESULTS / "benchmark_report.json"
    report_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print()
    print("=" * 60)
    print("BENCHMARK GENERATION COMPLETE")
    print("=" * 60)
    print(f"Ground truth : {GROUND}")
    print(f"Samples      : {SAMPLES}")
    print(f"Predictions  : {PRED}")
    print(f"Report       : {report_path}")
    print()
    print("Next: run evaluate.py against each prediction directory.")

if __name__ == "__main__":
    main()

