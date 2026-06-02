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


def find_source(query):
    sources = load_json(SOURCES_FILE)
    query_lower = query.lower()

    for source in sources:
        title = source.get("title", "").lower()
        author = source.get("author", "").lower()
        file_name = source.get("file_name", "").lower()

        if query_lower in title or query_lower in author or query_lower in file_name:
            return source

    return None


def get_items_by_ids(items, ids):
    return [item for item in items if item.get("id") in ids]


if __name__ == "__main__":
    query = input("Which book/source do you want to explore? ")

    source = find_source(query)

    if not source:
        print("\nNo matching source found.")
    else:
        concepts = load_json(CONCEPTS_FILE)
        problems = load_json(PROBLEMS_FILE)
        insights = load_json(INSIGHTS_FILE)

        source_insights = [
            insight for insight in insights
            if insight.get("source_id") == source["id"]
        ]

        print("\n==============================")
        print(f"Source: {source['title']}")
        print(f"Author: {source['author']}")
        print(f"Type: {source['source_type']}")
        print(f"File: {source['file_name']}")
        print("==============================")

        if not source_insights:
            print("\nNo insights found for this source yet.")
        else:
            print(f"\nInsights Found: {len(source_insights)}")

            for insight in source_insights:
                related_concepts = get_items_by_ids(
                    concepts,
                    insight.get("concept_ids", [])
                )

                related_problems = get_items_by_ids(
                    problems,
                    insight.get("problem_ids", [])
                )

                print("\n------------------------------")
                print(f"Insight: {insight.get('title')}")
                print(f"Type: {insight.get('knowledge_type')}")
                print(f"Section: {insight.get('chapter_or_section')}")
                print(f"What it says: {insight.get('what_it_says')}")

                print("\nConcepts:")
                for concept in related_concepts:
                    print(f"- {concept.get('name')}")

                print("\nProblems:")
                for problem in related_problems:
                    print(f"- {problem.get('name')}")

                print("\nHow to apply:")
                for step in insight.get("how_to_apply", []):
                    print(f"- {step}")

                print("\nEvidence:")
                print(insight.get("evidence", ""))