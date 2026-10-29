# Software Requirements Specification: Scan-to-Text Converter (Part One)

**Author:** Ali Salaheldin, INES-Ruhengeri
**Version:** 0.1 (draft)  **Date:** 26 October 2026

---

## 1. Introduction

### 1.1 Purpose
This document specifies the requirements, architecture, tools, OCR models, and deployment setup for Part One of the accessible reading project. Part One converts scanned PDFs and photographed pages of **printed text** into documents whose text can be selected, highlighted, searched, copied, and comfortably read.

### 1.2 Problem statement
Many books and newspapers exist only as scans: every page is an image, so readers cannot select, copy, search, or resize the text. Readers who already struggle with reading are affected most. Phones that cannot copy text from a photo leave the same problem for single pages.

### 1.3 Scope
In scope: image and PDF input, image cleanup, OCR of printed English and Kinyarwanda, three outputs (searchable PDF, clean text PDF, word-level JSON), a web interface, a REST API, and Docker deployment.

Out of scope for Part One: handwriting, text-to-speech, translation, dynamic or animated text, native mobile apps, user accounts beyond a basic version, Arabic (planned as a later phase because of right-to-left, connected script).

### 1.4 Definitions
| Term | Meaning |
|---|---|
| OCR | Optical Character Recognition: turning an image of text into text |
| Searchable PDF | Original page image plus an invisible text layer |
| Clean text PDF | New PDF built from recognized text with a readable font and reading order |
| CER / WER | Character / word error rate against hand-typed ground truth |
| PSM | Tesseract page segmentation mode |
| Sidecar | Plain text file saved next to the PDF |

### 1.5 References
OCRmyPDF and Tesseract documentation, the tessdata_best repository, PyMuPDF and ReportLab documentation, FastAPI documentation. Verify current versions and licenses before release.

## 2. Overall Description

### 2.1 Product perspective
Part One is a standalone system and the foundation for Part Two (TTS, translation, interactive text). Its word-level JSON output is the contract Part Two will consume, so it must be stable and versioned.

### 2.2 Users
1. **Struggling readers** using scanned books, who need larger, cleaner, selectable text.
2. **Students and researchers** who need to search and copy from scanned material.
3. **People with phones that cannot copy text from images.**
4. **The developer** (me), who needs a clear, testable pipeline.

### 2.3 Operating environment
Server: Linux in Docker (developed on Windows through WSL2 or Docker Desktop). Client: any modern browser on desktop or phone, including mid-range Android devices on slow connections.

### 2.4 Constraints
- Printed text only; scan quality varies widely.
- Kinyarwanda accuracy with Tesseract must be measured, not assumed.
- Tools must be free or open source, and licenses must permit the intended use.
- Uploaded documents may be personal, so privacy handling is mandatory.

### 2.5 Assumptions
- Input pages are mainly Latin-script printed text at 200 DPI or higher, or phone photos taken reasonably flat.
- Documents are at most about 500 pages and 200 MB in the first version.

## 3. System Architecture

### 3.1 Overview
```
Browser (React PWA)
   | HTTPS
Reverse proxy (Caddy or Nginx)
   |
API (FastAPI) ---- SQLite/PostgreSQL (job metadata)
   |  \
   |   Shared volume (uploads, work files, outputs)
   |
Redis queue ---- Worker(s) (Python):
                  1. ingest  2. preprocess  3. OCR  4. build outputs
                  tools: PyMuPDF, OpenCV, OCRmyPDF, Tesseract, ReportLab
```

### 3.2 Technology stack
| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.12 (backend), TypeScript (frontend) | Matches existing skills; best OCR ecosystem |
| API | FastAPI + Uvicorn | Async uploads, automatic OpenAPI docs |
| Queue | Redis + RQ (Celery if needs grow) | Books take minutes; work must run in the background |
| OCR engine | Tesseract 5 (LSTM) | Free, supports English, Kinyarwanda, Arabic |
| Searchable PDF | OCRmyPDF | Aligned text layer, deskew, rotate, parallel pages |
| Word data | Tesseract TSV/hOCR via pytesseract | Words, boxes, confidence, block/line numbers |
| Image processing | OpenCV, Pillow, NumPy | Deskew, denoise, binarize, crop, split spreads |
| PDF handling | PyMuPDF (fitz), pikepdf | Page rendering, text-layer inspection, repair |
| Clean PDF output | ReportLab (alternative: WeasyPrint) | Full control over fonts, size, flow |
| Database | SQLite first, PostgreSQL later | Simple start; SQLAlchemy keeps migration easy |
| Frontend | React + TypeScript + Vite, PDF.js | Upload, preview, correction screen |
| Evaluation | pytest, jiwer, rapidfuzz | Automated CER/WER measurement |
| Packaging | Docker + Docker Compose | Reproducible Tesseract/Ghostscript install |
| CI | GitHub Actions | Run tests and build images on every push |

