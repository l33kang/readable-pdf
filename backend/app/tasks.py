import os
import json
import subprocess
from pathlib import Path

import fitz
from PIL import Image

from app.ocr_engine import extract_blocks
from app.clean_pdf import generate_clean_pdf


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

    # Generate a new PDF containing digital text, not scanned images.
    generate_clean_pdf(result, str(clean_pdf))

    return {
        "document_id": document_id,
        "status": "completed",
        "searchable_pdf": (
            str(searchable_pdf) if searchable_pdf else None
        ),
        "clean_pdf": str(clean_pdf),
        "result_path": str(output_json),
    }