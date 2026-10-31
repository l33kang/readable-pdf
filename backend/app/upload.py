import os
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter()

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
UPLOAD_DIR = DATA_DIR / "uploads"

FILE_SIGNATURES = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".pdf": (b"%PDF-",),
}


def detect_file_type(content: bytes) -> str | None:
    """Identify a file using its binary signature."""
    for extension, signatures in FILE_SIGNATURES.items():
        if any(content.startswith(signature) for signature in signatures):
            return extension

    return None


@router.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()

    if extension not in FILE_SIGNATURES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file extension."
        )

    content = await file.read(MAX_FILE_SIZE + 1)

    if not content:
        raise HTTPException(
            status_code=400,
            detail="File is empty."
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File too large. Maximum size is 20 MB."
        )

    detected_type = detect_file_type(content)

    if detected_type is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid or unsupported file content."
        )

    if detected_type != extension:
        raise HTTPException(
            status_code=400,
            detail="File extension does not match its actual content."
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    document_id = str(uuid.uuid4())
    saved_path = UPLOAD_DIR / f"{document_id}{extension}"

    saved_path.write_bytes(content)

    return {
        "document_id": document_id,
        "filename": filename,
        "size": len(content),
        "detected_type": detected_type,
        "status": "uploaded"
    }