## 4. Functional Requirements

### 4.1 Input
- **FR-1** Accept PDF, JPG, PNG, TIFF, and HEIC (converted on upload).
- **FR-2** Accept multiple images as one document, ordered by the user.
- **FR-3** Validate file type by content (magic bytes), not extension; reject password-protected or corrupt files with a clear message.
- **FR-4** Enforce limits: file size, page count, and pixel count per page.
- **FR-5** Detect whether each PDF page already has a text layer, and skip OCR for pages that do (OCRmyPDF `--skip-text`), unless the user forces re-OCR.

### 4.2 Preprocessing
- **FR-6** Render PDF pages to images at a target of 300 DPI (PyMuPDF).
- **FR-7** Auto-rotate pages (orientation detection) and deskew.
- **FR-8** Improve contrast, remove noise and shadows (adaptive thresholding, background normalization), and crop borders.
- **FR-9** Detect and split two-page book spreads into separate pages.
- **FR-10** Keep the original image for the searchable PDF; use the cleaned image only for recognition and the clean text version.

### 4.3 Recognition
- **FR-11** The user selects languages (English, Kinyarwanda, or both); default is English plus Kinyarwanda.
- **FR-12** Run Tesseract with the LSTM engine (`--oem 1`) and a page segmentation mode chosen per page type (see section 5).
- **FR-13** Store for every word: text, bounding box, confidence, and its block, paragraph, line, and word indices.
- **FR-14** Flag words and pages below a confidence threshold for user review.

### 4.4 Outputs
- **FR-15 Searchable PDF:** original appearance plus an aligned invisible text layer (PDF/A optional).
- **FR-16 Clean text PDF:** new document with real text, correct reading order, paragraphs, headings, adjustable font size, line spacing, and a readable font.
- **FR-17 JSON:** words, lines, paragraphs, and page geometry in the schema of section 6.
- **FR-18 Plain text** (sidecar) and optional Markdown export.
- **FR-19** Offer a ZIP download containing all outputs.

### 4.5 Clean text document rules
- **FR-20** Order text by blocks using layout analysis, then top to bottom within columns, left to right across columns.
- **FR-21** Join hyphenated line breaks (for example `infor-` + `mation`) and merge lines into paragraphs.
- **FR-22** Remove repeated headers, footers, and page numbers (detect by repetition and position).
- **FR-23** Detect headings from relative text height and boldness; render them larger.
- **FR-24** Mark regions detected as images or diagrams with a placeholder or cropped image instead of garbage text.
- **FR-25** Default to a high-legibility font (for example Atkinson Hyperlegible or Noto Sans, both open-licensed), with user-set size, line spacing, and contrast.

### 4.6 Correction
- **FR-26** Show the page image beside recognized text; the user can edit words.
- **FR-27** Edits update the JSON, and the outputs can be regenerated.
- **FR-28** Store corrections as data (original, corrected, confidence), which can later become training data.

### 4.7 Job management
- **FR-29** Each upload creates a job with states: queued, processing (with page progress), done, failed, expired.
- **FR-30** The client polls (or uses server-sent events) for progress.
- **FR-31** Jobs can be cancelled. Failures keep partial results where possible and report which page failed.
- **FR-32** Files and results are deleted automatically after a retention period (default 24 hours) or immediately on request.

## 5. OCR Engine and Models

### 5.1 Primary engine: Tesseract 5
Tesseract 5 uses an LSTM neural network recognizer. Use `--oem 1` (LSTM only).

### 5.2 Language data (`.traineddata`)
| Code | Language | Source |
|---|---|---|
| `eng` | English | tessdata_best |
| `kin` | Kinyarwanda | tessdata_best (verify availability and quality) |
| `ara` | Arabic | tessdata_best (later phase) |

