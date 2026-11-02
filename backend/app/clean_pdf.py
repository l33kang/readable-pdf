"""Clean (reflowable) PDF generation from word-level OCR data.

Pipeline (each stage testable without producing a PDF):

1. build_elements(ocr_data, config) -> BuildResult
   - word-level and paragraph-level OCR confidence analysis
   - paragraph quality scoring (suspicious OCR fragments)
   - image-related text detection (figure overlap + noise clusters)
   - projection-based reading order (columns, spanning blocks, RTL option)
   - header/footer/page-number removal
   - scored heading classification
   - geometry-aware paragraph merging
   - removal report: everything discarded or flagged, with scores
2. render_pdf(elements, output_path, config)
3. to_markdown() / to_text() / format_report() / write_report()

Docker: fonts are needed for rendering. Add to the Dockerfile:
    apt-get install -y --no-install-recommends fonts-dejavu-core
"""
from __future__ import annotations

import json
import logging
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from html import escape
from pathlib import Path
from typing import Iterable, Optional

try:
    from wordfreq import zipf_frequency
except ImportError:
    zipf_frequency = None

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate

log = logging.getLogger(__name__)

SENTENCE_END = (".", "?", "!", "\u2026", "\u201d", "\u00bb", '"')
_PAGE_NUMBER = re.compile(r"^[\W_]*(\d{1,4}|[ivxl]{1,6})[\W_]*$")
_PUNCT = set(".,;:!?\"'()[]{}\u2026-\u2013\u2014/&%+=*\u2022\u00a7\u201c\u201d\u2018\u2019\u00ab\u00bb")
_SINGLE_OK = {"a", "i", "o", "u", "y", "e"}

_FONT_CANDIDATES = [
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
    ),
    (
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
    ),
    (
        "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSerif-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSerif-Italic.ttf",
    ),
    (
        "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSerifItalic.ttf",
    ),
]


# --------------------------------------------------------------------------
# Data classes
# --------------------------------------------------------------------------
@dataclass
class Element:
    kind: str  # "heading" | "paragraph" | "figure"
    text: str
    source_page: int  # original scanned page where the element starts
    quality: Optional[float] = None
    flags: list[str] = field(default_factory=list)
    geom: Optional[dict] = field(default=None, repr=False)


@dataclass
class Removed:
    page: int
    text: str
    reason: str
    level: str = "paragraph"  # "paragraph" | "word"
    bbox: Optional[list] = None
    scores: dict = field(default_factory=dict)


@dataclass
class BuildResult:
    elements: list[Element]
    removed: list[Removed] = field(default_factory=list)
    flagged: list[Removed] = field(default_factory=list)  # kept but suspicious
    corrections: list[dict] = field(default_factory=list)


@dataclass
class CleanConfig:
    # Typography
    font_size: float = 12.0
    line_spacing: float = 1.5
    align: str = "left"  # "left" or "justify"
    font_path: Optional[str] = None
    bold_font_path: Optional[str] = None
    italic_font_path: Optional[str] = None

    # OCR confidence (Tesseract scale 0-100; negative/missing = unknown)
    word_conf_drop: float = 25.0  # junk words below this are removed
    word_conf_warn: float = 50.0  # words below this count as low confidence
    drop_junk_words: bool = True

    # Paragraph quality score (0-1)
    min_quality_drop: float = 0.40  # below: paragraph discarded
    min_quality_flag: float = 0.60  # below: kept but flagged in the report

    # Image-related text
    figure_overlap: float = 0.6  # share of a paragraph inside a figure box
    figure_text_quality: float = 0.75  # text inside a figure below this is dropped
    figure_short_words: int = 4  # short text inside a figure is dropped
    noise_cluster_margin: float = 3.0  # in body-text heights
    min_noise_cluster: int = 3  # suspicious fragments needed to call it noise
    min_figure_area: float = 0.02  # page share needed for a placeholder

    # Header / footer
    header_band: float = 0.12
    footer_band: float = 0.10
    min_header_repeats: int = 3

    # Reading order
    reading_direction: str = "ltr"  # "ltr" or "rtl"
    min_gutter: float = 0.02  # min gap between columns (page width)
    span_width: float = 0.6  # blocks this wide separate column bands

    # Headings
    heading_ratio: float = 1.25
    heading_soft_ratio: float = 1.12
    heading_threshold: float = 0.55
    heading_isolation: float = 1.6  # blank space around heading, in body heights
    heading_min_quality: float = 0.75  # uncertain OCR is never promoted to a heading
    max_heading_lines: int = 2
    max_heading_chars: int = 100
    max_heading_words: int = 12
    heading_keywords: tuple = (
        "chapter", "part", "section", "book", "prologue", "epilogue",
        "appendix", "umutwe", "igice", "chapitre", "partie", "capitulo",
        "cap\u00edtulo", "parte", "kapitel",
    )

    # Paragraph merging
    indent_factor: float = 1.5  # first-line indent (body heights) = new paragraph
    merge_edge_tol: float = 0.05  # "reaches the right edge" tolerance (page width)
    merge_gap: float = 2.0  # max vertical gap (body heights) on the same page
    min_words_geometric_merge: int = 8

    # Hyphen joining dictionary (lowercase words), optional
    dictionary: Optional[set[str]] = None


