
import json
import re
import difflib
import pymupdf

JSON_PATH = "/data/results/3451db17-fc42-4007-9656-b760d28f39af.json"
PDF_PATH = "/data/results/3451db17-fc42-4007-9656-b760d28f39af_clean.pdf"


def normalize(word):
    return re.sub(r"[^a-z0-9]", "", word.lower())


# Extract OCR words
with open(JSON_PATH, encoding="utf-8") as file:
    data = json.load(file)

original = [
    word["text"]
    for page in data["pages"]
    for block in page.get("blocks", [])
    for paragraph in block.get("paragraphs", [])
    for line in paragraph.get("lines", [])
    for word in line.get("words", [])
]

# Extract clean PDF words
document = pymupdf.open(PDF_PATH)
pdf_text = " ".join(page.get_text() for page in document)
output = pdf_text.split()

# Normalize both sequences
original = [normalize(w) for w in original if normalize(w)]
output = [normalize(w) for w in output if normalize(w)]

# Compare sequences
matcher = difflib.SequenceMatcher(
    None, original, output, autojunk=False
)

counts = {
    "equal": 0,
    "replace": 0,
    "delete": 0,
    "insert": 0,
}

examples = {
    "replace": [],
    "delete": [],
    "insert": [],
}

for tag, i1, i2, j1, j2 in matcher.get_opcodes():
    if tag == "equal":
        counts[tag] += i2 - i1

    elif tag == "delete":
        counts[tag] += i2 - i1
        examples[tag].extend(original[i1:i2][:5])

    elif tag == "insert":
        counts[tag] += j2 - j1
        examples[tag].extend(output[j1:j2][:5])

    elif tag == "replace":
        counts[tag] += max(i2 - i1, j2 - j1)
        examples[tag].append(
            (original[i1:i2][:5], output[j1:j2][:5])
        )

print("OCR tokens:", len(original))
print("PDF tokens:", len(output))
print("Matching tokens:", counts["equal"])
print("Deleted:", counts["delete"])
print("Inserted:", counts["insert"])
print("Replaced:", counts["replace"])

print("\nDeleted examples:", examples["delete"][:30])
print("Inserted examples:", examples["insert"][:30])
print("Replacement examples:", examples["replace"][:15])
