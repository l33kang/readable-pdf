
import json
import re
import argparse
from pathlib import Path


def normalize_text(text: str) -> str:
    """Normalize whitespace and remove UTF-8 BOM artifacts."""
    text = text.replace("\ufeff", "")
    return re.sub(r"\s+", " ", text).strip()


def normalize_words_for_wer(text: str) -> list:
    """Normalize punctuation and typography for word-level comparison."""
    text = normalize_text(text)

    # Standardize quotation marks and dash characters
    replacements = {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Remove punctuation while preserving letters and numbers
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)

    return text.split()



def analyze_segmentation_errors(reference: list, hypothesis: list) -> list:
    """Detect words merged or split by OCR."""

    def clean(word):
        return re.sub(r"[^\w]", "", word.lower())

    ref = [clean(word) for word in reference]
    hyp = [clean(word) for word in hypothesis]

    errors = []
    i = 0
    j = 0

    while i < len(ref) and j < len(hyp):

        if ref[i] == hyp[j]:
            i += 1
            j += 1
            continue

        # Check whether multiple reference words became one OCR word.
        merged = False

        for count in range(2, min(5, len(ref) - i + 1)):
            combined = "".join(ref[i:i + count])

            if combined == hyp[j]:
                errors.append({
                    "type": "merged_words",
                    "reference": reference[i:i + count],
                    "prediction": hypothesis[j],
                })
                i += count
                j += 1
                merged = True
                break

        if merged:
            continue

        # Check whether one reference word became multiple OCR words.
        split = False

        for count in range(2, min(5, len(hyp) - j + 1)):
            combined = "".join(hyp[j:j + count])

            if combined == ref[i]:
                errors.append({
                    "type": "split_word",
                    "reference": reference[i],
                    "prediction": hypothesis[j:j + count],
                })
                i += 1
                j += count
                split = True
                break

        if split:
            continue

        i += 1
        j += 1

    return errors


def levenshtein_distance(reference: list, hypothesis: list) -> int:
    """Calculate edit distance between two sequences."""
    previous = list(range(len(hypothesis) + 1))

    for i, ref_item in enumerate(reference, start=1):
        current = [i]

        for j, hyp_item in enumerate(hypothesis, start=1):
            cost = 0 if ref_item == hyp_item else 1

            current.append(
                min(
                    current[j - 1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + cost,
                )
            )

        previous = current

    return previous[-1]


def analyze_word_errors(reference: list, hypothesis: list) -> list:
    """Align words and identify substitutions, deletions and insertions."""
    rows = len(reference)
    cols = len(hypothesis)

    dp = [[0] * (cols + 1) for _ in range(rows + 1)]

    for i in range(rows + 1):
        dp[i][0] = i

    for j in range(cols + 1):
        dp[0][j] = j

    for i in range(1, rows + 1):
        for j in range(1, cols + 1):
            cost = 0 if reference[i - 1] == hypothesis[j - 1] else 1

            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )

    errors = []
    i, j = rows, cols

    while i > 0 or j > 0:

        # Matching or substitution
        if i > 0 and j > 0:
            cost = 0 if reference[i - 1] == hypothesis[j - 1] else 1

            if dp[i][j] == dp[i - 1][j - 1] + cost:
                if cost == 1:
                    errors.append({
                        "type": "substitution",
                        "position": i,
                        "reference": reference[i - 1],
                        "prediction": hypothesis[j - 1],
                    })

                i -= 1
                j -= 1
                continue

        # Deletion: a reference word was missed
        if i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            errors.append({
                "type": "deletion",
                "position": i,
                "reference": reference[i - 1],
                "prediction": None,
            })
            i -= 1
            continue

        # Insertion: OCR added an extra word
        if j > 0:
            errors.append({
                "type": "insertion",
                "position": i + 1,
                "reference": None,
                "prediction": hypothesis[j - 1],
            })
            j -= 1

    errors.reverse()
    return errors


