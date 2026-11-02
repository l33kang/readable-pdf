import json
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from rq.job import Job

from app.queue import ocr_queue, redis_connection

router = APIRouter()


class CorrectionDecisionRequest(BaseModel):
    decision: str


class BulkCorrectionDecisionItem(BaseModel):
    correction_id: str
    decision: str


class BulkCorrectionDecisionRequest(BaseModel):
    decisions: list[BulkCorrectionDecisionItem]


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
        raise HTTPException(status_code=404, detail="Document not found.")

    # Check whether this document already has an active job.
    existing_job_id = redis_connection.get(
        f"document:{document_id}:job_id"
    )

    if existing_job_id:
        existing_job_id = existing_job_id.decode("utf-8")

        try:
            existing_job = Job.fetch(
                existing_job_id,
                connection=redis_connection
            )

            if existing_job.get_status().value in [
                "queued",
                "started",
                "deferred",
                "scheduled",
            ]:
                return {
                    "document_id": document_id,
                    "job_id": existing_job.id,
                    "status": existing_job.get_status().value,
                    "message": "Processing is already in progress."
                }

        except Exception:
            pass

    file_path = matching_files[0]

    job = ocr_queue.enqueue(
        "app.tasks.process_document",
        document_id,
        str(file_path),
    )

    redis_connection.set(
        f"document:{document_id}:job_id",
        job.id
    )

    return {
        "document_id": document_id,
        "job_id": job.id,
        "status": "queued"
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
    clean_pdf = RESULTS_DIR / f"{document_id}_clean.pdf"
    json_file = RESULTS_DIR / f"{document_id}.json"
    correction_report = RESULTS_DIR / f"{document_id}_report.json"

    return {
        "document_id": document_id,
        "status": status,
        "job_id": job_id,
        "outputs": {
            "searchable_pdf": searchable_pdf.exists(),
            "clean_pdf": clean_pdf.exists(),
            "json": json_file.exists(),
            "correction_report": correction_report.exists(),
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

    elif type == "clean":
        file_path = RESULTS_DIR / f"{document_id}_clean.pdf"
        media_type = "application/pdf"
        filename = f"{document_id}_clean.pdf"

    elif type == "json":
        file_path = RESULTS_DIR / f"{document_id}.json"
        media_type = "application/json"
        filename = f"{document_id}.json"

    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid download type. Use 'searchable', 'clean', or 'json'."
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


@router.get("/api/documents/{document_id}/corrections")
def get_corrections(document_id: str):
    document_id = validate_document_id(document_id)
    report_file = RESULTS_DIR / f"{document_id}_report.json"
    decisions_file = RESULTS_DIR / f"{document_id}_correction_decisions.json"
    if not report_file.is_file():
        raise HTTPException(
            status_code=404,
            detail="Correction report not found.",
        )
    with open(report_file, "r", encoding="utf-8") as file:
        report = json.load(file)
    decisions = {}
    if decisions_file.is_file():
        with open(decisions_file, "r", encoding="utf-8") as file:
            decisions = json.load(file)
    corrections = []
    for item in report.get("corrections", []):
        correction = item.copy()
        decision = decisions.get(correction["id"])
        correction["status"] = (
            "auto_applied"
            if correction["context_score"] == 2
            else "needs_review"
        )
        correction["decision"] = decision
        correction["effective_status"] = (
            decision if decision else correction["status"]
        )
        corrections.append(correction)
    correction_statistics = {
        "total": len(corrections),
        "pending_review": sum(
            1 for item in corrections
            if item["decision"] is None
            and item["status"] == "needs_review"
        ),
        "accepted": sum(
            1 for item in corrections
            if item["decision"] == "accepted"
        ),
        "rejected": sum(
            1 for item in corrections
            if item["decision"] == "rejected"
        ),
        "auto_applied": sum(
            1 for item in corrections
            if item["decision"] is None
            and item["status"] == "auto_applied"
        ),
    }
    return {
        "document_id": document_id,
        "summary": report.get("summary", {}),
        "corrections": corrections,
        "correction_statistics": correction_statistics,
    }


@router.post("/api/documents/{document_id}/corrections/bulk")
def bulk_review_corrections(
    document_id: str,
    request: BulkCorrectionDecisionRequest,
):
    document_id = validate_document_id(document_id)
    report_file = RESULTS_DIR / f"{document_id}_report.json"
    decisions_file = RESULTS_DIR / f"{document_id}_correction_decisions.json"

    if not report_file.is_file():
        raise HTTPException(
            status_code=404,
            detail="Correction report not found.",
        )

    if not request.decisions:
        raise HTTPException(
            status_code=400,
            detail="At least one correction decision is required.",
        )

    correction_ids = [
        item.correction_id for item in request.decisions
    ]

    if len(correction_ids) != len(set(correction_ids)):
        raise HTTPException(
            status_code=400,
            detail="Duplicate correction IDs are not allowed.",
        )

    for item in request.decisions:
        if item.decision not in ("accepted", "rejected"):
            raise HTTPException(
                status_code=400,
                detail="Decision must be 'accepted' or 'rejected'.",
            )

    with open(report_file, "r", encoding="utf-8") as file:
        report = json.load(file)

    valid_ids = {
        correction["id"]
        for correction in report.get("corrections", [])
    }
    invalid_ids = [
        correction_id
        for correction_id in correction_ids
        if correction_id not in valid_ids
    ]
    if invalid_ids:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Some correction IDs were not found.",
                "invalid_correction_ids": invalid_ids,
            },
        )

    decisions = {}
    if decisions_file.is_file():
        with open(decisions_file, "r", encoding="utf-8") as file:
            decisions = json.load(file)

    for item in request.decisions:
        decisions[item.correction_id] = item.decision

    with open(decisions_file, "w", encoding="utf-8") as file:
        json.dump(decisions, file, indent=2)

    job = ocr_queue.enqueue(
        "app.tasks.rebuild_clean_document",
        document_id,
    )

    return {
        "document_id": document_id,
        "updated_count": len(request.decisions),
        "decisions": [
            {
                "correction_id": item.correction_id,
                "decision": item.decision,
            }
            for item in request.decisions
        ],
        "job_id": job.id,
        "status": "queued",
    }


@router.post("/api/documents/{document_id}/corrections/{correction_id}")
def review_correction(
    document_id: str,
    correction_id: str,
    request: CorrectionDecisionRequest,
):
    document_id = validate_document_id(document_id)

    if request.decision not in ["accepted", "rejected"]:
        raise HTTPException(
            status_code=400,
            detail="Decision must be 'accepted' or 'rejected'.",
        )

    report_file = RESULTS_DIR / f"{document_id}_report.json"
    decisions_file = RESULTS_DIR / f"{document_id}_correction_decisions.json"
    ocr_file = RESULTS_DIR / f"{document_id}.json"

    if not ocr_file.is_file() or not report_file.is_file():
        raise HTTPException(
            status_code=404,
            detail="Processed document or correction report not found.",
        )

    with open(report_file, "r", encoding="utf-8") as file:
        report = json.load(file)

    correction_exists = any(
        item.get("id") == correction_id
        for item in report.get("corrections", [])
    )

    if not correction_exists:
        raise HTTPException(
            status_code=404,
            detail="Correction not found.",
        )

    decisions = {}

    if decisions_file.is_file():
        with open(decisions_file, "r", encoding="utf-8") as file:
            decisions = json.load(file)

    decisions[correction_id] = request.decision

    with open(decisions_file, "w", encoding="utf-8") as file:
        json.dump(decisions, file, indent=2)

    job = ocr_queue.enqueue(
        "app.tasks.rebuild_clean_document",
        document_id,
    )

    return {
        "document_id": document_id,
        "correction_id": correction_id,
        "decision": request.decision,
        "job_id": job.id,
        "status": "queued",
    }