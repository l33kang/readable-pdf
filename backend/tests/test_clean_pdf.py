
from app.clean_pdf import extract_paragraph_text, is_heading


def test_hyphenated_word_reconstruction():
    paragraph = {
        "lines": [
            {"words": [{"text": "walk-"}]},
            {"words": [{"text": "ing"}, {"text": "home"}]},
        ]
    }

    assert extract_paragraph_text(paragraph) == "walking home"


def test_normal_line_reconstruction():
    paragraph = {
        "lines": [
            {"words": [{"text": "She"}, {"text": "opened"}, {"text": "the"}, {"text": "door"}]},
            {"words": [{"text": "and"}, {"text": "entered"}, {"text": "the"}, {"text": "room."}]},
        ]
    }

    assert extract_paragraph_text(paragraph) == (
        "She opened the door and entered the room."
    )


def test_empty_paragraph():
    assert extract_paragraph_text({"lines": []}) == ""


def test_chapter_heading():
    assert is_heading("Chapter Two") is True


def test_title_case_heading():
    assert is_heading("Four Sisters") is True


def test_uppercase_heading():
    assert is_heading("THE MARCH FAMILY") is True


def test_normal_sentence_is_not_heading():
    assert is_heading("She went to the garden") is False


def test_sentence_with_punctuation_is_not_heading():
    assert is_heading("The End.") is False

from app.clean_pdf import is_running_header


def test_running_header_detected():
    paragraph = {
        "lines": [
            {
                "words": [
                    {"text": "Little", "bbox": [620, 153, 721, 188]},
                    {"text": "Women", "bbox": [735, 154, 878, 188]},
                ]
            }
        ]
    }

    assert is_running_header(paragraph, 2330) is True


def test_body_paragraph_not_header():
    paragraph = {
        "lines": [
            {
                "words": [
                    {"text": "Then", "bbox": [237, 308, 338, 344]},
                    {"text": "Meg", "bbox": [347, 311, 435, 354]},
                ]
            }
        ]
    }

    assert is_running_header(paragraph, 2330) is False