- **tessdata_best** models are slower but more accurate; **tessdata_fast** models are quicker with lower accuracy. Use best for quality, and benchmark both.
- Combine languages with `eng+kin`; order can affect results, so test it.
- Confirm models are installed with `tesseract --list-langs`.

### 5.3 Page segmentation modes
| PSM | Use for |
|---|---|
| 3 | Fully automatic layout, no OSD (default for book pages) |
| 1 | Automatic layout with orientation and script detection |
| 4 | Single column of variable-size text |
| 6 | Single uniform block of text |
| 11 / 12 | Sparse text (captions, scattered text) |

Newspapers: detect columns first (OpenCV projection profiles or a layout model), then OCR each column separately with PSM 4 or 6.

### 5.4 Quality improvement options (in order of effort)
1. Better input: 300 DPI, deskew, clean background, binarization.
2. Correct language set and PSM per page type.
3. Confidence filtering and a correction interface.
4. A word list or user dictionary for Kinyarwanda terms.
5. **Fine-tuning Tesseract** (tesstrain) on Kinyarwanda printed pages, using corrected pages from FR-28 as ground truth.
6. Optional layout-analysis model (LayoutParser or similar) for complex pages, only if Tesseract's own layout detection proves insufficient.

### 5.5 Alternatives to evaluate
PaddleOCR and EasyOCR can be more accurate on some scripts but have weaker or unverified Kinyarwanda support and heavier dependencies. Evaluate them on the test set before adopting; do not assume.

### 5.6 OCRmyPDF configuration
```bash
ocrmypdf -l eng+kin \
  --rotate-pages --deskew --clean \
  --output-type pdf --optimize 1 \
  --jobs 4 --sidecar out.txt \
  --skip-text \
  input.pdf output.pdf
```
Notes: `--clean` requires `unpaper`; `--clean-final` also uses the cleaned image in the output; `--force-ocr` rasterizes text pages; `--redo-ocr` replaces a bad existing text layer; `--tesseract-timeout` stops runaway pages.

## 6. Data Specification

### 6.1 JSON schema (version 1)
See `schema/ocr_output.example.json` for a complete example.

Coordinates are in pixels of the page image, origin top-left. Sentence grouping may be added in Part Two without breaking this schema. Any change to the schema increments `schema_version`.

### 6.2 Database tables (initial)
`documents` (id, filename, status, languages, created_at, expires_at), `pages` (document_id, page_no, status, avg_confidence), `corrections` (document_id, page_no, word_id, original, corrected).

