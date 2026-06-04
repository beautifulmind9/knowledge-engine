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


def score_insight(insight):
    return (
        insight.get("importance_score", 0),
        insight.get("confidence_score", 0),
        insight.get("novelty_score", 0)
    )


def print_section(title):
    print("\n" + title)
    print("-" * len(title))


if __name__ == "__main__":
    sources = load_json(SOURCES_FILE)
    concepts = load_json(CONCEPTS_FILE)
    problems = load_json(PROBLEMS_FILE)
    insights = load_json(INSIGHTS_FILE)

    query = input("Which book/source do you want to summarize? ")

    source = find_source(query, sources)

    if not source:
        print("\nNo matching source found.")
        exit()

    source_id = source["id"]

    source_insights = [
        insight for insight in insights
        if insight.get("source_id") == source_id
    ]

    if not source_insights:
        print("\nNo insights found for this source yet.")
        exit()

    ranked_insights = sorted(
        source_insights,
        key=score_insight,
        reverse=True
    )

    concept_ids = collect_unique_ids(source_insights, "concept_ids")
    problem_ids = collect_unique_ids(source_insights, "problem_ids")

    source_concepts = get_items_by_ids(concepts, concept_ids)
    source_problems = get_items_by_ids(problems, problem_ids)

    print("\n==============================")
    print(f"SUMMARY: {source.get('title')}")
    print("==============================")
    print(f"Author: {source.get('author')}")
    print(f"Insights used: {len(source_insights)}")

    print_section("Main Message")

    top_keywords = []

    for insight in ranked_insights:
        top_keywords.extend(insight.get("keywords", []))

    keyword_counts = Counter(top_keywords)

    if keyword_counts:
        common_keywords = [
            keyword for keyword, count in keyword_counts.most_common(5)
        ]

        print(
            "This source is currently teaching ideas around: "
            + ", ".join(common_keywords)
            + "."
        )
    else:
        print("Main message will become clearer after more insights are extracted.")

    print_section("Top Lessons")

    for index, insight in enumerate(ranked_insights[:7], start=1):
        print(f"{index}. {insight.get('title')}")
        print(f"   {insight.get('what_it_says')}")

    print_section("Most Important Concepts")

    for concept in source_concepts:
        print(f"- {concept.get('name')}: {concept.get('description')}")

    print_section("Problems This Source Helps Solve")

    for problem in source_problems:
        print(f"- {problem.get('name')}: {problem.get('description')}")

    print_section("Most Useful Decision Rules")

    found = False

    for insight in ranked_insights:
        for rule in insight.get("decision_rules", []):
            found = True
            print(f"- {rule.get('rule')}")
            print(f"  Use when: {rule.get('condition')}")
            print(f"  Action: {rule.get('action')}")

    if not found:
        print("- None found yet.")

    print_section("Most Useful Patterns")

    found = False

    for insight in ranked_insights:
        for pattern in insight.get("patterns", []):
            found = True
            print(f"- {pattern.get('pattern_name')}: {pattern.get('description')}")

            for step in pattern.get("steps", []):
                print(f"  - {step}")

    if not found:
        print("- None found yet.")

    print_section("Best Examples")

    found = False

    for insight in ranked_insights:
        examples = insight.get("examples_from_source", [])

        for example in examples:
            found = True
            print(f"- {example.get('example_name')}")
            print(f"  Lesson: {example.get('transferable_lesson')}")

        old_examples = insight.get("examples", [])

        for example in old_examples:
            found = True
            print(f"- {example}")

    if not found:
        print("- None found yet.")

    print_section("Practical Use Cases")

    use_cases = source.get("monetization_use_cases", [])

    if use_cases:
        for use_case in use_cases:
            print(f"- {use_case}")
    else:
        print("- None listed yet.")