@dataclass
class ParaStats:
    n_words: int = 0
    mean_conf: Optional[float] = None
    min_conf: Optional[float] = None
    low_conf_ratio: float = 0.0
    garbage_ratio: float = 0.0
    singleton_ratio: float = 0.0
    alnum_ratio: float = 1.0
    misalign: float = 0.0
    height_cv: float = 0.0
    quality: float = 1.0

    def as_scores(self) -> dict:
        d = asdict(self)
        return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in d.items() if v is not None}


@dataclass
class _Rec:
    page: int
    kind: str  # "text" | "figure"
    page_w: float = 0.0
    page_h: float = 0.0
    para: Optional[dict] = None
    text: str = ""
    bbox: Optional[list] = None
    block_bbox: Optional[list] = None
    first_x0: Optional[float] = None
    last_x1: Optional[float] = None
    n_lines: int = 0
    n_words: int = 0
    band: Optional[str] = None
    stats: Optional[ParaStats] = None
    dropped_words: list = field(default_factory=list)
    status: str = "keep"
    reason: str = ""
    placeholder: bool = False
    flags: list = field(default_factory=list)


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------
def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _valid_box(box) -> bool:
    return (
        isinstance(box, (list, tuple))
        and len(box) == 4
        and all(isinstance(v, (int, float)) for v in box)
    )


