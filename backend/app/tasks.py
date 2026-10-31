
import os
from pathlib import Path

from app.ocr_engine import save_document_json


def process_document(document_id: str, file_path: str) -> dict:
    """Process an uploaded image and save its OCR result."""

    source_path = Path(file_path)

    if not source_path.exists():
        raise FileNotFoundError(f"Document not found: {file_path}")

    data_dir = Path(os.getenv("DATA_DIR", "/data"))
    results_dir = data_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    output_path = results_dir / f"{document_id}.json"

    save_document_json(
        str(source_path),
        str(output_path),
    )

    return {
        "document_id": document_id,
        "status": "completed",
        "result_path": str(output_path),
    }
