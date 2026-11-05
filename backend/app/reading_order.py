"""
Reading-order reconstruction for OCR output.

Input and output use the same schema as ocr_engine.extract_blocks():
    block -> paragraph -> line -> word

Pipeline:
    split lines that straddle a gutter
        -> recursive XY-cut
        -> rebuild blocks/paragraphs/lines in reading order.
"""

from statistics import median


# All thresholds are multiples of the median word height,
# so they scale with font size and DPI.
SPLIT_FACTOR = 2.5
GUTTER_FACTOR = 2.5
ROW_GAP_FACTOR = 1.0


def _union(boxes):
    if not boxes:
        return None

    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def split_line(
    line: dict,
    h: float,
    gap_factor: float = SPLIT_FACTOR,
) -> list[dict]:
    """
    Split a line into one segment per column when OCR merged columns into it.
    """

    words = sorted(
        line.get("words", []),
        key=lambda w: w["bbox"][0],
    )

    if not words:
        return []

    groups = [[words[0]]]

    for prev, word in zip(words, words[1:]):
        gap = word["bbox"][0] - prev["bbox"][2]

        if gap > gap_factor * h:
            groups.append([word])
        else:
            groups[-1].append(word)

    return [
        {
            "bbox": _union([w["bbox"] for w in group]),
            "words": group,
        }
        for group in groups
    ]


def _widest_gap(items, axis, min_gap):
    """
    Find the midpoint of the widest empty channel.

    axis:
        0 = horizontal/x
        1 = vertical/y

    Intervals are merged using a running maximum end coordinate.
    Therefore a gap only exists where no item covers that range.
    """

    if len(items) < 2:
        return None

    spans = sorted(
        (item["bbox"][axis], item["bbox"][axis + 2])
        for item in items
    )

    end = spans[0][1]

    best_width = 0
    best_mid = None

    for start, stop in spans[1:]:
        width = start - end

        if width >= min_gap and width > best_width:
            best_width = width
            best_mid = (end + start) / 2

        end = max(end, stop)

    return best_mid


def _bands(items, min_gap):
    """
    Split items into vertical bands separated by enough whitespace.
    """

    if not items:
        return []

    ordered = sorted(
        items,
        key=lambda item: item["bbox"][1],
    )

    bands = []
    current = [ordered[0]]
    end = ordered[0]["bbox"][3]

    for item in ordered[1:]:
        gap = item["bbox"][1] - end

        if gap >= min_gap:
            bands.append(current)
            current = []

        current.append(item)
        end = max(end, item["bbox"][3])

    bands.append(current)

    return bands


def _cut(items, min_x, min_y, path=()):
    """
    Recursive XY-cut.

    Returns:

        [(column_path, lines), ...]

    in reading order.

    The path identifies the column hierarchy.
    """

    if len(items) <= 1:
        return [(path, items)]

    # First look for a vertical gutter.
    gutter = _widest_gap(
        items,
        axis=0,
        min_gap=min_x,
    )

    if gutter is not None:
        left = [
            item
            for item in items
            if item["bbox"][2] <= gutter
        ]

        right = [
            item
            for item in items
            if item["bbox"][2] > gutter
        ]

        if left and right:
            return (
                _cut(
                    left,
                    min_x,
                    min_y,
                    path + (0,),
                )
                +
                _cut(
                    right,
                    min_x,
                    min_y,
                    path + (1,),
                )
            )

    # If there is no column gutter, look for a horizontal gap.
    bands = _bands(items, min_y)

    if len(bands) > 1:
        output = []

        for band in bands:
            output.extend(
                _cut(
                    band,
                    min_x,
                    min_y,
                    path,
                )
            )

        return output

    # Nothing else to split: sort normally.
    return [
        (
            path,
            sorted(
                items,
                key=lambda item: (
                    item["bbox"][1],
                    item["bbox"][0],
                ),
            ),
        )
    ]


def reorder_blocks(
    blocks: list[dict],
    split_factor: float = SPLIT_FACTOR,
    gutter_factor: float = GUTTER_FACTOR,
    row_gap_factor: float = ROW_GAP_FACTOR,
) -> list[dict]:
    """
    Return OCR blocks rebuilt in reading order.

    Word text, bbox and confidence values are preserved.
    """

    words = [
        word
        for block in blocks
        for paragraph in block["paragraphs"]
        for line in paragraph["lines"]
        for word in line["words"]
    ]

    if not words:
        return blocks

    heights = [
        word["bbox"][3] - word["bbox"][1]
        for word in words
        if word["bbox"][3] > word["bbox"][1]
    ]

    if not heights:
        return blocks

    h = median(heights)

    segments = [
        segment
        for block in blocks
        for paragraph in block["paragraphs"]
        for line in paragraph["lines"]
        for segment in split_line(
            line,
            h,
            split_factor,
        )
    ]

    if not segments:
        return blocks

    leaves = _cut(
        segments,
        min_x=gutter_factor * h,
        min_y=row_gap_factor * h,
    )

    new_blocks = []

    previous_path = None

    b_n = 0
    p_n = 0
    l_n = 0
    w_n = 0

    for path, lines in leaves:

        if path != previous_path or not new_blocks:
            b_n += 1

            new_blocks.append(
                {
                    "id": f"b{b_n}",
                    "type": "text",
                    "bbox": None,
                    "paragraphs": [],
                }
            )

            previous_path = path

        block = new_blocks[-1]

        p_n += 1

        paragraph = {
            "id": f"p{p_n}",
            "lines": [],
        }

        for line in lines:
            l_n += 1

            for word in line["words"]:
                w_n += 1
                word["id"] = f"w{w_n}"

            paragraph["lines"].append(
                {
                    "id": f"l{l_n}",
                    "bbox": line["bbox"],
                    "words": line["words"],
                }
            )

        block["paragraphs"].append(paragraph)

        paragraph_boxes = [
            line["bbox"]
            for line in paragraph["lines"]
        ]

        paragraph_bbox = _union(paragraph_boxes)

        if block["bbox"] is None:
            block["bbox"] = paragraph_bbox
        else:
            block["bbox"] = _union(
                [
                    block["bbox"],
                    paragraph_bbox,
                ]
            )

    return new_blocks