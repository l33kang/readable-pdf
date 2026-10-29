FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-ara \
    ghostscript qpdf unpaper pngquant \
    libgl1 libglib2.0-0 curl \
 && rm -rf /var/lib/apt/lists/*
# Best-quality models; confirm the tessdata path with: tesseract --list-langs
ARG TESSDATA=/usr/share/tesseract-ocr/5/tessdata
RUN curl -L -o $TESSDATA/kin.traineddata \
    https://github.com/tesseract-ocr/tessdata_best/raw/main/kin.traineddata \
 && curl -L -o $TESSDATA/eng.traineddata \
    https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m appuser && mkdir -p /data && chown appuser /data
USER appuser
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
