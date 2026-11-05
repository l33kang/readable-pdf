from pathlib import Path
import subprocess
import json

ROOT = Path(__file__).parent
SAMPLES = ROOT / "eval" / "samples" / "benchmark"
PRED = ROOT / "eval" / "predictions" / "benchmark_reading_order"
PRED.mkdir(parents=True, exist_ok=True)

container = subprocess.check_output(
    ["docker", "compose", "ps", "-q", "api"],
    text=True
).strip()

images = sorted(SAMPLES.glob("*.png"))

for image in images:
    name = image.stem
    container_path = f"/tmp/{name}.png"

    print(f"\n=== {name} ===")

    subprocess.run(
        ["docker", "cp", str(image), f"{container}:{container_path}"],
        check=True
    )

    code = (
        "from app.ocr_engine import extract_document; "
        "import json; "
        f"print(json.dumps(extract_document('{container_path}'), ensure_ascii=False))"
    )

    result = subprocess.run(
        ["docker", "exec", container, "python", "-c", code],
        capture_output=True,
        text=True,
        check=True
    )

    data = json.loads(result.stdout)

    text = data["text"]

    output = PRED / f"{name}.txt"
    output.write_text(text.strip() + "\n", encoding="utf-8")

    print(f"Saved: {output}")
    print(f"Characters: {len(text)}")

print("\nDONE")
