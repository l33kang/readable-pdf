#!/usr/bin/env bash
# Phase 1 test: make a searchable PDF from one scanned PDF.
# Usage: ./scripts/ocr_one.sh input.pdf output.pdf
set -e
ocrmypdf -l eng+kin --rotate-pages --deskew --clean \
  --output-type pdf --optimize 1 --jobs 4 \
  --sidecar "${2%.pdf}.txt" --skip-text "$1" "$2"
