import json
from pathlib import Path
from collections import Counter

DATA_FOLDER = Path("data")

CONCEPTS_FILE = DATA_FOLDER / "concepts.json"
PROBLEMS_FILE = DATA_FOLDER / "problems.json"
INSIGHTS_FILE = DATA_FOLDER / "insights.json"


def load_json(file_path):
    text = file_path.read_text(encoding="utf-8").strip()

    if not text:
        return []

    return json.loads(text)


def normalize(text):
    return text.lower().strip().replace("-", " ")


def collect_nested_items(insights, field_name, name_key):
    items = []

    for insight in insights:
        for item in insight.get(field_name, []):
            name = item.get(name_key, "").strip()

            if name:
                items.append(
                    {
                        "name": name,
                        "insight_id": insight.get("id"),
                        "insight_title": insight.get("title"),
                        "field": field_name
                    }
                )

    return items


def find_duplicate_names(items):
    names = [normalize(item["name"]) for item in items]
    counts = Counter(names)

    duplicates = {
        name: count
        for name, count in counts.items()
        if count > 1
    }

    return duplicates


def print_duplicates(title, items):
    duplicates = find_duplicate_names(items)

    print(f"\n{title}")
    print("=" * len(title))

    if not duplicates:
        print("- None")
        return

    for duplicate_name, count in duplicates.items():
        print(f"\n- {duplicate_name}: {count} times")

        for item in items:
            if normalize(item["name"]) == duplicate_name:
                print(f"  - {item['name']} | {item['insight_id']} | {item['insight_title']}")


if __name__ == "__main__":
    concepts = load_json(CONCEPTS_FILE)
    problems = load_json(PROBLEMS_FILE)
    insights = load_json(INSIGHTS_FILE)

    print("KNOWLEDGE AUDIT REPORT")
    print("======================")

    print(f"\nConcepts: {len(concepts)}")
    print(f"Problems: {len(problems)}")
    print(f"Insights: {len(insights)}")

    concept_items = [
        {
            "name": concept.get("name", ""),
            "insight_id": "",
            "insight_title": "concepts.json",
            "field": "concepts"
        }
        for concept in concepts
    ]

    problem_items = [
        {
            "name": problem.get("name", ""),
            "insight_id": "",
            "insight_title": "problems.json",
            "field": "problems"
        }
        for problem in problems
    ]

    pattern_items = collect_nested_items(
        insights,
        "patterns",
        "pattern_name"
    )

    example_items = collect_nested_items(
        insights,
        "examples_from_source",
        "example_name"
    )

    application_pattern_items = collect_nested_items(
        insights,
        "application_patterns",
        "pattern_name"
    )

    decision_rule_items = collect_nested_items(
        insights,
        "decision_rules",
        "rule"
    )

    warning_items = collect_nested_items(
        insights,
        "warnings",
        "warning"
    )

    print_duplicates("Duplicate Concepts", concept_items)
    print_duplicates("Duplicate Problems", problem_items)
    print_duplicates("Duplicate Patterns", pattern_items)
    print_duplicates("Duplicate Examples", example_items)
    print_duplicates("Duplicate Application Patterns", application_pattern_items)
    print_duplicates("Duplicate Decision Rules", decision_rule_items)
    print_duplicates("Duplicate Warnings", warning_items)
