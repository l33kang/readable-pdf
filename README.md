# readable-pdf

**Turn scanned books and photos of printed text into real, selectable, searchable PDFs, plus a clean, readable version for people who struggle with scans.**

> **Status: early development.** The design is complete (see [`docs/SRS.md`](docs/SRS.md)) and the Docker setup is ready. The processing pipeline is being built. Nothing here is production-ready yet.

---

## Why this exists

This project started with an elderly woman selling corn on the street who could not read or write. It made me think about how much knowledge, news, and stories are closed off from people who cannot access the written word.

A related problem is far more common. Many books and documents are distributed as scanned PDFs, where every page is only a picture. You cannot highlight a sentence, search for a word, copy a paragraph, or enlarge the text without blurring it. Readers who already find reading difficult are hit hardest, because faded, small scan text is often the barrier itself. Many phones also cannot copy text out of a photo of a newspaper or a printed page.

`readable-pdf` fixes the first step: getting real text out of the picture.

## What it produces

From a scanned PDF or a set of photos, the tool creates:

| Output | Description |
|---|---|
| **Searchable PDF** | Keeps the original look of each page and adds an accurate invisible text layer, so text can be selected, highlighted, searched, and copied. |
| **Clean text PDF** | A new document built from the recognized text, with a readable font, adjustable size and spacing, and correct reading order. Designed for readers who struggle with the original scan. |
| **Structured JSON** | Every word with its position, confidence, and its line and paragraph. This is the foundation for Part Two. |

Plain text export and a ZIP of all outputs are also planned.

## Why not use existing tools?

Tools like OCRmyPDF, Adobe Acrobat, Google Drive, and Apple Live Text each solve part of the problem. Most only add an invisible text layer behind the scan, so the page still looks like a scan. Some produce messy editable documents, require payment or an internet connection, or produce no file at all. Support for languages like Kinyarwanda, and for users on low-cost phones, is limited.

This project builds on those tools (OCRmyPDF and Tesseract are used for the searchable PDF) and adds what is missing: the clean, readable output, word-level data, correction of OCR mistakes, and a focus on Kinyarwanda and low-cost devices.

## Scope

**In scope for Part One**
- Printed text only (no handwriting)
- English and Kinyarwanda first
- PDF and image input (JPG, PNG, TIFF)
- Image cleanup: rotation, deskew, noise and contrast correction
- Correction of recognition mistakes
- Web interface and REST API, deployed with Docker

**Planned later:** Arabic (right-to-left, connected script makes recognition and layout much harder), Tesseract fine-tuning for Kinyarwanda, and a phone-friendly installable web app.

**Not in Part One:** text-to-speech, translation, and interactive or animated text (see Part Two below).

## How it works

```
Upload (PDF or photos)
   -> split into page images
   -> clean up (rotate, deskew, denoise, contrast)
   -> OCR with Tesseract (words, positions, confidence)
   -> rebuild outputs: searchable PDF / clean text PDF / JSON
```

Long documents run as background jobs, so uploads return immediately and progress can be followed per page.

## Tech stack

| Area | Tools |
|---|---|
| Backend | Python, FastAPI |
| OCR | Tesseract 5 (LSTM), OCRmyPDF, pytesseract |
| Image and PDF processing | OpenCV, Pillow, PyMuPDF, pikepdf, ReportLab |
| Jobs | Redis, RQ |
| Data | SQLite (PostgreSQL later) |
| Frontend (planned) | React, TypeScript, PDF.js |
| Packaging | Docker, Docker Compose |
| Evaluation | pytest, jiwer (character and word error rate) |

## Getting started

**Requirements:** Docker and Docker Compose. On Windows, use WSL2 or Docker Desktop rather than installing Tesseract natively.

```bash
git clone https://github.com/l33kang/readable-pdf.git
cd readable-pdf

# Build the backend image (installs Tesseract, Ghostscript, and language data)
docker compose build api

# Check that the OCR language models are installed (expect eng, kin, ara)
docker compose run --rm api tesseract --list-langs
```

To try the first step on a single scanned PDF with OCRmyPDF:

```bash
./scripts/ocr_one.sh input.pdf output.pdf
```

> The Kinyarwanda model (`kin`) is downloaded during the image build. Its accuracy has not been measured yet, so treat early Kinyarwanda results with caution.

Copy `.env.example` to `.env` to change limits such as maximum upload size and file retention time.

## Project structure

```
readable-pdf/
  backend/          API, worker, OCR and output code (Dockerfile, requirements)
  frontend/         Web interface (planned)
  eval/             Test pages and hand-typed ground truth
  schema/           JSON output format (version 1)
  scripts/          Helper scripts
  docs/SRS.md       Full requirements and design
  docker-compose.yml
```

## Measuring quality

Accuracy is measured, not assumed. A small test set covers clean books, poor scans, phone photos, newspapers, and Kinyarwanda pages. Recognized text is compared with hand-typed versions using character error rate (CER) and word error rate (WER), and the results will be published in this repository.

Part One is complete when a poor scan goes in and a clean, selectable, correctly ordered document comes out.

## Privacy

Uploaded documents may be personal. Files are stored under random identifiers, deleted automatically after a retention period (24 hours by default), and can be deleted immediately on request. Document text is not written to logs.

## Roadmap

- [x] Requirements specification and architecture
- [x] Docker setup
- [ ] Searchable PDF from a scan (OCRmyPDF)
- [ ] Word-level JSON and evaluation test set
- [ ] Image preprocessing
- [ ] API and background jobs
- [ ] Clean text PDF with correct reading order
- [ ] Web interface with correction screen
- [ ] Arabic support, Kinyarwanda fine-tuning, installable phone app

## Part Two

Once text and word positions exist, a second project can build on them: reading text aloud, translating it into the reader's own language (for example Kinyarwanda, English, or Arabic), and interactive effects as the reader touches or moves over the words. These are deliberately left out of Part One so the foundation is solid first.

## Contributing

Ideas, bug reports, and test pages are welcome, especially printed Kinyarwanda pages you are allowed to share. Please open an issue before starting large changes.

## License

To be decided. Check the licenses of Tesseract, OCRmyPDF, language data, and any fonts or sample documents before choosing one.

## Author

**Ali Salaheldin**, Computer Science (Software Engineering) student, INES-Ruhengeri, Kigali, Rwanda.
[GitHub](https://github.com/l33kang) · [LinkedIn](https://www.linkedin.com/in/ali-salaheldin-08a5293b6/)