def calculate_metrics(reference: str, hypothesis: str) -> dict:
    reference = normalize_text(reference)
    hypothesis = normalize_text(hypothesis)

    reference_chars = list(reference)
    hypothesis_chars = list(hypothesis)

    reference_words = reference.split()
    hypothesis_words = hypothesis.split()

    normalized_reference_words = normalize_words_for_wer(reference)
    normalized_hypothesis_words = normalize_words_for_wer(hypothesis)

    normalized_word_errors = levenshtein_distance(
        normalized_reference_words,
        normalized_hypothesis_words,
    )

    normalized_wer = normalized_word_errors / max(
        len(normalized_reference_words), 1
    )

    char_errors = levenshtein_distance(
        reference_chars,
        hypothesis_chars,
    )

    word_errors = levenshtein_distance(
        reference_words,
        hypothesis_words,
    )

    cer = char_errors / max(len(reference_chars), 1)
    wer = word_errors / max(len(reference_words), 1)

    word_error_details = analyze_word_errors(
        reference_words,
        hypothesis_words,
    )

    segmentation_errors = analyze_segmentation_errors(
    reference_words,
    hypothesis_words,
    )

    return {
        "reference_characters": len(reference_chars),
        "reference_words": len(reference_words),
        "character_errors": char_errors,
        "word_errors": word_errors,
        "cer": cer,
        "wer": wer,
        "cer_percent": round(cer * 100, 2),
        "wer_percent": round(wer * 100, 2),
        "word_error_details": word_error_details,
                "punctuation_insensitive_word_errors": normalized_word_errors,
        "punctuation_insensitive_wer": normalized_wer,
        "punctuation_insensitive_wer_percent": round(
            normalized_wer * 100, 2
        ),
        "segmentation_errors": segmentation_errors,
    }


def evaluate_dataset(ground_truth_dir: Path, predictions_dir: Path):
    results = []

    for reference_path in sorted(ground_truth_dir.glob("*.txt")):
        prediction_path = predictions_dir / reference_path.name

        if not prediction_path.exists():
            print(f"Missing prediction: {reference_path.name}")
            continue

        reference = reference_path.read_text(encoding="utf-8")
        hypothesis = prediction_path.read_text(encoding="utf-8")

        metrics = calculate_metrics(reference, hypothesis)

        results.append({
            "document": reference_path.name,
            **metrics,
        })

    if not results:
        raise ValueError("No matching ground-truth and prediction files found.")

    total_chars = sum(r["reference_characters"] for r in results)
    total_words = sum(r["reference_words"] for r in results)

    total_char_errors = sum(r["character_errors"] for r in results)
    total_word_errors = sum(r["word_errors"] for r in results)

    summary = {
        "documents_evaluated": len(results),
        "cer_percent": round(
            total_char_errors / max(total_chars, 1) * 100, 2
        ),
        "wer_percent": round(
            total_word_errors / max(total_words, 1) * 100, 2
        ),
    }

    return {
        "summary": summary,
        "documents": results,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate OCR accuracy using CER and WER."
    )

    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path("eval/ground_truth"),
    )

    parser.add_argument(
        "--predictions",
        type=Path,
        default=Path("eval/predictions"),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("eval/results/report.json"),
    )

    args = parser.parse_args()

    report = evaluate_dataset(
        args.ground_truth,
        args.predictions,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)

    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\nOCR Evaluation Results")
    print("----------------------")
    print(f"Documents: {report['summary']['documents_evaluated']}")
    print(f"CER: {report['summary']['cer_percent']}%")
    print(f"WER: {report['summary']['wer_percent']}%")

    for document in report["documents"]:
        print(f"\n{document['document']}")
        print(f"  CER: {document['cer_percent']}%")
        print(f"  WER: {document['wer_percent']}%")

        for error in document["word_error_details"]:
            print(
                f"  {error['type'].upper()} at word "
                f"{error['position']}: "
                f"reference={error['reference']!r}, "
                f"prediction={error['prediction']!r}"
            )

    print(f"\nReport saved to: {args.output}")


if __name__ == "__main__":
    main()
