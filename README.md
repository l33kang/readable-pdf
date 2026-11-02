# Scan-to-Text Converter

A web application that converts scanned documents and images into readable digital documents using OCR.

## Overview

Scanned documents are often stored as images, making their text difficult to search, select, or edit. This project uses Optical Character Recognition (OCR) to extract text and provide different output formats.

## Features

- Extract text from scanned PDFs and images.
- Generate searchable PDFs while preserving the original page appearance.
- Create clean PDFs containing reconstructed text.
- Export extracted text as `.txt` files.
- Detect possible OCR errors and suggest word corrections.
- Review, accept, or reject correction suggestions.
- Store processing results in persistent Docker storage.

## Technology Stack

- **Backend:** Python, FastAPI
- **OCR:** Tesseract, pytesseract, OCRmyPDF
- **PDF processing:** PyMuPDF, ReportLab
- **Frontend:** React, Vite
- **Background jobs:** RQ, Redis
- **Deployment:** Docker Compose

## Getting Started

### Requirements

- Docker Desktop
- Docker Compose
- Node.js and npm

### Run the application

Clone the repository:

```bash
git clone https://github.com/l33kang/readable-pdf.git
cd scan-to-text
```

Start the backend services:

```bash
docker compose up --build -d
```

Start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open the frontend at:

```text
http://localhost:5173
```

The API documentation is available at:

```text
http://localhost:8000/docs
```

## Project Structure

```text
scan-to-text/
├── backend/
│   └── app/
│       ├── ocr_engine.py
│       ├── clean_pdf.py
│       ├── processing.py
│       ├── tasks.py
│       └── upload.py
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

## Output Formats

| Format | Description |
|---|---|
| Searchable PDF | Original appearance with searchable text |
| Simple PDF | Reconstructed document containing readable text |
| Text document | Extracted text in `.txt` format |

## Current Status

The application supports document uploads, OCR processing, correction review, and downloading results in all three output formats.

Further work will focus on improving OCR accuracy, document layout reconstruction, and the overall reading experience.
