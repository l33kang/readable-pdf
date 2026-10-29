import os
import json
import pytesseract
from PIL import Image


def extract_text(image_path: str) -> str:
    """Extract the complete text from an image."""
    image = Image.open(image_path)
    text = pytesseract.image_to_string(image, lang="eng")
    return text.strip()


def extract_words(image_path: str) -> list[dict]:
    """Extract words, confidence scores, and bounding boxes."""
    image = Image.open(image_path)

    data = pytesseract.image_to_data(
        image,
        lang="eng",
        output_type=pytesseract.Output.DICT,
    )

    words = []

    for i, word in enumerate(data["text"]):
        word = word.strip()
        confidence = float(data["conf"][i])

        if not word or confidence < 0:
            continue

        words.append({
            "text": word,
            "confidence": confidence,
            "needs_review": confidence < 70,
            "bbox": {
                "x": data["left"][i],
                "y": data["top"][i],
                "width": data["width"][i],
                "height": data["height"][i],
            },
        })

    return words

def extract_document(image_path: str) -> dict:
    """Extract document text and structured word data"""
    return {
        "language": "eng",
        "text": extract_text(image_path),
        "words": extract_words(image_path),
    }

def save_document_json( image_path: str, output_path: str | None = None) -> str:
    """Save structured OCR output as a JSON file."""
    result = extract_document(image_path)

    if output_path is None:
        data_dir = os.getenv("DATA_DIR", "/data")
        os.makedirs(data_dir, exist_ok=True)
        output_path = os.path.join(data_dir, "ocr-result.json")

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(result, file, indent=2, ensure_ascii=False)

    return output_path