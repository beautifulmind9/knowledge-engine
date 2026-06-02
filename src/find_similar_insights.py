import json
from pathlib import Path
from difflib import SequenceMatcher

DATA_FOLDER = Path("data")
INSIGHTS_FILE = DATA_FOLDER / "insights.json"


def load_json(file_path):
    text = file_path.read_text(encoding="utf-8").strip()

    if not text:
        return []

    return json.loads(text)


def similarity(text_a, text_b):
    return SequenceMatcher(
        None,
        text_a.lower().strip(),
        text_b.lower().strip()
    ).ratio()


def insight_text(insight):
    return " ".join([
        insight.get("title", ""),
        insight.get("what_it_says", ""),
        insight.get("why_it_matters", ""),
        " ".join(insight.get("keywords", []))
    ])


if __name__ == "__main__":
    insights = load_json(INSIGHTS_FILE)

    threshold = 0.35

    print("SIMILAR INSIGHTS REPORT")
    print("=======================")

    found_any = False

    for i in range(len(insights)):
        for j in range(i + 1, len(insights)):
            insight_a = insights[i]
            insight_b = insights[j]

            if insight_a.get("id") == insight_b.get("id"):
                continue

            if insight_a.get("source_id") != insight_b.get("source_id"):
                continue

            score = similarity(
                insight_text(insight_a),
                insight_text(insight_b)
            )

            if score >= threshold:
                found_any = True

                print("\n-----------------------")
                print(f"Similarity score: {score:.2f}")

                print(f"\nInsight A: {insight_a.get('id')}")
                print(f"Title: {insight_a.get('title')}")
                print(f"What it says: {insight_a.get('what_it_says')}")

                print(f"\nInsight B: {insight_b.get('id')}")
                print(f"Title: {insight_b.get('title')}")
                print(f"What it says: {insight_b.get('what_it_says')}")

                print("\nSuggested review:")
                print("- If these are the same idea, merge manually.")
                print("- If they are related but distinct, keep both.")
                print("- If they overlap, consider adding a related_to relationship.")

    if not found_any:
        print("\nNo highly similar insights found.")