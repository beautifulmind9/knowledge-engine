import json
from pathlib import Path
from collections import Counter

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


def find_duplicate_names(items):
    names = [
        item.get("name", "").strip().lower()
        for item in items
        if item.get("name", "").strip()
    ]

    counts = Counter(names)

    return {
        name: count
        for name, count in counts.items()
        if count > 1
    }


def find_duplicate_insights(insights):
    keys = []

    for insight in insights:
        key = (
            insight.get("source_id", "").strip().lower(),
            insight.get("title", "").strip().lower(),
            insight.get("what_it_says", "").strip().lower(),
        )
        keys.append(key)

    counts = Counter(keys)

    return {
        key: count
        for key, count in counts.items()
        if count > 1
    }


def find_duplicate_relationships(relationships):
    keys = []

    for rel in relationships:
        key = (
            rel.get("from", ""),
            rel.get("relationship", ""),
            rel.get("to", "")
        )
        keys.append(key)

    counts = Counter(keys)

    return {
        key: count
        for key, count in counts.items()
        if count > 1
    }


if __name__ == "__main__":
    concepts = load_json(CONCEPTS_FILE)
    problems = load_json(PROBLEMS_FILE)
    insights = load_json(INSIGHTS_FILE)
    relationships = load_json(RELATIONSHIPS_FILE)

    print("GRAPH VALIDATION REPORT")
    print("=======================")

    print(f"\nConcepts: {len(concepts)}")
    print(f"Problems: {len(problems)}")
    print(f"Insights: {len(insights)}")
    print(f"Relationships: {len(relationships)}")

    duplicate_concepts = find_duplicate_names(concepts)
    duplicate_problems = find_duplicate_names(problems)
    duplicate_insights = find_duplicate_insights(insights)
    duplicate_relationships = find_duplicate_relationships(relationships)

    print("\nDuplicate Concepts:")
    if duplicate_concepts:
        for name, count in duplicate_concepts.items():
            print(f"- {name}: {count} times")
    else:
        print("- None")

    print("\nDuplicate Problems:")
    if duplicate_problems:
        for name, count in duplicate_problems.items():
            print(f"- {name}: {count} times")
    else:
        print("- None")

    print("\nDuplicate Insights:")
    if duplicate_insights:
        for key, count in duplicate_insights.items():
            source_id, title, what_it_says = key
            print(f"- Source: {source_id}")
            print(f"  Title: {title}")
            print(f"  Count: {count}")
    else:
        print("- None")

    print("\nDuplicate Relationships:")
    if duplicate_relationships:
        for key, count in duplicate_relationships.items():
            from_id, relationship, to_id = key
            print(f"- {from_id} {relationship} {to_id}: {count} times")
    else:
        print("- None")