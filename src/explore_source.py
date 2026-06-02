import json
from pathlib import Path
from collections import Counter

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


def find_source(query, sources):
    for source in sources:
        searchable_text = (
            f"{source.get('title', '')} "
            f"{source.get('author', '')} "
            f"{source.get('file_name', '')}"
        )

        if simple_match(query, searchable_text):
            return source

    return None


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


def print_section(title):
    print("\n==============================")
    print(title)
    print("==============================")


def print_bullets(items):
    if not items:
        print("- None")
        return

    for item in items:
        print(f"- {item}")


def score_insight(insight):
    return (
        insight.get("importance_score", 0),
        insight.get("confidence_score", 0),
        insight.get("novelty_score", 0)
    )


if __name__ == "__main__":
    sources = load_json(SOURCES_FILE)
    concepts = load_json(CONCEPTS_FILE)
    problems = load_json(PROBLEMS_FILE)
    insights = load_json(INSIGHTS_FILE)

    query = input("Which book/source do you want to explore? ")

    source = find_source(query, sources)

    if not source:
        print("\nNo matching source found.")
        exit()

    source_id = source["id"]

    source_insights = [
        insight for insight in insights
        if insight.get("source_id") == source_id
    ]

    print_section("SOURCE")
    print(f"Title: {source.get('title')}")
    print(f"Author: {source.get('author')}")
    print(f"Type: {source.get('source_type')}")
    print(f"File: {source.get('file_name')}")

    classification = source.get("classification", {})

    if classification:
        print("\nClassification:")
        print(f"- Form: {classification.get('form', '')}")
        print(f"- Domain: {', '.join(classification.get('domain', []))}")
        print(f"- Subdomain: {', '.join(classification.get('subdomain', []))}")
        print(f"- Purpose: {', '.join(classification.get('purpose', []))}")
        print(f"- Audience: {', '.join(classification.get('audience', []))}")

    print("\nExtraction Lenses:")
    print_bullets(source.get("extraction_lenses", []))

    print("\nKnowledge Priority:")
    print_bullets(source.get("knowledge_priority", []))

    print_section("BOOK-LEVEL TAKEAWAYS")

    if not source_insights:
        print("No insights found for this source yet.")
        exit()

    print(f"Insights extracted so far: {len(source_insights)}")

    concept_ids = collect_unique_ids(source_insights, "concept_ids")
    problem_ids = collect_unique_ids(source_insights, "problem_ids")

    source_concepts = get_items_by_ids(concepts, concept_ids)
    source_problems = get_items_by_ids(problems, problem_ids)

    print_section("MAJOR CONCEPTS")
    for concept in source_concepts:
        print(f"- {concept.get('name')}: {concept.get('description')}")

    print_section("PROBLEMS ADDRESSED")
    for problem in source_problems:
        print(f"- {problem.get('name')}: {problem.get('description')}")

    print_section("TOP INSIGHTS")
    ranked_insights = sorted(
        source_insights,
        key=score_insight,
        reverse=True
    )

    for insight in ranked_insights:
        print(f"\n- {insight.get('title')}")
        print(f"  Type: {insight.get('knowledge_type')}")
        print(f"  Section: {insight.get('chapter_or_section')}")
        print(f"  What it says: {insight.get('what_it_says')}")
        print(f"  Evidence: {insight.get('evidence')}")

    print_section("DECISION RULES")
    found = False

    for insight in source_insights:
        for rule in insight.get("decision_rules", []):
            found = True
            print(f"\n- {rule.get('rule')}")
            print(f"  Condition: {rule.get('condition')}")
            print(f"  Action: {rule.get('action')}")
            print(f"  Rationale: {rule.get('rationale')}")
            print(f"  From: {insight.get('title')}")

    if not found:
        print("- None")

    print_section("PATTERNS")
    found = False

    for insight in source_insights:
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

    print_section("WARNINGS")
    found = False

    for insight in source_insights:
        for warning in insight.get("warnings", []):
            found = True
            print(f"\n- {warning.get('warning')}")
            print(f"  Consequence: {warning.get('consequence')}")
            print(f"  Prevention: {warning.get('prevention')}")
            print(f"  From: {insight.get('title')}")

    if not found:
        print("- None")

    print_section("APPLICATION PATTERNS")
    found = False

    for insight in source_insights:
        for pattern in insight.get("application_patterns", []):
            found = True
            print(f"\n- {pattern.get('pattern_name')}")
            print(f"  When to use: {pattern.get('when_to_use')}")
            print("  Steps:")
            for step in pattern.get("steps", []):
                print(f"   - {step}")
            print(f"  Notes: {pattern.get('adaptation_notes')}")
            print(f"  From: {insight.get('title')}")

    if not found:
        print("- None")

    print_section("EXAMPLES FROM SOURCE")
    found = False

    for insight in source_insights:
        examples = insight.get("examples_from_source", [])

        if examples:
            for example in examples:
                found = True
                print(f"\n- {example.get('example_name')}")
                print(f"  What happened: {example.get('what_happened')}")
                print(f"  Why it matters: {example.get('why_it_matters')}")
                print(f"  Transferable lesson: {example.get('transferable_lesson')}")
                print(f"  From: {insight.get('title')}")

        old_examples = insight.get("examples", [])

        if old_examples:
            for example in old_examples:
                found = True
                print(f"\n- {example}")
                print(f"  From: {insight.get('title')}")

    if not found:
        print("- None")

    print_section("KEYWORD CLOUD")
    all_keywords = []

    for insight in source_insights:
        all_keywords.extend(insight.get("keywords", []))

    keyword_counts = Counter(all_keywords)

    if keyword_counts:
        for keyword, count in keyword_counts.most_common(20):
            print(f"- {keyword}: {count}")
    else:
        print("- None")