## 7. API Specification

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/documents` | Upload files and options; returns a job id |
| GET | `/api/documents/{id}` | Status, progress, per-page confidence |
| GET | `/api/documents/{id}/pages/{n}` | Page image and word data |
| PATCH | `/api/documents/{id}/pages/{n}/words` | Submit corrections |
| POST | `/api/documents/{id}/rebuild` | Regenerate outputs after corrections |
| GET | `/api/documents/{id}/download?type=searchable\|clean\|json\|txt\|zip` | Download outputs |
| DELETE | `/api/documents/{id}` | Delete everything immediately |
| GET | `/api/health` | Health check for Docker and monitoring |

Errors use consistent JSON (`code`, `message`). OpenAPI documentation is generated by FastAPI.

## 8. Docker and Deployment

### 8.1 Dockerfile (backend and worker)
See `backend/Dockerfile` and `backend/requirements.txt`. Pin exact versions once the project works.

### 8.2 docker-compose.yml
See `docker-compose.yml`. The `web` service is commented out until the frontend exists.

### 8.3 Deployment notes
- Develop in WSL2 or Docker Desktop; avoid installing Tesseract natively on Windows.
- Add a cleanup job (cron or RQ scheduler) that deletes expired files.
- Production: reverse proxy with HTTPS (Caddy gives automatic certificates), memory and CPU limits per container, and a size limit on the proxy.
- Scale by adding worker replicas; OCR is CPU-bound.

## 9. Non-Functional Requirements

### 9.1 Performance (targets to validate)
- A 10-page clean book PDF completes within a few minutes on a 4-core machine.
- The upload request returns immediately; processing never blocks the API.
- Memory stays bounded by processing pages one at a time, not loading entire books as images.

### 9.2 Accuracy (targets to validate)
- Clean printed English: CER at or below 2%.
- Poor scans and Kinyarwanda: measure the baseline first, then set targets from real results.
- Reading order correct on single-column pages in the test set; newspapers measured separately.

### 9.3 Security
- Validate content type, enforce size, page, and pixel limits (protection against decompression and PDF bombs).
- Run containers as a non-root user; keep Ghostscript, Tesseract, and base images updated, since they parse untrusted files.
- Store files under random identifiers; never trust user filenames in paths.
- Rate-limit uploads; configure CORS strictly.

### 9.4 Privacy
- Automatic deletion after the retention period; a delete button for immediate removal.
- No document text in application logs.
- A short plain-language notice about retention.

### 9.5 Accessibility and usability
- Responsive, touch-friendly layout; camera capture on phones.
- Keyboard and screen-reader support, sufficient contrast, plain language.
- The clean text PDF must be a tagged, selectable PDF where practical.

### 9.6 Reliability and maintainability
- Idempotent jobs; a failed page does not destroy the whole document.
- Structured logging, a health endpoint, and automated tests in CI.
- Typed code (type hints, TypeScript) and a linter (ruff, ESLint).

## 10. Testing and Evaluation

### 10.1 Test set
About 20 pages across five categories: clean printed English, clean printed Kinyarwanda, poor scans (faded, skewed, shadowed), phone photos, and newspaper columns. Type the ground truth by hand for at least 10 pages and store it in the repository (respecting copyright).

### 10.2 Metrics
CER and WER with `jiwer`, reading-order correctness (manual check), processing time per page, and low-confidence rate.

### 10.3 Test types
- **Unit:** preprocessing functions, hyphen joining, header removal, JSON building.
- **Integration:** upload to download through Docker Compose.
- **Regression:** the test set runs in CI so every change shows its accuracy effect.
- **Manual:** real phones and slow connections.

## 11. Project Structure and Plan

### 11.1 Repository layout
```
scan-to-text/
  backend/app/{api, core, ocr, preprocess, outputs, jobs, models}/
  backend/tests/
  frontend/src/
  eval/{samples, ground_truth, run_eval.py}
  schema/
  scripts/
  docker-compose.yml
  docs/SRS.md
```

### 11.2 Milestones
| Phase | Work | Done when |
|---|---|---|
| 1 | Docker image with Tesseract and OCRmyPDF; run on one page | Searchable PDF created from a scan |
| 2 | Script for words, boxes, and JSON; test set and evaluation | CER numbers recorded |
| 3 | Preprocessing (deskew, cleanup, spread split) | Measured improvement on poor scans |
| 4 | FastAPI, Redis queue, job states | Upload to results by API |
| 5 | Clean text PDF with reading order | Readable document from a book chapter |
| 6 | React interface and correction screen | Full flow works on a phone |
| 7 | Security, retention, CI, documentation | Release candidate |
| 8 | Later: Arabic, fine-tuning, PWA polish | Planned separately |

## 12. Risks
| Risk | Impact | Mitigation |
|---|---|---|
| Kinyarwanda model accuracy is low | High | Measure early; fine-tune with corrected pages; offer correction UI |
| Reading order wrong on columns | High | Column detection first; evaluate layout models; scope newspapers later |
| Installation problems on Windows | Medium | Docker and WSL2 from day one |
| Large books are slow or exhaust memory | Medium | Page-by-page processing, queue, limits |
| Malicious or malformed uploads | Medium | Validation, limits, non-root containers, updates |
| Licensing of models, fonts, or test material | Medium | Check licenses; use open fonts and sample documents |
| Scope creep into Part Two | Medium | Keep TTS, translation, and animation out until Part One passes acceptance |

## 13. Interface with Part Two
Part Two reads the JSON (words, boxes, lines, paragraphs) and the searchable PDF. It adds sentence grouping, speech synthesis, translation, and interaction on top. For that reason the schema is versioned, coordinates are documented, and corrections are stored so that Part Two works from the best available text.

## 14. Acceptance Criteria for Part One
1. A scanned PDF and a phone photo of a printed page each produce a searchable PDF, a clean text PDF, and a JSON file.
2. Text in the outputs can be selected, highlighted, searched, and copied on desktop and phone.
3. The evaluation report shows CER and WER on the test set for English and Kinyarwanda.
4. Pages with low confidence are flagged and can be corrected, and the outputs can be rebuilt.
5. The whole system starts with `docker compose up` and passes automated tests.
6. Uploaded files are deleted after the retention period.
