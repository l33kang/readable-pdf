# Scan-to-Text Converter (Part One)

Converts scanned PDFs and photos of printed text into searchable PDFs, clean text PDFs, and word-level JSON.

## Contents
- `docs/SRS.md` : Software Requirements Specification
- `schema/ocr_output.example.json` : JSON output format (version 1)
- `backend/Dockerfile`, `backend/requirements.txt` : backend and worker image
- `docker-compose.yml` : api, worker, redis (frontend commented out)
- `scripts/ocr_one.sh` : first test, one scanned PDF to a searchable PDF
- `eval/` : test pages and hand-typed ground truth
- `.env.example` : configuration template

## First steps
1. Put a scanned PDF in `eval/samples/`.
2. Build the image: `docker compose build api`
3. Check models: `docker compose run --rm api tesseract --list-langs` (expect `eng`, `kin`, `ara`)
4. Run: `docker compose run --rm api bash -c "cd /app && ./scripts/ocr_one.sh /data/in.pdf /data/out.pdf"` after mounting your files, or run the script inside the container.

The backend code (`backend/app`) is not included yet; the SRS describes what to build. Verify tool versions, the tessdata path, and licenses before release.
