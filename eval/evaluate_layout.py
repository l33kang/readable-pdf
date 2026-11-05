from pathlib import Path
import argparse
import json
import re
from difflib import SequenceMatcher


def normalize_lines(text):
    lines = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line.strip())
        if line:
            lines.append(line)
    return lines


def normalize_words(text):
    return re.findall(r"\b[\w'-]+\b", text.lower())


def line_similarity(reference, prediction):
    if not reference or not prediction:
        return 0.0

    matcher = SequenceMatcher(None, reference, prediction)
    return matcher.ratio()


def evaluate_file(gt_path, pred_path):
    gt = gt_path.read_text(encoding="utf-8", errors="replace")
    pred = pred_path.read_text(encoding="utf-8", errors="replace")

    gt_lines = normalize_lines(gt)
    pred_lines = normalize_lines(pred)

    gt_words = normalize_words(gt)
    pred_words = normalize_words(pred)

    line_count_accuracy = (
        min(len(gt_lines), len(pred_lines)) / max(len(gt_lines), len(pred_lines))
        if gt_lines or pred_lines
        else 1.0
    )

    line_order_similarity = SequenceMatcher(
        None,
        gt_lines,
        pred_lines
    ).ratio()

    word_order_similarity = SequenceMatcher(
        None,
        gt_words,
        pred_words
    ).ratio()

    avg_line_similarity = 0.0

    if gt_lines and pred_lines:
        total = 0.0
        count = 0

        for gt_line in gt_lines:
            best = max(
                (line_similarity(gt_line, pred_line) for pred_line in pred_lines),
                default=0.0
            )
            total += best
            count += 1

        avg_line_similarity = total / count

    layout_score = (
        0.35 * line_count_accuracy +
        0.35 * line_order_similarity +
        0.30 * avg_line_similarity
    )

    return {
        "reference_lines": len(gt_lines),
        "prediction_lines": len(pred_lines),
        "line_count_accuracy": round(line_count_accuracy * 100, 2),
        "line_order_similarity": round(line_order_similarity * 100, 2),
        "average_line_similarity": round(avg_line_similarity * 100, 2),
        "word_order_similarity": round(word_order_similarity * 100, 2),
        "layout_score": round(layout_score * 100, 2),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate OCR line structure and reading order."
    )
    parser.add_argument("--ground-truth", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output", required=True)

    args = parser.parse_args()

    gt_dir = Path(args.ground_truth)
    pred_dir = Path(args.predictions)
    output = Path(args.output)

    results = {}

    for gt_path in sorted(gt_dir.glob("*.txt")):
        pred_path = pred_dir / gt_path.name

        if not pred_path.exists():
            print(f"WARNING: Missing prediction for {gt_path.name}")
            continue

        results[gt_path.name] = evaluate_file(gt_path, pred_path)

    if results:
        avg = {
            key: round(
                sum(item[key] for item in results.values()) / len(results),
                2
            )
            for key in [
                "line_count_accuracy",
                "line_order_similarity",
                "average_line_similarity",
                "word_order_similarity",
                "layout_score",
            ]
        }
    else:
        avg = {}

    report = {
        "documents": len(results),
        "average": avg,
        "per_document": results,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print()
    print("OCR Layout Evaluation")
    print("---------------------")
    print(f"Documents: {len(results)}")

    if avg:
        print(f"Line count accuracy:    {avg['line_count_accuracy']:.2f}%")
        print(f"Line order similarity:  {avg['line_order_similarity']:.2f}%")
        print(f"Average line similarity:{avg['average_line_similarity']:.2f}%")
        print(f"Word order similarity:  {avg['word_order_similarity']:.2f}%")
        print(f"Layout score:           {avg['layout_score']:.2f}%")

    for name, result in results.items():
        print()
        print(name)
        print(f"  Layout score: {result['layout_score']:.2f}%")
        print(f"  Line order:   {result['line_order_similarity']:.2f}%")
        print(f"  Word order:   {result['word_order_similarity']:.2f}%")

    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print()
    print(f"Report saved to: {output}")


if __name__ == "__main__":
    main()
