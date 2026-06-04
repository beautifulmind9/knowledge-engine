import json
from pathlib import Path

DATA_FOLDER = Path("data")

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


def search_concepts(query):
    concepts = load_json(CONCEPTS_FILE)

    matches = []

    for concept in concepts:
        searchable_text = (
            f"{concept.get('name', '')} "
            f"{concept.get('description', '')} "
            f"{' '.join(concept.get('keywords', []))}"
        )

        if simple_match(query, searchable_text):
            matches.append(concept)

    return matches


def get_items_by_ids(items, ids):
    return [
        item for item in items
        if item.get("id") in ids
    ]


def find_related_insights(concept_id):
    insights = load_json(INSIGHTS_FILE)

    related_insights = []

    for insight in insights:
        if concept_id in insight.get("concept_ids", []):
            related_insights.append(insight)

    return related_insights


def find_related_problems(insights):
    problems = load_json(PROBLEMS_FILE)

    problem_ids = []

    for insight in insights:
        problem_ids.extend(insight.get("problem_ids", []))

    problem_ids = sorted(set(problem_ids))

    return get_items_by_ids(problems, problem_ids)


def print_examples(insight):
    examples = insight.get("examples_from_source", [])

    if examples:
        for example in examples:
            print(f"- {example.get('example_name')}")
            print(f"  What happened: {example.get('what_happened')}")
            print(f"  Why it matters: {example.get('why_it_matters')}")
            print(f"  Transferable lesson: {example.get('transferable_lesson')}")
    else:
        old_examples = insight.get("examples", [])

        if old_examples:
            for example in old_examples:
                print(f"- {example}")
        else:
            print("- None")


def print_decision_rules(insight):
    decision_rules = insight.get("decision_rules", [])

    if not decision_rules:
        print("- None")
        return

    for rule in decision_rules:
        print(f"- Rule: {rule.get('rule')}")
        print(f"  Condition: {rule.get('condition')}")
        print(f"  Action: {rule.get('action')}")
        print(f"  Rationale: {rule.get('rationale')}")


def print_patterns(insight):
    patterns = insight.get("patterns", [])

    if not patterns:
        print("- None")
        return

    for pattern in patterns:
        print(f"- {pattern.get('pattern_name')}: {pattern.get('description')}")

        for step in pattern.get("steps", []):
            print(f"  - {step}")


def print_warnings(insight):
    warnings = insight.get("warnings", [])

    if not warnings:
        print("- None")
        return

    for warning in warnings:
        print(f"- Warning: {warning.get('warning')}")
        print(f"  Consequence: {warning.get('consequence')}")
        print(f"  Prevention: {warning.get('prevention')}")


def print_application_patterns(insight):
    application_patterns = insight.get("application_patterns", [])

    if application_patterns:
        for pattern in application_patterns:
            print(f"- {pattern.get('pattern_name')}")
            print(f"  When to use: {pattern.get('when_to_use')}")
            print("  Steps:")

            for step in pattern.get("steps", []):
                print(f"   - {step}")

            print(f"  Notes: {pattern.get('adaptation_notes')}")
    else:
        old_how_to_apply = insight.get("how_to_apply", [])

        if old_how_to_apply:
            for step in old_how_to_apply:
                print(f"- {step}")
        else:
            print("- None")


if __name__ == "__main__":
    query = input("Which concept do you want to explore? ")

    matching_concepts = search_concepts(query)

    if not matching_concepts:
        print("\nNo matching concept found.")
        print("Try using words that are already in your concepts.json file.")
    else:
        for concept in matching_concepts:
            print("\n==============================")
            print(f"Concept: {concept['name']}")
            print(f"Description: {concept['description']}")

            print("\nKeywords:")
            for keyword in concept.get("keywords", []):
                print(f"- {keyword}")

            insights = find_related_insights(concept["id"])
            problems = find_related_problems(insights)

            sources = sorted(
                set(
                    insight.get("source_title", "")
                    for insight in insights
                    if insight.get("source_title", "")
                )
            )

            print("\nSources:")
            if sources:
                for source in sources:
                    print(f"- {source}")
            else:
                print("- None")

            print("\nProblems This Concept Helps With:")
            if problems:
                for problem in problems:
                    print(f"- {problem['name']}: {problem['description']}")
            else:
                print("- None")

            print("\nRelevant Insights:")
            if not insights:
                print("- None")
            else:
                for insight in insights:
                    print("\n------------------------------")
                    print(f"Insight: {insight.get('title')}")
                    print(f"Source: {insight.get('source_title')}")
                    print(f"Section: {insight.get('chapter_or_section')}")
                    print(f"Type: {insight.get('knowledge_type')}")

                    print(f"\nWhat it says:")
                    print(insight.get("what_it_says", ""))

                    print(f"\nWhy it matters:")
                    print(insight.get("why_it_matters", ""))

                    print("\nExamples from source:")
                    print_examples(insight)

                    print("\nDecision rules:")
                    print_decision_rules(insight)

                    print("\nPatterns:")
                    print_patterns(insight)

                    print("\nWarnings:")
                    print_warnings(insight)

                    print("\nApplication patterns:")
                    print_application_patterns(insight)

                    print("\nEvidence:")
                    print(insight.get("evidence", ""))