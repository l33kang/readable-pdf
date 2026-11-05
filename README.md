# scanablePDF

**Turn scanned books, documents, and photographs into readable, searchable digital documents.**

scanablePDF is an OCR-powered web application that transforms scanned PDFs and images into accessible digital documents. It extracts printed text while providing different output formats depending on whether users want to preserve the original appearance, obtain a clean reconstructed document, or edit the extracted text.

## Why scanablePDF?

Many books, historical documents, and printed materials exist only as scanned images. Their contents cannot easily be searched, selected, copied, or edited.

scanablePDF aims to make these documents more accessible by converting scanned pages into usable digital text while preserving the original document when needed.

## Features

- **Searchable PDF:** Preserve the original page appearance while adding an invisible OCR text layer for searching and selecting text.
- **Simple PDF:** Reconstruct extracted text into a clean, readable PDF.
- **Text Export:** Export recognized content as an editable `.txt` file.
- **OCR Correction Review:** Review potentially incorrect OCR words and apply correction suggestions for text-based outputs.
- **Multi-format Input:** Process scanned PDFs and common image formats.
- **English and Kinyarwanda OCR:** Tesseract is configured with English and Kinyarwanda language data.
- **Reading Order Reconstruction:** Reorganize OCR results using document geometry to improve reading order, including multi-column documents.
- **Word-level OCR Data:** Extract recognized words together with bounding boxes, confidence scores, and correction status.
- **Background Processing:** Run document processing asynchronously using Redis and RQ.
- **Persistent Storage:** Store uploaded documents and generated results using Docker volumes.

## Output Formats

| Format | Purpose |
|---|---|
| Searchable PDF | Original appearance with searchable/selectable OCR text |
| Simple PDF | Clean PDF reconstructed from extracted text |
| Text Document | Editable plain-text output |

The internal OCR representation also includes structured word-level information such as text, confidence, bounding boxes, and correction status.

## Technology Stack

| Component | Technology |
|---|---|
| Backend | Python, FastAPI |
| OCR Engine | Tesseract, pytesseract |
| PDF Processing | OCRmyPDF, PyMuPDF, ReportLab |
| Image Processing | Pillow, OpenCV |
| Background Jobs | RQ, Redis |
| Frontend | React, Vite |
| Deployment | Docker Compose |

## Architecture

The application follows a document-processing pipeline:

```text
Browser / React Frontend
          │
          ▼
       FastAPI
          │
          ▼
      Redis Queue
          │
          ▼
       RQ Worker
          │
          ▼
   Document Processing
          │
     ┌────┴────┐
     ▼         ▼
 Preprocessing OCR Engine
               │
               ▼
        Reading Order
               │
               ▼
      Output Generation
       ┌──────┼──────┐
       ▼      ▼      ▼
 Searchable  Simple  Text
    PDF        PDF   Output
```

### Processing Flow

1. **Upload:** The user uploads a scanned PDF or image.
2. **Validation:** The backend validates and stores the uploaded document.
3. **Job Creation:** A background processing job is submitted through Redis/RQ.
4. **OCR:** Tesseract extracts printed text and word-level information.
5. **Reading Order:** OCR blocks are reordered using their geometric positions to improve document reading order.
6. **Output Generation:** The system generates the requested Searchable PDF, Simple PDF, or Text output.
7. **Correction Review:** For supported text-based outputs, users can review OCR correction suggestions.
8. **Download:** The generated document becomes available through the API and web interface.

## API

The backend exposes REST API endpoints for document processing:

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/documents/upload` | Upload a document |
| POST | `/api/documents/{document_id}/process` | Start document processing |
| GET | `/api/jobs/{job_id}` | Check processing status |
| GET | `/api/documents/{document_id}` | Retrieve document status/results |
| GET | `/api/documents/{document_id}/download?type=...` | Download generated output |
| GET | `/api/documents/{document_id}/corrections` | Retrieve correction information |
| POST | `/api/documents/{document_id}/corrections/bulk` | Apply multiple corrections |
| POST | `/api/documents/{document_id}/corrections/{correction_id}` | Update a correction |
| GET | `/api/health` | Check API health |

Interactive API documentation is available through FastAPI at `/docs`.

## Getting Started

### Requirements

- Docker Desktop
- Docker Compose
- Node.js and npm

### 1. Clone the repository

```bash
git clone https://github.com/l33kang/scanable-pdf.git
cd scanable-pdf
```

### 2. Start the backend

From the project root:

```bash
docker compose up --build -d
```

This starts:

- FastAPI API
- RQ OCR worker
- Redis

Verify the services with:

```bash
docker compose ps
```

Check API health:

```bash
curl http://localhost:8000/api/health
```

Expected response:

```json
{
  "status": "healthy"
}
```

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
scanable-pdf/
├── backend/
│   ├── app/
│   │   ├── ocr_engine.py
│   │   ├── reading_order.py
│   │   ├── clean_pdf.py
│   │   ├── processing.py
│   │   ├── tasks.py
│   │   └── upload.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/
│   └── src/
│
├── docs/
│   └── SRS.md
│
├── schema/
│   └── ocr_output.example.json
│
├── eval/
│   ├── ground_truth/
│   └── ...
│
├── scripts/
├── docker-compose.yml
└── README.md
```

## Evaluation

The project includes an OCR benchmark covering several document layouts, including:

- Normal printed pages
- Small-font documents
- Two-column documents
- Grid tables
- Borderless tables
- Mixed layouts

Reading-order evaluation across the six benchmark documents produced:

| Metric | Result |
|---|---:|
| Character Error Rate (CER) | 28.52% |
| Word Error Rate (WER) | 32.77% |

The reading-order implementation significantly improved extraction of multi-column documents compared with the earlier baseline.

For example, the two-column benchmark improved from approximately **62.47% CER** with the earlier baseline to **4.44% CER** after reading-order reconstruction.

### Limitations

OCR accuracy depends strongly on the quality and layout of the input document.

Current limitations include:

- Small or low-quality text can produce higher OCR error rates.
- Complex tables remain difficult to reconstruct accurately.
- Grid-based tables can significantly reduce OCR accuracy because table lines interfere with character recognition.
- OCR results may require human correction for difficult documents.
- The current system is primarily designed for **printed text**, rather than handwriting.

## Project Status

scanablePDF currently supports:

- PDF and image uploads
- English and Kinyarwanda OCR configuration
- OCR-based text extraction
- Word-level OCR information
- Reading-order reconstruction
- Searchable PDF generation
- Clean PDF reconstruction
- Plain-text export
- OCR correction review
- Asynchronous processing with Redis/RQ
- Dockerized backend, worker, and Redis services
- React web interface
- REST API

The complete document-processing pipeline has been tested using both generated test documents and a real scanned PDF.

## Roadmap

Potential future improvements include:

- Improving OCR accuracy on low-quality and multilingual documents.
- Better preservation of complex document structure.
- Improved table detection and reconstruction.
- More advanced accessibility features.
- Support for additional languages.
- Performance optimization for large documents.
- Improved preprocessing for difficult scans.

## Contributing

Contributions, suggestions, and bug reports are welcome.

If you find an issue or have an idea for improving scanablePDF, feel free to open an issue or submit a pull request.

---

**scanablePDF — Making scanned knowledge readable again.**