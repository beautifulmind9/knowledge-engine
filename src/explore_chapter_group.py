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


def find_source_by_group(query, sources):
    for source in sources:
        structure = source.get("structure", {})
        groups = structure.get("chapter_groups", [])

        for group in groups:
            if simple_match(query, group.get("name", "")):
                return source, group

    return None, None


def insight_in_group(insight, chapters):
    section = insight.get("chapter_or_section", "").lower()

    for chapter in chapters:
        if chapter.lower() in section or section in chapter.lower():
            return True

    return False


def print_section(title):
    print("\n==============================")
    print(title)
    print("==============================")


if __name__ == "__main__":
    sources = load_json(SOURCES_FILE)
    concepts = load_json(CONCEPTS_FILE)
    problems = load_json(PROBLEMS_FILE)
    insights = load_json(INSIGHTS_FILE)

    query = input("Which chapter group do you want to explore? ")

    source, group = find_source_by_group(query, sources)

    if not source or not group:
        print("\nNo matching chapter group found.")
        exit()

    source_id = source["id"]
    chapters = group.get("chapters", [])

    group_insights = [
        insight for insight in insights
        if insight.get("source_id") == source_id
        and insight_in_group(insight, chapters)
    ]

    concept_ids = collect_unique_ids(group_insights, "concept_ids")
    problem_ids = collect_unique_ids(group_insights, "problem_ids")

    group_concepts = get_items_by_ids(concepts, concept_ids)
    group_problems = get_items_by_ids(problems, problem_ids)

    print_section(f"CHAPTER GROUP: {group.get('name')}")
    print(f"Source: {source.get('title')}")
    print("\nChapters:")
    for chapter in chapters:
        print(f"- {chapter}")

    print(f"\nInsights found: {len(group_insights)}")

    print_section("CONCEPTS")
    if group_concepts:
        for concept in group_concepts:
            print(f"- {concept.get('name')}: {concept.get('description')}")
    else:
        print("- None")

    print_section("PROBLEMS")
    if group_problems:
        for problem in group_problems:
            print(f"- {problem.get('name')}: {problem.get('description')}")
    else:
        print("- None")

    print_section("INSIGHTS")
    if group_insights:
        for insight in group_insights:
            print(f"\n- {insight.get('title')}")
            print(f"  Section: {insight.get('chapter_or_section')}")
            print(f"  Type: {insight.get('knowledge_type')}")
            print(f"  What it says: {insight.get('what_it_says')}")
    else:
        print("- None")

    print_section("DECISION RULES")
    found = False
    for insight in group_insights:
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
    for insight in group_insights:
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
    for insight in group_insights:
        for example in insight.get("examples_from_source", []):
            found = True
            print(f"\n- {example.get('example_name')}")
            print(f"  Lesson: {example.get('transferable_lesson')}")
            print(f"  From: {insight.get('title')}")

        for example in insight.get("examples", []):
            found = True
            print(f"\n- {example}")
            print(f"  From: {insight.get('title')}")
    if not found:
        print("- None")

    print_section("WARNINGS")
    found = False
    for insight in group_insights:
        for warning in insight.get("warnings", []):
            found = True
            print(f"\n- {warning.get('warning')}")
            print(f"  Consequence: {warning.get('consequence')}")
            print(f"  Prevention: {warning.get('prevention')}")
            print(f"  From: {insight.get('title')}")
    if not found:
        print("- None")