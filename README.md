# readablePDF

**Turn scanned books, documents, and photographs into readable, searchable digital documents.**

readablePDF is an OCR-powered web application that transforms scanned PDFs and images into accessible digital documents. It extracts text while offering different output formats depending on whether users want to preserve the original appearance, obtain a clean reconstructed document, or edit the extracted text.

## Why readablePDF?

Many books, historical documents, and printed materials exist only as scanned images. Their contents cannot easily be searched, selected, copied, or edited.

readablePDF aims to make these documents more accessible by converting scanned pages into usable digital text while preserving the original document when needed.

## Features

- **Searchable PDF:** Preserve the original page appearance while adding an invisible OCR text layer for searching and selecting text.
- **Simple PDF:** Reconstruct extracted text into a clean, readable PDF.
- **Text Export:** Export recognized content as an editable `.txt` file.
- **OCR Correction Review:** Detect potentially incorrect OCR words and allow users to accept or reject correction suggestions for text-based outputs.
- **Multi-format Input:** Process scanned PDFs and common image formats.
- **Background Processing:** Run document processing asynchronously using Redis and RQ.
- **Persistent Storage:** Store uploaded documents and generated results using Docker volumes.

## Output Formats

| Format | Purpose |
|---|---|
| Searchable PDF | Original appearance with searchable text |
| Simple PDF | Clean PDF reconstructed from extracted text |
| Text Document | Editable plain-text output |

## Technology Stack

| Component | Technology |
|---|---|
| Backend | Python, FastAPI |
| OCR Engine | Tesseract, pytesseract |
| PDF Processing | OCRmyPDF, PyMuPDF, ReportLab |
| Frontend | React, Vite |
| Background Jobs | RQ, Redis |
| Deployment | Docker Compose |

## Architecture

The application follows a simple document-processing pipeline:

1. **Upload:** The user uploads a scanned PDF or image.
2. **Processing:** The backend validates the document and submits a background job.
3. **OCR:** The OCR engine extracts text and word-level information.
4. **Reconstruction:** Depending on the selected format, the system generates the requested output.
5. **Correction Review:** For Simple PDF and Text Document outputs, users can review suggested corrections.
6. **Download:** The generated document becomes available for download.

## Getting Started

### Requirements

- Docker Desktop
- Docker Compose
- Node.js and npm

### 1. Clone the repository

```bash
git clone https://github.com/l33kang/readable-pdf.git
cd readable-pdf
```

### 2. Start the backend

From the project root:

```bash
docker compose up --build -d
```

This starts the API, background worker, and Redis services.

### 3. Start the frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

### 4. Open the application

- **Frontend:** http://localhost:5173
- **API:** http://localhost:8000
- **API Documentation:** http://localhost:8000/docs

## Project Structure

```text
readable-pdf/
├── backend/
│   ├── app/
│   │   ├── ocr_engine.py
│   │   ├── clean_pdf.py
│   │   ├── processing.py
│   │   ├── tasks.py
│   │   └── upload.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   └── src/
├── docs/
│   └── SRS.md
├── schema/
│   └── ocr_output.example.json
├── eval/
├── scripts/
├── docker-compose.yml
└── README.md
```

## Project Status

readablePDF currently supports:

- Document and image uploads.
- OCR-based text extraction.
- Searchable PDF generation.
- Clean PDF reconstruction.
- Plain-text export.
- OCR correction suggestions and review.
- Asynchronous processing and document downloads.

## Roadmap

Potential areas of future development include:

- Improving OCR accuracy, especially for multilingual documents.
- Better preservation of document structure and layout.
- More advanced reading and accessibility features.
- Improved handling of complex page layouts.
- Performance optimization for large documents.

## Contributing

Contributions, suggestions, and bug reports are welcome.

If you find an issue or have an idea for improving readablePDF, feel free to open an issue or submit a pull request.

---

**readablePDF — Making scanned knowledge readable again.**
