
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


def process_document(document_id: str, file_path: str) -> dict:
    """Process an uploaded document and generate its outputs."""

    source_path = Path(file_path)

    if not source_path.exists():
        raise FileNotFoundError(f"Document not found: {file_path}")

    data_dir = Path(os.getenv("DATA_DIR", "/data"))
    results_dir = data_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    output_json = results_dir / f"{document_id}.json"
    clean_pdf = results_dir / f"{document_id}_clean.pdf"
    text_file = results_dir / f"{document_id}.txt"

    searchable_pdf = None

    if source_path.suffix.lower() == ".pdf":
        searchable_pdf = results_dir / f"{document_id}_searchable.pdf"

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

        pages = []

        with fitz.open(searchable_pdf) as pdf:
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

        pages = [{
            "page": 1,
            "width": width,
            "height": height,
            "dpi": DPI,
            "blocks": extract_blocks(str(source_path)),
        }]

    result = {
        "schema_version": 1,
        "document_id": document_id,
        "languages": LANGUAGES,
        "pages": pages,
    }

    # Save structured OCR output.
    with open(output_json, "w", encoding="utf-8") as file:
        json.dump(result, file, indent=2, ensure_ascii=False)

    # Build reconstructed text and correction suggestions.
    build_result = build_elements(result)

    write_report(
        build_result,
        str(results_dir / f"{document_id}_report.json"),
        str(results_dir / f"{document_id}_report.txt"),
    )

    clean_text = to_text(build_result.elements)

    # Save plain text output.
    text_file.write_text(clean_text, encoding="utf-8")

    # Save diagnostic text.
    (results_dir / f"{document_id}_clean_debug.txt").write_text(
        clean_text,
        encoding="utf-8",
    )

    # Generate reconstructed PDF.
    render_pdf(build_result.elements, str(clean_pdf))

    return {
        "document_id": document_id,
        "status": "completed",
        "searchable_pdf": (
            str(searchable_pdf) if searchable_pdf else None
        ),
        "clean_pdf": str(clean_pdf),
        "text_file": str(text_file),
        "result_path": str(output_json),
    }


def rebuild_clean_document(document_id: str) -> dict:
    """Regenerate clean outputs using saved correction decisions."""

    results_dir = Path(os.getenv("DATA_DIR", "/data")) / "results"

    output_json = results_dir / f"{document_id}.json"
    decisions_file = (
        results_dir / f"{document_id}_correction_decisions.json"
    )
    clean_pdf = results_dir / f"{document_id}_clean.pdf"
    text_file = results_dir / f"{document_id}.txt"

    if not output_json.is_file():
        raise FileNotFoundError("OCR result not found.")

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

    # Update text output after corrections.
    text_file.write_text(clean_text, encoding="utf-8")

    (results_dir / f"{document_id}_clean_debug.txt").write_text(
        clean_text,
        encoding="utf-8",
    )

    render_pdf(build_result.elements, str(clean_pdf))

    return {
        "document_id": document_id,
        "status": "completed",
        "clean_pdf": str(clean_pdf),
        "text_file": str(text_file),
    }
