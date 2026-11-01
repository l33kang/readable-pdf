
import json
from pathlib import Path


def load_ocr_output(file_path: Path) -> dict:
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def test_document_structure():
    data = {
        "schema_version": 1,
        "document_id": "test-document",
        "languages": ["eng"],
        "pages": []
    }

    assert data["schema_version"] == 1
    assert isinstance(data["document_id"], str)
    assert isinstance(data["languages"], list)
    assert isinstance(data["pages"], list)


def test_page_structure():
    page = {
        "page": 1,
        "width": 1000,
        "height": 1500,
        "dpi": 300,
        "blocks": []
    }

    for field in ["page", "width", "height", "dpi", "blocks"]:
        assert field in page


def test_word_structure():
    word = {
        "id": "w1",
        "text": "Hello",
        "bbox": [10, 20, 100, 50],
        "conf": 96.0,
        "corrected": False
    }

    assert isinstance(word["id"], str)
    assert isinstance(word["text"], str)
    assert len(word["bbox"]) == 4
    assert isinstance(word["conf"], (int, float))
    assert isinstance(word["corrected"], bool)


def test_sample_ocr_output():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "sample_ocr_output.json"
    )

    data = load_ocr_output(fixture_path)

    assert data["schema_version"] == 1
    assert data["document_id"] == "test-document"
    assert len(data["pages"]) == 1

    for page in data["pages"]:
        assert page["page"] >= 1
        assert page["width"] > 0
        assert page["height"] > 0
        assert page["dpi"] > 0

        for block in page["blocks"]:
            assert block["id"]

            x1, y1, x2, y2 = block["bbox"]
            assert 0 <= x1 < x2 <= page["width"]
            assert 0 <= y1 < y2 <= page["height"]

            for paragraph in block["paragraphs"]:
                assert paragraph["id"]

                for line in paragraph["lines"]:
                    assert line["id"]

                    x1, y1, x2, y2 = line["bbox"]
                    assert 0 <= x1 < x2 <= page["width"]
                    assert 0 <= y1 < y2 <= page["height"]

                    for word in line["words"]:
                        assert word["id"]
                        assert word["text"].strip()

                        x1, y1, x2, y2 = word["bbox"]
                        assert 0 <= x1 < x2 <= page["width"]
                        assert 0 <= y1 < y2 <= page["height"]

                        assert 0 <= word["conf"] <= 100
                        assert isinstance(word["corrected"], bool)
