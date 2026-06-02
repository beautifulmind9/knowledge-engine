import json
from pathlib import Path

DATA_FOLDER = Path("data")

SOURCES_FILE = DATA_FOLDER / "sources.json"
CONCEPTS_FILE = DATA_FOLDER / "concepts.json"
PROBLEMS_FILE = DATA_FOLDER / "problems.json"
INSIGHTS_FILE = DATA_FOLDER / "insights.json"


def load_json(file_path):
    text = file_path.read_text(encoding="utf-8").strip()

    if not text:
        return []

    return json.loads(text)


def simple_match(query, text):
    query_words = query.lower().split()
    text_lower = text.lower()

    return any(word in text_lower for word in query_words)


def get_items_by_ids(items, ids):
    return [
        item for item in items
        if item.get("id") in ids
    ]


def collect_unique_ids(insights, key):
    ids = []

    for insight in insights:
        ids.extend(insight.get(key, []))

    return sorted(set(ids))


def find_matching_insights(query, insights):
    matches = []

    for insight in insights:
        section = insight.get("chapter_or_section", "")

        if simple_match(query, section):
            matches.append(insight)

    return matches


def print_section(title):
    print("\n==============================")
    print(title)
    print("==============================")


if __name__ == "__main__":
    concepts = load_json(CONCEPTS_FILE)
    problems = load_json(PROBLEMS_FILE)
    insights = load_json(INSIGHTS_FILE)

    query = input("Which chapter/section do you want to explore? ")

    chapter_insights = find_matching_insights(query, insights)

    if not chapter_insights:
        print("\nNo matching chapter or section found.")
        exit()

    concept_ids = collect_unique_ids(chapter_insights, "concept_ids")
    problem_ids = collect_unique_ids(chapter_insights, "problem_ids")

    chapter_concepts = get_items_by_ids(concepts, concept_ids)
    chapter_problems = get_items_by_ids(problems, problem_ids)

    print_section(f"CHAPTER / SECTION: {query}")
    print(f"Insights found: {len(chapter_insights)}")

    print_section("CONCEPTS")
    for concept in chapter_concepts:
        print(f"- {concept.get('name')}: {concept.get('description')}")

    print_section("PROBLEMS")
    for problem in chapter_problems:
        print(f"- {problem.get('name')}: {problem.get('description')}")

    print_section("INSIGHTS")
    for insight in chapter_insights:
        print(f"\n- {insight.get('title')}")
        print(f"  Type: {insight.get('knowledge_type')}")
        print(f"  What it says: {insight.get('what_it_says')}")
        print(f"  Evidence: {insight.get('evidence')}")

    print_section("DECISION RULES")
    found = False
    for insight in chapter_insights:
        for rule in insight.get("decision_rules", []):
            found = True
            print(f"\n- {rule.get('rule')}")
            print(f"  Use when: {rule.get('condition')}")
            print(f"  Action: {rule.get('action')}")
            print(f"  From: {insight.get('title')}")
    if not found:
        print("- None")

    print_section("PATTERNS")
    found = False
    for insight in chapter_insights:
        for pattern in insight.get("patterns", []):
            found = True
            print(f"\n- {pattern.get('pattern_name')}")
            print(f"  Description: {pattern.get('description')}")
            print("  Steps:")
            for step in pattern.get("steps", []):
                print(f"   - {step}")
            print(f"  From: {insight.get('title')}")
    if not found:
        print("- None")

    print_section("EXAMPLES")
    found = False
    for insight in chapter_insights:
        examples = insight.get("examples_from_source", [])

        for example in examples:
            found = True
            print(f"\n- {example.get('example_name')}")
            print(f"  Lesson: {example.get('transferable_lesson')}")
            print(f"  From: {insight.get('title')}")

        old_examples = insight.get("examples", [])
        for example in old_examples:
            found = True
            print(f"\n- {example}")
            print(f"  From: {insight.get('title')}")

    if not found:
        print("- None")

    print_section("WARNINGS")
    found = False
    for insight in chapter_insights:
        for warning in insight.get("warnings", []):
            found = True
            print(f"\n- {warning.get('warning')}")
            print(f"  Consequence: {warning.get('consequence')}")
            print(f"  Prevention: {warning.get('prevention')}")
            print(f"  From: {insight.get('title')}")
    if not found:
        print("- None")