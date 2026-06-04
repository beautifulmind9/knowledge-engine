import json
from pathlib import Path

DATA_FOLDER = Path("data")

PROBLEMS_FILE = DATA_FOLDER / "problems.json"
CONCEPTS_FILE = DATA_FOLDER / "concepts.json"
INSIGHTS_FILE = DATA_FOLDER / "insights.json"
RELATIONSHIPS_FILE = DATA_FOLDER / "relationships.json"


def load_json(file_path):
    text = file_path.read_text(encoding="utf-8").strip()

    if not text:
        return []

    return json.loads(text)


def simple_match(query, text):
    query_words = query.lower().split()
    text_lower = text.lower()

    return any(word in text_lower for word in query_words)


def search_problems(query):
    problems = load_json(PROBLEMS_FILE)

    matches = []

    for problem in problems:
        searchable_text = f"{problem.get('name', '')} {problem.get('description', '')}"

        if simple_match(query, searchable_text):
            matches.append(problem)

    return matches


def find_related_concepts(problem_id):
    relationships = load_json(RELATIONSHIPS_FILE)
    concepts = load_json(CONCEPTS_FILE)

    concept_ids = []

    for relationship in relationships:
        if relationship["relationship"] == "helps_solve" and relationship["to"] == problem_id:
            concept_ids.append(relationship["from"])

    related_concepts = [
        concept for concept in concepts
        if concept["id"] in concept_ids
    ]

    return related_concepts


def find_related_insights(problem_id):
    insights = load_json(INSIGHTS_FILE)

    related_insights = []

    for insight in insights:
        if problem_id in insight.get("problem_ids", []):
            related_insights.append(insight)

    return related_insights


if __name__ == "__main__":
    query = input("What problem are you trying to solve? ")

    matching_problems = search_problems(query)

    if not matching_problems:
        print("\nNo matching problems found yet.")
        print("Try using words that are already in your problems.json file.")
    else:
        for problem in matching_problems:
            print("\n==============================")
            print(f"Problem: {problem['name']}")
            print(f"Description: {problem['description']}")

            concepts = find_related_concepts(problem["id"])
            insights = find_related_insights(problem["id"])

            print("\nRelated Concepts:")
            for concept in concepts:
                print(f"- {concept['name']}: {concept['description']}")

            print("\nRelevant Insights:")
            for insight in insights:
                print(f"- {insight['title']}")
                print(f"  What it says: {insight['what_it_says']}")
                print("  How to apply:")
                for step in insight.get("how_to_apply", []):
                    print(f"   - {step}")