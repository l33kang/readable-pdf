# Scan-to-Text Converter

A tool for converting scanned documents and images into readable, searchable text.

## Project status

**Current milestone:** OCR engine and structured JSON export.

### Implemented

- Extract text from images using Tesseract OCR.
- Extract individual words with confidence scores.
- Record word-level bounding boxes in pixel coordinates.
- Flag words with confidence below 70 for review.
- Return structured OCR results as a Python dictionary.
- Export results to JSON.
- Save JSON output in persistent Docker storage.

### Technology stack

- Python 3.12
- Tesseract OCR
- pytesseract
- Pillow
- FastAPI
- Docker Compose

### Project structure

- `backend/app/ocr_engine.py` — OCR extraction and JSON export.
- `backend/app/main.py` — API entry point.
- `backend/requirements.txt` — Python dependencies.
- `docker-compose.yml` — application services.
- `docs/SRS.md` — Software Requirements Specification.
- `schema/ocr_output.example.json` — example OCR output.
- `eval/` — evaluation resources.

### Run the project

Build the API image:

```powershell
docker compose build api
```

The OCR engine can be tested inside the API container using Python and Pillow.

### Planned work

- Implement and test the FastAPI health endpoint.
- Add document upload and validation.
- Process OCR jobs through a background worker.
- Generate searchable PDFs and clean text PDFs.
- Build the frontend.
- Evaluate OCR quality and improve preprocessing.

See `docs/SRS.md` for the detailed requirements and roadmap.
