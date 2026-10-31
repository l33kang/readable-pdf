from rq.job import Job
from app.queue import redis_connection

from pathlib import Path
import os

from fastapi import APIRouter, HTTPException

from app.queue import ocr_queue

router = APIRouter()

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
UPLOAD_DIR = DATA_DIR / "uploads"


@router.post("/api/documents/{document_id}/process")
def start_processing(document_id: str):
    # Find the uploaded document
    matching_files = list(UPLOAD_DIR.glob(f"{document_id}.*"))

    if not matching_files:
        raise HTTPException(
            status_code=404,
            detail="Document not found."
        )

    file_path = matching_files[0]

    # Submit the OCR task to Redis/RQ
    job = ocr_queue.enqueue(
        "app.tasks.process_document",
        document_id,
        str(file_path),
    )

    return {
        "document_id": document_id,
        "job_id": job.id,
        "status": "queued",
    }


@router.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    try:
        job = Job.fetch(job_id, connection=redis_connection)
    except Exception:
        raise HTTPException(
            status_code=404,
            detail="Job not found."
        )

    return {
        "job_id": job.id,
        "status": job.get_status().value,
        "result": job.result if job.is_finished else None,
        "error": job.exc_info if job.is_failed else None,
    }
