import json
from pathlib import Path

DATA_FOLDER = Path("data")

CONCEPTS_FILE = DATA_FOLDER / "concepts.json"
PROBLEMS_FILE = DATA_FOLDER / "problems.json"
INSIGHTS_FILE = DATA_FOLDER / "insights.json"
RELATIONSHIPS_FILE = DATA_FOLDER / "relationships.json"


def load_json(file_path):
    text = file_path.read_text(encoding="utf-8").strip()

    if not text:
        return []

    return json.loads(text)


def save_json(file_path, data):
    file_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def clean_duplicate_insights(insights):
    seen = set()
    cleaned = []

    for insight in insights:
        key = (
            insight.get("source_id", "").strip().lower(),
            insight.get("title", "").strip().lower(),
            insight.get("what_it_says", "").strip().lower(),
        )

        if key in seen:
            continue

        seen.add(key)
        cleaned.append(insight)

    return cleaned


def clean_duplicate_relationships(relationships):
    seen = set()
    cleaned = []

    for relationship in relationships:
        key = (
            relationship.get("from", ""),
            relationship.get("relationship", ""),
            relationship.get("to", "")
        )

        if key in seen:
            continue

        seen.add(key)
        cleaned.append(relationship)

    return cleaned


def clean_broken_relationships(relationships, valid_ids):
    cleaned = []

    for relationship in relationships:
        from_id = relationship.get("from", "")
        to_id = relationship.get("to", "")

        if from_id not in valid_ids:
            continue

        if to_id not in valid_ids:
            continue

        cleaned.append(relationship)

    return cleaned


if __name__ == "__main__":
    concepts = load_json(CONCEPTS_FILE)
    problems = load_json(PROBLEMS_FILE)
    insights = load_json(INSIGHTS_FILE)
    relationships = load_json(RELATIONSHIPS_FILE)

    cleaned_insights = clean_duplicate_insights(insights)

    valid_ids = set()

    valid_ids.add("source_001")

    for concept in concepts:
        valid_ids.add(concept["id"])

    for problem in problems:
        valid_ids.add(problem["id"])

    for insight in cleaned_insights:
        valid_ids.add(insight["id"])

    cleaned_relationships = clean_duplicate_relationships(relationships)
    cleaned_relationships = clean_broken_relationships(cleaned_relationships, valid_ids)

    save_json(INSIGHTS_FILE, cleaned_insights)
    save_json(RELATIONSHIPS_FILE, cleaned_relationships)

    print("Graph cleaned.")
    print(f"Insights: {len(insights)} → {len(cleaned_insights)}")
    print(f"Relationships: {len(relationships)} → {len(cleaned_relationships)}")