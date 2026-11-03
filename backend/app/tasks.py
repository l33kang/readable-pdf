
import os
import json
import subprocess
from pathlib import Path

import fitz
from PIL import Image

from app.ocr_engine import extract_blocks
from app.clean_pdf import build_elements, to_text, render_pdf, write_report


LANGUAGES = ["eng"]
DPI = 300


def process_document(
    document_id: str,
    file_path: str,
    output_format: str = "searchable_pdf",
) -> dict:
    """Process a document and generate only the requested output."""
    if output_format not in ("searchable_pdf", "simple_pdf", "text"):
        raise ValueError("Invalid output format.")

    source_path = Path(file_path)

    if not source_path.exists():
        raise FileNotFoundError(f"Document not found: {file_path}")

    data_dir = Path(os.getenv("DATA_DIR", "/data"))
    results_dir = data_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    searchable_pdf = results_dir / f"{document_id}_searchable.pdf"
    clean_pdf = results_dir / f"{document_id}_clean.pdf"
    output_json = results_dir / f"{document_id}.json"
    text_file = results_dir / f"{document_id}.txt"

    # SEARCHABLE PDF: OCRmyPDF handles OCR and PDF creation.
    # Do not run extract_blocks() or correction analysis here.
    if output_format == "searchable_pdf":
        if source_path.suffix.lower() != ".pdf":
            raise ValueError("Searchable PDF requires a PDF input.")

        subprocess.run(
            [
                "ocrmypdf",
                "-l", "+".join(LANGUAGES),
                "--skip-text",
                "--deskew",
                "--rotate-pages",
                str(source_path),
                str(searchable_pdf),
            ],
            check=True,
        )

        return {
            "document_id": document_id,
            "status": "completed",
            "output_format": output_format,
            "searchable_pdf": str(searchable_pdf),
        }

    # SIMPLE PDF and TEXT: perform one structured OCR pass.
    pages = []

    if source_path.suffix.lower() == ".pdf":
        with fitz.open(source_path) as pdf:
            for page_number, page in enumerate(pdf, start=1):
                pixmap = page.get_pixmap(dpi=DPI, alpha=False)

                image_path = results_dir / (
                    f"{document_id}_page_{page_number}.png"
                )

                try:
                    pixmap.save(str(image_path))

                    pages.append({
                        "page": page_number,
                        "width": pixmap.width,
                        "height": pixmap.height,
                        "dpi": DPI,
                        "blocks": extract_blocks(str(image_path)),
                    })
                finally:
                    image_path.unlink(missing_ok=True)

    else:
        with Image.open(source_path) as image:
            width, height = image.size

        pages = [
            {
                "page": 1,
                "width": width,
                "height": height,
                "dpi": DPI,
                "blocks": extract_blocks(str(source_path)),
            }
        ]

    result = {
        "schema_version": 1,
        "document_id": document_id,
        "languages": LANGUAGES,
        "pages": pages,
    }

    with open(output_json, "w", encoding="utf-8") as file:
        json.dump(result, file, indent=2, ensure_ascii=False)

    # Build correction suggestions for text-based outputs.
    build_result = build_elements(result)

    write_report(
        build_result,
        str(results_dir / f"{document_id}_report.json"),
        str(results_dir / f"{document_id}_report.txt"),
    )

    clean_text = to_text(build_result.elements)

    if output_format == "text":
        text_file.write_text(clean_text, encoding="utf-8")

    elif output_format == "simple_pdf":
        render_pdf(build_result.elements, str(clean_pdf))

    # Remember which output was requested for correction rebuilds.
    (results_dir / f"{document_id}_processing.json").write_text(
        json.dumps({"output_format": output_format}),
        encoding="utf-8",
    )

    return {
        "document_id": document_id,
        "status": "completed",
        "output_format": output_format,
        "clean_pdf": str(clean_pdf) if output_format == "simple_pdf" else None,
        "text_file": str(text_file) if output_format == "text" else None,
        "result_path": str(output_json),
    }


def rebuild_clean_document(document_id: str) -> dict:
    """Regenerate clean outputs using saved correction decisions."""

    results_dir = Path(os.getenv("DATA_DIR", "/data")) / "results"

    output_json = results_dir / f"{document_id}.json"
    processing_file = results_dir / f"{document_id}_processing.json"
    decisions_file = (
        results_dir / f"{document_id}_correction_decisions.json"
    )
    clean_pdf = results_dir / f"{document_id}_clean.pdf"
    text_file = results_dir / f"{document_id}.txt"

    if not output_json.is_file():
        raise FileNotFoundError("OCR result not found.")

    if not processing_file.is_file():
        raise FileNotFoundError("Processing metadata not found.")
    with open(processing_file, "r", encoding="utf-8") as file:
        output_format = json.load(file).get("output_format")
    if output_format not in ("simple_pdf", "text"):
        raise ValueError("Invalid output format for correction rebuild.")

    with open(output_json, "r", encoding="utf-8") as file:
        ocr_data = json.load(file)

    correction_decisions = {}

    if decisions_file.is_file():
        with open(decisions_file, "r", encoding="utf-8") as file:
            correction_decisions = json.load(file)

    build_result = build_elements(
        ocr_data,
        correction_decisions=correction_decisions,
    )

    write_report(
        build_result,
        str(results_dir / f"{document_id}_report.json"),
        str(results_dir / f"{document_id}_report.txt"),
    )

    clean_text = to_text(build_result.elements)

    if output_format == "text":
        text_file.write_text(clean_text, encoding="utf-8")

    elif output_format == "simple_pdf":
        render_pdf(build_result.elements, str(clean_pdf))

    return {
        "document_id": document_id,
        "status": "completed",
        "output_format": output_format,
        "clean_pdf": str(clean_pdf) if output_format == "simple_pdf" else None,
        "text_file": str(text_file) if output_format == "text" else None,
    }
