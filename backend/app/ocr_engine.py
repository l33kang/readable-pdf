import os
import json
import pytesseract
from PIL import Image


def extract_text(image_path: str, languages: str = "eng") -> str:
    """Extract the complete text from an image."""
    image = Image.open(image_path)
    text = pytesseract.image_to_string(image, lang=languages)
    return text.strip()


def extract_blocks(image_path: str, languages: str = "eng") -> list[dict]:
    """Extract OCR results organized into blocks, paragraphs and lines."""

    image = Image.open(image_path)

    data = pytesseract.image_to_data(
        image,
        lang=languages,
        output_type=pytesseract.Output.DICT,
    )

    blocks = []
    block_map = {}

    for i, word in enumerate(data["text"]):
        word = word.strip()
        confidence = float(data["conf"][i])

        if not word or confidence < 0:
            continue

        block_num = data["block_num"][i]
        par_num = data["par_num"][i]
        line_num = data["line_num"][i]

        block_key = block_num
        paragraph_key = (block_num, par_num)
        line_key = (block_num, par_num, line_num)

        x1 = data["left"][i]
        y1 = data["top"][i]
        x2 = x1 + data["width"][i]
        y2 = y1 + data["height"][i]

        if block_key not in block_map:
            block = {
                "id": f"b{len(blocks) + 1}",
                "type": "text",
                "bbox": [x1, y1, x2, y2],
                "paragraphs": [],
                "_paragraph_map": {},
            }
            blocks.append(block)
            block_map[block_key] = block

        block = block_map[block_key]

        if paragraph_key not in block["_paragraph_map"]:
            paragraph = {
                "id": f"p{sum(len(b['paragraphs']) for b in blocks) + 1}",
                "lines": [],
                "_line_map": {},
            }
            block["paragraphs"].append(paragraph)
            block["_paragraph_map"][paragraph_key] = paragraph

        paragraph = block["_paragraph_map"][paragraph_key]

        if line_key not in paragraph["_line_map"]:
            line = {
                "id": f"l{sum(len(p['lines']) for b in blocks for p in b['paragraphs']) + 1}",
                "bbox": [x1, y1, x2, y2],
                "words": [],
            }
            paragraph["lines"].append(line)
            paragraph["_line_map"][line_key] = line

        line = paragraph["_line_map"][line_key]

        line["words"].append({
            "id": f"w{sum(len(l['words']) for b in blocks for p in b['paragraphs'] for l in p['lines']) + 1}",
            "text": word,
            "bbox": [x1, y1, x2, y2],
            "conf": round(confidence, 1),
            "corrected": False,
        })

        # Expand the line and block bounding boxes as words are added.
        line["bbox"] = [
            min(line["bbox"][0], x1),
            min(line["bbox"][1], y1),
            max(line["bbox"][2], x2),
            max(line["bbox"][3], y2),
        ]

        block["bbox"] = [
            min(block["bbox"][0], x1),
            min(block["bbox"][1], y1),
            max(block["bbox"][2], x2),
            max(block["bbox"][3], y2),
        ]

    # Remove internal dictionaries used for grouping.
    for block in blocks:
        del block["_paragraph_map"]
        for paragraph in block["paragraphs"]:
            del paragraph["_line_map"]

    return blocks

def extract_document(image_path: str) -> dict:
    """Extract document text and structured OCR data."""
    return {
        "languages": ["eng"],
        "text": extract_text(image_path),
        "blocks": extract_blocks(image_path),
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