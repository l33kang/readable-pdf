import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from rq.job import Job

from app.queue import ocr_queue, redis_connection

router = APIRouter()

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
UPLOAD_DIR = DATA_DIR / "uploads"
RESULTS_DIR = DATA_DIR / "results"


def validate_document_id(document_id: str) -> str:
    """Ensure the document ID is a valid UUID."""
    try:
        return str(uuid.UUID(document_id))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid document ID."
        )


@router.post("/api/documents/{document_id}/process")
def start_processing(document_id: str):
    document_id = validate_document_id(document_id)

    matching_files = list(UPLOAD_DIR.glob(f"{document_id}.*"))

    if not matching_files:
        raise HTTPException(
            status_code=404,
            detail="Document not found."
        )

    file_path = matching_files[0]

    job = ocr_queue.enqueue(
        "app.tasks.process_document",
        document_id,
        str(file_path),
    )

    # Save the relationship between the document and its job.
    redis_connection.set(
        f"document:{document_id}:job_id",
        job.id
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


@router.get("/api/documents/{document_id}")
def get_document(document_id: str):
    document_id = validate_document_id(document_id)

    matching_files = list(UPLOAD_DIR.glob(f"{document_id}.*"))

    if not matching_files:
        raise HTTPException(
            status_code=404,
            detail="Document not found."
        )

    job_id = redis_connection.get(
        f"document:{document_id}:job_id"
    )

    status = "uploaded"
    job_result = None
    error = None

    if job_id:
        job_id = job_id.decode("utf-8")

        try:
            job = Job.fetch(job_id, connection=redis_connection)
            status = job.get_status().value

            if job.is_finished:
                job_result = job.result

            if job.is_failed:
                error = job.exc_info

        except Exception:
            status = "unknown"

    searchable_pdf = RESULTS_DIR / f"{document_id}_searchable.pdf"
    json_file = RESULTS_DIR / f"{document_id}.json"

    return {
        "document_id": document_id,
        "status": status,
        "job_id": job_id,
        "outputs": {
            "searchable_pdf": searchable_pdf.exists(),
            "json": json_file.exists(),
        },
        "result": job_result,
        "error": error,
    }


@router.get("/api/documents/{document_id}/download")
def download_document(document_id: str, type: str):
    document_id = validate_document_id(document_id)

    if type == "searchable":
        file_path = RESULTS_DIR / f"{document_id}_searchable.pdf"
        media_type = "application/pdf"
        filename = f"{document_id}_searchable.pdf"

    elif type == "json":
        file_path = RESULTS_DIR / f"{document_id}.json"
        media_type = "application/json"
        filename = f"{document_id}.json"

    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid download type. Use 'searchable' or 'json'."
        )

    if not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Requested output is not available."
        )

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
    )