def _bbox(items: Iterable[dict]) -> Optional[list[float]]:
    boxes = [i["bbox"] for i in items if _valid_box(i.get("bbox"))]
    if not boxes:
        return None
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def _area(b) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _overlap_ratio(a, b) -> float:
    """Share of box a that lies inside box b."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    area = _area(a)
    return (w * h) / area if area > 0 else 0.0


def _x_overlap(a, b) -> float:
    ow = min(a[2], b[2]) - max(a[0], b[0])
    if ow <= 0:
        return 0.0
    mw = min(a[2] - a[0], b[2] - b[0])
    return ow / mw if mw > 0 else 0.0


def _boxes_touch(a, b, margin: float) -> bool:
    return (
        a[0] - margin < b[2]
        and a[2] + margin > b[0]
        and a[1] - margin < b[3]
        and a[3] + margin > b[1]
    )


def _words(paragraph: dict) -> list[dict]:
    return [
        w
        for line in paragraph.get("lines", [])
        for w in line.get("words", [])
        if w.get("text", "").strip()
    ]


def _word_heights(paragraph: dict) -> list[float]:
    heights = [
        w["bbox"][3] - w["bbox"][1]
        for w in _words(paragraph)
        if _valid_box(w.get("bbox"))
    ]
    return [h for h in heights if h > 0]


def _conf(word: dict) -> Optional[float]:
    c = word.get("conf")
    if isinstance(c, (int, float)) and c >= 0:
        return float(c)
    return None


def _body_height(pages: list[dict]) -> float:
    heights = [
        h
        for page in pages
        for block in page.get("blocks", [])
        if block.get("type", "text") == "text"
        for para in block.get("paragraphs", [])
        for h in _word_heights(para)
    ]
    return statistics.median(heights) if heights else 0.0


def _doc_conf(pages: list[dict]) -> float:
    confs = [
        c
        for page in pages
        for block in page.get("blocks", [])
        if block.get("type", "text") == "text"
        for para in block.get("paragraphs", [])
        for w in _words(para)
        for c in [_conf(w)]
        if c is not None
    ]
    return statistics.median(confs) if confs else 80.0


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------
def join_lines(lines: list[str], dictionary: Optional[set[str]] = None) -> str:
    """Join lines into one paragraph, repairing line-end hyphenation.

    "infor-" + "mation"  -> "information"   (next line starts lowercase)
    "Anglo-" + "Saxon"   -> "Anglo-Saxon"   (next line starts uppercase)
    With a dictionary, "well-" + "known" stays "well-known" unless
    "wellknown" is a known word.
    """
    text = ""
    for raw in lines:
        line = raw.strip().replace("\u00ad", "")
        if not line:
            continue
        if not text:
            text = line
            continue

        if text.endswith("-") and len(text) > 1 and text[-2].isalpha():
            first = line[0]
            if first.islower():
                if dictionary is None:
                    text = text[:-1] + line
                else:
                    prefix = text[:-1].split()[-1]
                    next_word = re.sub(r"\W+$", "", line.split()[0])
                    if (prefix + next_word).lower() in dictionary:
                        text = text[:-1] + line
                    else:
                        text = text + line
            elif first.isalpha():
                text = text + line
            else:
                text = text + " " + line
        else:
            text = text + " " + line
    return text.strip()


def extract_paragraph_text(
    paragraph: dict, dictionary: Optional[set[str]] = None
) -> str:
    lines = []
    for line in paragraph.get("lines", []):
        words = [
            w.get("text", "").strip()
            for w in line.get("words", [])
            if w.get("text", "").strip()
        ]
        if words:
            lines.append(" ".join(words))
    return join_lines(lines, dictionary)


def _is_page_number(text: str) -> bool:
    return bool(_PAGE_NUMBER.match(text.strip()))


def _norm(text: str) -> str:
    text = re.sub(r"\d+", "#", text.lower())
    text = re.sub(r"\s+", " ", text)
    return text.strip(" #.-\u2014\u2013|")


def _is_junk_token(tok: str) -> bool:
    if all(ch in _PUNCT for ch in tok):
        return len(tok) > 3
    alnum = sum(ch.isalnum() for ch in tok)
    if alnum == 0:
        return True
    if len(tok) >= 4 and len(set(tok.lower())) == 1:
        return True
    if len(tok) >= 3 and alnum / len(tok) < 0.5:
        return True
    return False


def _split_merged_token(token: str) -> Optional[str]:
    """Suggest a split for a likely merged OCR token."""
    if zipf_frequency is None:
        return None
    if not token.isalpha() or len(token) < 4:
        return None
    original = token.lower()
    original_freq = zipf_frequency(original, "en")
    best_split = None
    best_score = 0.0
    for i in range(1, len(original)):
        left = original[:i]
        right = original[i:]
        if len(left) < 1 or len(right) < 2:
            continue
        if len(left) == 1 and left not in {"a", "i"}:
            continue
        left_freq = zipf_frequency(left, "en")
        right_freq = zipf_frequency(right, "en")
        if left_freq < 3.5 or right_freq < 3.5:
            continue
        score = min(left_freq, right_freq) - original_freq
        if score > best_score:
            best_score = score
            best_split = (left, right)
    if best_split is None or best_score < 1.5:
        return None
    left, right = best_split
    if token.isupper():
        left = left.upper()
        right = right.upper()
    else:
        if token[0].isupper():
            left = left.capitalize()
        if token[len(left)].isupper():
            right = right.capitalize()
    return f"{left} {right}"


def _split_with_context(
    token: str,
    previous: Optional[str] = None,
    following: Optional[str] = None,
) -> Optional[str]:
    """Suggest a merged-word split using neighbouring words."""

    if zipf_frequency is None:
        return None

    suggestion = _split_merged_token(token)

    if suggestion is None:
        return None

    left, right = suggestion.split(" ", 1)

    context_score = 0

    if previous:
        phrase = f"{previous.lower()} {left.lower()}"
        if zipf_frequency(phrase, "en") >= 3.5:
            context_score += 1

    if following:
        phrase = f"{right.lower()} {following.lower()}"
        if zipf_frequency(phrase, "en") >= 3.5:
            context_score += 1

    # Require stronger evidence when only one neighbouring word exists.
    if context_score < 1:
        return None

    return suggestion


def _band(box, page_height: float, cfg: CleanConfig) -> Optional[str]:
    if not page_height or box is None:
        return None
    if box[3] <= cfg.header_band * page_height:
        return "top"
    if box[1] >= (1 - cfg.footer_band) * page_height:
        return "bottom"
    return None


# --------------------------------------------------------------------------
# Confidence analysis and paragraph quality
# --------------------------------------------------------------------------
def _analyze_paragraph(
    para: dict, cfg: CleanConfig, doc_conf: float
) -> tuple[ParaStats, list[str], list[tuple[dict, float]]]:
    """Return (stats, kept line texts, dropped (word, conf) pairs).

    Words are dropped only when confidence is below word_conf_drop AND the
    token looks like junk (symbols, repeated characters, or 1-2 characters).
    Quality is scored on all words, so junk still lowers the paragraph score.
    """
    kept_lines: list[str] = []
    dropped: list[tuple[dict, float]] = []
    all_words: list[dict] = []

    for line in para.get("lines", []):
        kept = []
        for w in line.get("words", []):
            tok = w.get("text", "").strip()
            if not tok:
                continue
            all_words.append(w)
            c = _conf(w)
            if (
                cfg.drop_junk_words
                and c is not None
                and c < cfg.word_conf_drop
                and (_is_junk_token(tok) or sum(ch.isalnum() for ch in tok) <= 2)
            ):
                dropped.append((w, c))
                continue
            kept.append(tok)
        if kept:
            kept_lines.append(" ".join(kept))

    stats = ParaStats(n_words=len(all_words))
    if not all_words:
        stats.quality = 0.0
        return stats, kept_lines, dropped

    toks = [w["text"].strip() for w in all_words]
    n = len(toks)
    confs = [c for c in (_conf(w) for w in all_words) if c is not None]
    if confs:
        stats.mean_conf = sum(confs) / len(confs)
        stats.min_conf = min(confs)
        stats.low_conf_ratio = sum(c < cfg.word_conf_warn for c in confs) / len(confs)
    stats.garbage_ratio = sum(_is_junk_token(t) for t in toks) / n
    if n >= 3:
        stats.singleton_ratio = (
            sum(len(t) == 1 and t.isalpha() and t.lower() not in _SINGLE_OK for t in toks) / n
        )
    chars = "".join(toks)
    stats.alnum_ratio = sum(ch.isalnum() for ch in chars) / len(chars) if chars else 0.0

    heights = _word_heights(para)
    if len(heights) >= 3 and statistics.mean(heights) > 0:
        stats.height_cv = statistics.pstdev(heights) / statistics.mean(heights)

    misaligns = []
    for line in para.get("lines", []):
        boxed = [w for w in line.get("words", []) if _valid_box(w.get("bbox"))]
        if len(boxed) >= 3:
            centres = [(w["bbox"][1] + w["bbox"][3]) / 2 for w in boxed]
            h = statistics.median(w["bbox"][3] - w["bbox"][1] for w in boxed)
            if h > 0:
                misaligns.append(statistics.pstdev(centres) / h)
    if misaligns:
        stats.misalign = sum(misaligns) / len(misaligns)

    ref = max(doc_conf, 50.0)
    conf_comp = 0.7 if stats.mean_conf is None else _clamp(stats.mean_conf / ref)
    layout_penalty = 0.5 * _clamp(stats.misalign / 0.5) + 0.5 * _clamp(stats.height_cv / 0.8)
    stats.quality = _clamp(
        0.45 * conf_comp
        + 0.20 * (1 - stats.low_conf_ratio)
        + 0.15 * (1 - stats.garbage_ratio)
        + 0.05 * _clamp(stats.alnum_ratio / 0.7)
        + 0.05 * (1 - stats.singleton_ratio)
        + 0.10 * (1 - layout_penalty)
    )
    return stats, kept_lines, dropped


# --------------------------------------------------------------------------
# Reading order
# --------------------------------------------------------------------------
def _order_band(band: list, width: float, cfg: CleanConfig) -> list:
    """Order one band of blocks (between full-width blocks)."""
    by_pos = sorted(band, key=lambda t: (t[1][1], t[1][0]))
    if len(band) < 2:
        return by_pos

    # Merge x-intervals; a gutter wider than min_gutter starts a new column.
    intervals = sorted((t[1][0], t[1][2]) for t in band)
    cols: list[list[float]] = []
    for x0, x1 in intervals:
        if cols and x0 <= cols[-1][1] + cfg.min_gutter * width:
            cols[-1][1] = max(cols[-1][1], x1)
        else:
            cols.append([x0, x1])
    if len(cols) < 2:
        return by_pos

    def col_of(t) -> int:
        cx = (t[1][0] + t[1][2]) / 2
        for i, (x0, x1) in enumerate(cols):
            if x0 <= cx <= x1:
                return i
        return len(cols) - 1

    grouped: dict[int, list] = defaultdict(list)
    for t in band:
        grouped[col_of(t)].append(t)

    # Columns are real only if blocks of different columns share vertical space.
    def v_overlap(a, b) -> bool:
        ov = min(a[1][3], b[1][3]) - max(a[1][1], b[1][1])
        smaller = min(a[1][3] - a[1][1], b[1][3] - b[1][1])
        return smaller > 0 and ov > 0.3 * smaller

    idx = sorted(grouped)
    side_by_side = any(
        v_overlap(a, b)
        for i, ci in enumerate(idx)
        for cj in idx[i + 1:]
        for a in grouped[ci]
        for b in grouped[cj]
    )
    if not side_by_side:
        return by_pos

    if cfg.reading_direction == "rtl":
        idx = idx[::-1]
    out = []
    for i in idx:
        out.extend(sorted(grouped[i], key=lambda t: t[1][1]))
    return out


def order_blocks(blocks: list[dict], page_width: float, cfg: CleanConfig) -> list[dict]:
    """Order blocks top-to-bottom, finishing each column before the next.

    Blocks at least span_width of the page wide (titles, full-width text)
    separate the page into bands; column gutters are found per band from the
    union of block x-ranges, which tolerates indents and uneven widths. If any
    block has no geometry the original order is kept.
    """
    boxed = []
    for block in blocks:
        box = block.get("bbox")
        if not _valid_box(box):
            box = _bbox(w for p in block.get("paragraphs", []) for w in _words(p))
        if box is None:
            return list(blocks)
        boxed.append((block, box))
    if len(boxed) < 2:
        return list(blocks)

    width = page_width or max(box[2] for _, box in boxed)
    boxed.sort(key=lambda t: (t[1][1], t[1][0]))

    ordered: list = []
    band: list = []
    for item in boxed:
        if item[1][2] - item[1][0] >= cfg.span_width * width:
            ordered.extend(_order_band(band, width, cfg))
            band = []
            ordered.append(item)
        else:
            band.append(item)
    ordered.extend(_order_band(band, width, cfg))
    return [block for block, _ in ordered]


# --------------------------------------------------------------------------
# Headings
# --------------------------------------------------------------------------
def is_heading(paragraph: dict, text: str, body_height: float, cfg: CleanConfig) -> bool:
    """Simple geometry-only check (kept for compatibility)."""
    heights = _word_heights(paragraph)
    if not text or not heights or not body_height or _is_page_number(text):
        return False
    if len(text) > cfg.max_heading_chars:
        return False
    return statistics.median(heights) >= cfg.heading_ratio * body_height


def _heading_score(rec: _Rec, gaps: tuple, body_h: float, cfg: CleanConfig) -> tuple[float, bool]:
    """Return (score, gate). A heading needs gate and score >= threshold."""
    text = rec.text.strip()
    words = text.split()
    if (
        not text
        or len(text) > cfg.max_heading_chars
        or len(words) > cfg.max_heading_words
        or rec.n_lines > cfg.max_heading_lines
        or _is_page_number(text)
        or not body_h
    ):
        return 0.0, False

    heights = _word_heights(rec.para)
    ratio = statistics.median(heights) / body_h if heights else 1.0
    size = 1.0 if ratio >= cfg.heading_ratio else 0.5 if ratio >= cfg.heading_soft_ratio else 0.0

    gap_above, gap_below = gaps
    iso_min = cfg.heading_isolation * body_h
    iso = (
        (1.0 if gap_above is None or gap_above >= iso_min else 0.0)
        + (1.0 if gap_below is None or gap_below >= iso_min else 0.0)
    ) / 2

    punct = 0.0 if text.endswith((".", ",", ";", ":")) else 1.0

    centered = 0.0
    if rec.bbox and rec.block_bbox:
        bw = rec.block_bbox[2] - rec.block_bbox[0]
        pw = rec.bbox[2] - rec.bbox[0]
        pc = (rec.bbox[0] + rec.bbox[2]) / 2
        bc = (rec.block_bbox[0] + rec.block_bbox[2]) / 2
        if bw > 0 and pw <= 0.8 * bw and abs(pc - bc) <= 0.04 * max(rec.page_w, bw):
            centered = 1.0

    letters = [c for c in text if c.isalpha()]
    caps = len(letters) >= 3 and text == text.upper()
    titled = len(words) >= 2 and all(w[0].isupper() for w in words if w[0].isalpha())
    case = 1.0 if caps else 0.5 if titled else 0.0

    first = re.sub(r"\W+", "", words[0].lower()) if words else ""
    keyword = 1.0 if first in cfg.heading_keywords else 0.0
    if re.match(r"^\d+(\.\d+){0,3}[.)]?\s+\S", text):
        keyword = max(keyword, 0.5)

    score = (
        0.40 * size + 0.20 * iso + 0.10 + 0.10 * punct
        + 0.10 * centered + 0.05 * case + 0.15 * keyword
    )
    gate = size > 0 or keyword >= 1.0 or (centered and iso == 1.0 and caps)
    return score, bool(gate)


def _gaps(rec: _Rec, kept: list[_Rec]) -> tuple:
    above = below = None
    if not rec.bbox:
        return None, None
    for o in kept:
        if o is rec or not o.bbox or _x_overlap(o.bbox, rec.bbox) < 0.3:
            continue
        if o.bbox[3] <= rec.bbox[1] + 1:
            gap = rec.bbox[1] - o.bbox[3]
            above = gap if above is None else min(above, gap)
        elif o.bbox[1] >= rec.bbox[3] - 1:
            gap = o.bbox[1] - rec.bbox[3]
            below = gap if below is None else min(below, gap)
    return above, below


# --------------------------------------------------------------------------
# Paragraph merging
# --------------------------------------------------------------------------
def _continues(prev: Element, rec: _Rec, body_h: float, cfg: CleanConfig) -> bool:
    g = prev.geom
    if not g or prev.kind != "paragraph" or not rec.bbox:
        return False

    ptxt = prev.text.rstrip()
    text = rec.text
    starts_lower = text[:1].islower()
    same_page = g["page"] == rec.page
    indented = bool(
        rec.first_x0 is not None
        and rec.block_bbox
        and body_h
        and rec.first_x0 - rec.block_bbox[0] > cfg.indent_factor * body_h
    )

    if ptxt.endswith("-") and len(ptxt) > 1 and ptxt[-2].isalpha():
        return starts_lower or not indented
    if ptxt.endswith(SENTENCE_END) or indented:
        return False

    if starts_lower:
        if not same_page:
            return True
        if _x_overlap(g["bbox"], rec.bbox) < 0.3:
            # Flow jumps to another column: only a real column break if the
            # previous text ends near the bottom and the next starts near the top.
            return bool(
                g["page_h"]
                and rec.bbox[1] < g["bbox"][1]
                and g["bbox"][3] >= 0.6 * g["page_h"]
                and rec.bbox[1] <= 0.4 * g["page_h"]
            )
        gap = rec.bbox[1] - g["bbox"][3]
        return -body_h <= gap <= cfg.merge_gap * body_h

    # Uppercase or digit start: merge only with strong geometric evidence.
    if g["n_words"] >= cfg.min_words_geometric_merge and not same_page and g["page_h"]:
        reaches_edge = g["last_x1"] >= g["block_x1"] - cfg.merge_edge_tol * g["page_w"]
        at_bottom = g["bbox"][3] >= 0.6 * g["page_h"]
        at_top = rec.page_h and rec.bbox[1] <= 0.3 * rec.page_h
        return bool(reaches_edge and at_bottom and at_top)
    return False


# --------------------------------------------------------------------------
# Stage 1: OCR JSON -> elements
# --------------------------------------------------------------------------
def build_elements(
    ocr_data: dict,
    cfg: Optional[CleanConfig] = None,
    correction_decisions: Optional[dict[str, str]] = None,
) -> BuildResult:
    cfg = cfg or CleanConfig()
    correction_decisions = correction_decisions or {}
    pages = ocr_data.get("pages", [])
    if not pages:
        raise ValueError("OCR data contains no pages.")

    body_h = _body_height(pages)
    doc_conf = _doc_conf(pages)
    removed: list[Removed] = []
    flagged: list[Removed] = []
    corrections: list[dict] = []

    # ---- Pass 1: ordered records with confidence and geometry ----------
    recs: list[_Rec] = []
    figures: dict[int, list] = defaultdict(list)

    for idx, page in enumerate(pages):
        page_no = page.get("page", idx + 1)
        page_h = page.get("height") or 0
        page_w = page.get("width") or 0
        blocks = order_blocks(page.get("blocks", []), page_w, cfg)
        if not page_w:
            xs = [b.get("bbox")[2] for b in blocks if _valid_box(b.get("bbox"))]
            page_w = max(xs) if xs else 0

        for block_index, block in enumerate(blocks):
            if block.get("type", "text") != "text":
                box = block.get("bbox") if _valid_box(block.get("bbox")) else None
                recs.append(_Rec(page_no, "figure", page_w, page_h, bbox=box))
                if box:
                    figures[page_no].append(box)
                continue

            block_box = block.get("bbox") if _valid_box(block.get("bbox")) else _bbox(
                w for p in block.get("paragraphs", []) for w in _words(p)
            )
            for paragraph_index, para in enumerate(block.get("paragraphs", [])):
                stats, kept_lines, dropped = _analyze_paragraph(para, cfg, doc_conf)
                corrected_lines = []
                for line_index, line_text in enumerate(kept_lines):
                    tokens = line_text.split()
                    corrected_tokens = []
                    for i, token in enumerate(tokens):
                        previous = tokens[i - 1] if i > 0 else None
                        following = tokens[i + 1] if i + 1 < len(tokens) else None
                        suggestion = _split_with_context(
                            token, previous, following
                        )
                        if suggestion:
                            left, right = suggestion.split(" ", 1)
                            context_score = 0
                            if previous and zipf_frequency(
                                f"{previous.lower()} {left.lower()}", "en"
                            ) >= 3.5:
                                context_score += 1
                            if following and zipf_frequency(
                                f"{right.lower()} {following.lower()}", "en"
                            ) >= 3.5:
                                context_score += 1
                            auto_apply = context_score == 2
                            correction_id = (
                                f"p{page_no}-b{block_index}-para{paragraph_index}"
                                f"-line{line_index}-word{i}"
                            )
                            decision = correction_decisions.get(correction_id)
                            apply_correction = (
                                decision == "accepted"
                                or (decision is None and auto_apply)
                            )
                            if decision == "accepted":
                                correction_status = "accepted"
                            elif decision == "rejected":
                                correction_status = "rejected"
                            elif auto_apply and decision is None:
                                correction_status = "auto_applied"
                            else:
                                correction_status = "needs_review"
                            corrections.append({
                                "id": correction_id,
                                "page": page_no,
                                "block_index": block_index,
                                "paragraph_index": paragraph_index,
                                "line_index": line_index,
                                "word_index": i,
                                "original": token,
                                "corrected": suggestion,
                                "previous": previous,
                                "following": following,
                                "method": "merged_word_split",
                                "context_score": context_score,
                                "status": correction_status,
                            })
                            if apply_correction:
                                corrected_tokens.extend(suggestion.split())
                            else:
                                corrected_tokens.append(token)
                        else:
                            corrected_tokens.append(token)
                    corrected_lines.append(" ".join(corrected_tokens))
                kept_lines = corrected_lines
                box = _bbox(_words(para))
                if not kept_lines:
                    if stats.n_words:
                        # Kept as a dropped record so it can still take part in
                        # noise-cluster detection (and trigger a placeholder).
                        original = " ".join(w["text"].strip() for w in _words(para))
                        reason = "all words discarded (low-confidence junk)"
                        recs.append(_Rec(
                            page=page_no, kind="text", page_w=page_w, page_h=page_h,
                            para=para, text=original, bbox=box, block_bbox=block_box,
                            n_words=stats.n_words, stats=stats,
                            status="drop", reason=reason,
                        ))
                        removed.append(Removed(page_no, original, reason,
                                               bbox=box, scores=stats.as_scores()))
                    continue
                lines = [l for l in para.get("lines", []) if _words({"lines": [l]})]
                first_box = _bbox(_words({"lines": [lines[0]]})) if lines else None
                last_box = _bbox(_words({"lines": [lines[-1]]})) if lines else None
                recs.append(_Rec(
                    page=page_no, kind="text", page_w=page_w, page_h=page_h,
                    para=para, text=join_lines(kept_lines, cfg.dictionary),
                    bbox=box, block_bbox=block_box,
                    first_x0=first_box[0] if first_box else None,
                    last_x1=last_box[2] if last_box else None,
                    n_lines=len(lines), n_words=stats.n_words,
                    band=_band(box, page_h, cfg), stats=stats, dropped_words=dropped,
                ))

    texts = [r for r in recs if r.kind == "text"]

    def drop(rec: _Rec, reason: str) -> None:
        rec.status, rec.reason = "drop", reason
        removed.append(Removed(rec.page, rec.text, reason, "paragraph",
                               rec.bbox, rec.stats.as_scores() if rec.stats else {}))

    # ---- A: page numbers, repeated headers/footers ---------------------
    seen_on: dict[tuple, set] = defaultdict(set)
    for r in texts:
        if r.band:
            seen_on[(r.band, _norm(r.text))].add(r.page)
    required = min(cfg.min_header_repeats, max(2, len(pages)))
    for r in texts:
        if not r.band:
            continue
        key = (r.band, _norm(r.text))
        if _is_page_number(r.text):
            drop(r, "page number")
        elif key[1] and len(seen_on[key]) >= required:
            drop(r, "repeated header/footer")

    # ---- B: text inside figure regions ---------------------------------
    for r in texts:
        if r.status != "keep" or not r.bbox:
            continue
        inside = max((_overlap_ratio(r.bbox, f) for f in figures.get(r.page, [])), default=0.0)
        if inside >= cfg.figure_overlap:
            if r.stats.quality < cfg.figure_text_quality or r.n_words <= cfg.figure_short_words:
                drop(r, f"text inside figure region (overlap {inside:.2f})")
            else:
                r.flags.append("overlaps_figure")
                flagged.append(Removed(r.page, r.text, f"kept: overlaps figure ({inside:.2f})",
                                       bbox=r.bbox, scores=r.stats.as_scores()))

    # ---- C: clusters of suspicious fragments (illustration noise) ------
    margin = cfg.noise_cluster_margin * body_h
    by_page: dict[int, list[_Rec]] = defaultdict(list)
    for r in texts:
        if not r.bbox:
            continue
        already_junk = r.status == "drop" and r.reason.startswith("all words discarded")
        if already_junk or (r.status == "keep" and r.stats.quality < cfg.min_quality_flag):
            by_page[r.page].append(r)
    for page_no, cands in by_page.items():
        parent = list(range(len(cands)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(cands)):
            for j in range(i + 1, len(cands)):
                if _boxes_touch(cands[i].bbox, cands[j].bbox, margin):
                    parent[find(i)] = find(j)
        groups: dict[int, list[_Rec]] = defaultdict(list)
        for i, r in enumerate(cands):
            groups[find(i)].append(r)

        for members in groups.values():
            if len(members) < cfg.min_noise_cluster:
                continue
            box = _bbox([{"bbox": m.bbox} for m in members])
            page_area = (members[0].page_w or 0) * (members[0].page_h or 0)
            has_figure = any(_overlap_ratio(box, f) >= 0.3 for f in figures.get(page_no, []))
            members.sort(key=lambda m: recs.index(m))
            for m in members:
                if m.status == "keep":
                    drop(m, f"image-related OCR noise (cluster of {len(members)} fragments)")
            if page_area and _area(box) >= cfg.min_figure_area * page_area and not has_figure:
                members[0].placeholder = True

    # ---- D/E: paragraph quality ----------------------------------------
    for r in texts:
        if r.status != "keep":
            continue
        q = r.stats.quality
        if q < cfg.min_quality_drop:
            drop(r, f"low-quality OCR fragment (quality {q:.2f})")
        elif q < cfg.min_quality_flag:
            r.flags.append("low_quality")
            flagged.append(Removed(r.page, r.text, f"kept: suspicious OCR (quality {q:.2f})",
                                   bbox=r.bbox, scores=r.stats.as_scores()))

    kept_by_page: dict[int, list[_Rec]] = defaultdict(list)
    for r in texts:
        if r.status == "keep":
            kept_by_page[r.page].append(r)
            for w, c in r.dropped_words:
                removed.append(Removed(r.page, w["text"].strip(),
                                       "low-confidence junk word", "word",
                                       w.get("bbox"), {"conf": round(c, 1)}))

    # ---- Pass 2: headings, merging, figures ----------------------------
    elements: list[Element] = []

    def figure_element(page_no: int, note: Optional[str] = None) -> Element:
        el = Element("figure", f"[Figure on original page {page_no}]", page_no)
        if note:
            el.flags.append(note)
        return el

    for r in recs:
        if r.kind == "figure":
            elements.append(figure_element(r.page))
            continue
        if r.status == "drop":
            if r.placeholder:
                elements.append(figure_element(r.page, "inferred_from_noise"))
            continue

        geom = {
            "page": r.page, "bbox": r.bbox, "last_x1": r.last_x1,
            "block_x1": r.block_bbox[2] if r.block_bbox else None,
            "page_w": r.page_w, "page_h": r.page_h, "n_words": r.n_words,
        }
        suspicious = "low_quality" in r.flags or r.stats.quality < cfg.heading_min_quality
        score, gate = (0.0, False) if suspicious else _heading_score(
            r, _gaps(r, kept_by_page[r.page]), body_h, cfg)

        if gate and score >= cfg.heading_threshold:
            elements.append(Element("heading", r.text, r.page, r.stats.quality, list(r.flags), geom))
            continue

        prev = elements[-1] if elements else None
        if prev is not None and _continues(prev, r, body_h, cfg):
            prev.text = join_lines([prev.text, r.text], cfg.dictionary)
            prev.quality = min(prev.quality or 1.0, r.stats.quality)
            prev.flags = sorted(set(prev.flags) | set(r.flags))
            geom["n_words"] += prev.geom["n_words"] if prev.geom else 0
            prev.geom = geom
        else:
            elements.append(Element("paragraph", r.text, r.page, r.stats.quality, list(r.flags), geom))

    log.info("clean_pdf: %d elements, %d removed, %d flagged",
             len(elements), len(removed), len(flagged))
    return BuildResult(elements, removed, flagged, corrections)


# --------------------------------------------------------------------------
# Removal report
# --------------------------------------------------------------------------
def report_dict(result: BuildResult) -> dict:
    return {
        "summary": {
            "removed_by_reason": dict(Counter(
                re.sub(r"\s*\(.*\)$", "", x.reason) for x in result.removed)),
            "removed_total": len(result.removed),
            "flagged_total": len(result.flagged),
            "correction_total": len(result.corrections),
            "elements": len(result.elements),
        },
        "removed": [asdict(x) for x in result.removed],
        "flagged": [asdict(x) for x in result.flagged],
        "corrections": result.corrections,
    }


def format_report(result: BuildResult, max_text: int = 90) -> str:
    def line(x: Removed) -> str:
        t = x.text.replace("\n", " ")
        t = t if len(t) <= max_text else t[: max_text - 3] + "..."
        scores = ", ".join(f"{k}={v}" for k, v in x.scores.items()
                           if k in ("quality", "mean_conf", "low_conf_ratio",
                                    "garbage_ratio", "conf"))
        return f"  p{x.page:<3} [{x.level}] {x.reason}: {t!r}" + (f"  ({scores})" if scores else "")

    out = ["REMOVAL REPORT", "=" * 14]
    summary = report_dict(result)["summary"]
    out.append(f"Removed: {summary['removed_total']}  Flagged: {summary['flagged_total']}")
    for reason, n in sorted(summary["removed_by_reason"].items()):
        out.append(f"  {n:>4}  {reason}")
    out += ["", "Removed items:"] + [line(x) for x in result.removed]
    out += ["", "Kept but flagged:"] + [line(x) for x in result.flagged]
    return "\n".join(out) + "\n"


def write_report(result: BuildResult, json_path: str, text_path: Optional[str] = None) -> None:
    p = Path(json_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report_dict(result), indent=2, ensure_ascii=False), encoding="utf-8")
    if text_path:
        Path(text_path).write_text(format_report(result), encoding="utf-8")


# --------------------------------------------------------------------------
# Exports from the element list
# --------------------------------------------------------------------------
def to_markdown(elements: list[Element]) -> str:
    parts = []
    for e in elements:
        if e.kind == "heading":
            parts.append(f"## {e.text}")
        elif e.kind == "figure":
            parts.append(f"*{e.text}*")
        else:
            parts.append(e.text)
    return "\n\n".join(parts) + "\n"


def to_text(elements: list[Element]) -> str:
    return "\n\n".join(e.text for e in elements) + "\n"


# --------------------------------------------------------------------------
# Stage 2: elements -> PDF
# --------------------------------------------------------------------------
def _register_fonts(cfg: CleanConfig) -> tuple[str, str, str]:
    candidates = []
    if cfg.font_path:
        candidates.append((
            cfg.font_path,
            cfg.bold_font_path or cfg.font_path,
            cfg.italic_font_path or cfg.font_path,
        ))
    candidates.extend(_FONT_CANDIDATES)

    for regular, bold, italic in candidates:
        if all(Path(p).is_file() for p in (regular, bold, italic)):
            pdfmetrics.registerFont(TTFont("CleanBody", regular))
            pdfmetrics.registerFont(TTFont("CleanBold", bold))
            pdfmetrics.registerFont(TTFont("CleanItalic", italic))
            return "CleanBody", "CleanBold", "CleanItalic"

    log.warning(
        "No TrueType font found; using built-in Times. Characters outside "
        "basic Latin may not render. Install fonts-dejavu-core or set font_path."
    )
    return "Times-Roman", "Times-Bold", "Times-Italic"


def render_pdf(
    elements: list[Element], output_path: str, cfg: Optional[CleanConfig] = None
) -> str:
    cfg = cfg or CleanConfig()
    if not elements:
        raise ValueError("No readable text was found in OCR data.")

    body_font, bold_font, italic_font = _register_fonts(cfg)
    align = TA_JUSTIFY if cfg.align == "justify" else TA_LEFT

    body = ParagraphStyle(
        "CleanBody", fontName=body_font, fontSize=cfg.font_size,
        leading=cfg.font_size * cfg.line_spacing, alignment=align,
        spaceAfter=cfg.font_size * 0.8, allowWidows=0, allowOrphans=0,
    )
    heading = ParagraphStyle(
        "CleanHeading", fontName=bold_font, fontSize=cfg.font_size * 1.35,
        leading=cfg.font_size * 1.35 * 1.3, alignment=TA_LEFT,
        spaceBefore=cfg.font_size * 1.2, spaceAfter=cfg.font_size * 0.8,
        keepWithNext=True,
    )
    figure = ParagraphStyle(
        "CleanFigure", parent=body, fontName=italic_font,
        alignment=TA_CENTER, textColor="#555555",
    )
    styles = {"heading": heading, "paragraph": body, "figure": figure}

    def page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont(body_font, 9)
        canvas.drawCentredString(A4[0] / 2, 12 * mm, str(doc.page))
        canvas.restoreState()

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out), pagesize=A4,
        leftMargin=25 * mm, rightMargin=25 * mm,
        topMargin=25 * mm, bottomMargin=25 * mm,
        title="Clean Text Document",
    )
    doc.build(
        [Paragraph(escape(e.text), styles[e.kind]) for e in elements],
        onFirstPage=page_number, onLaterPages=page_number,
    )
    return str(out)


def generate_clean_pdf(
    ocr_data: dict,
    output_path: str,
    cfg: Optional[CleanConfig] = None,
    report_path: Optional[str] = None,
) -> str:
    """OCR JSON in, clean PDF out. Optionally writes the removal report
    (JSON at report_path, readable text next to it as .txt)."""
    cfg = cfg or CleanConfig()
    result = build_elements(ocr_data, cfg)
    if report_path:
        write_report(result, report_path, str(Path(report_path).with_suffix(".txt")))
    return render_pdf(result.elements, output_path, cfg)