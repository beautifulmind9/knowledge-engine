import json
from pathlib import Path

DATA_FOLDER = Path("data")
OUTPUTS_FOLDER = Path("outputs")

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


def count_nested_items(insights, key):
    total = 0

    for insight in insights:
        total += len(insight.get(key, []))

    return total


if __name__ == "__main__":
    sources = load_json(SOURCES_FILE)
    concepts = load_json(CONCEPTS_FILE)
    problems = load_json(PROBLEMS_FILE)
    insights = load_json(INSIGHTS_FILE)

    query = input("Which book/source do you want progress for? ")

    source = find_source(query, sources)

    if not source:
        print("\nNo matching source found.")
        exit()

    source_id = source["id"]
    source_title = source["title"]

    source_insights = [
        insight for insight in insights
        if insight.get("source_id") == source_id
    ]

    source_concept_ids = set()
    source_problem_ids = set()
    analyzed_chunk_files = set()

    for insight in source_insights:
        analyzed_chunk_files.add(insight.get("chunk_file", ""))

        for concept_id in insight.get("concept_ids", []):
            source_concept_ids.add(concept_id)

        for problem_id in insight.get("problem_ids", []):
            source_problem_ids.add(problem_id)

    chunk_folder = OUTPUTS_FOLDER / "chunks" / source.get("file_name", "").replace(".pdf", "")

    total_chunks = 0

    if chunk_folder.exists():
        total_chunks = len(list(chunk_folder.glob("chunk_*.txt")))

    analyzed_chunks = len(analyzed_chunk_files)

    remaining_chunks = max(total_chunks - analyzed_chunks, 0)

    coverage = 0

    if total_chunks:
        coverage = (analyzed_chunks / total_chunks) * 100

    print("\n==============================")
    print(f"PROGRESS: {source_title}")
    print("==============================")

    print(f"Total chunks: {total_chunks}")
    print(f"Analyzed chunks: {analyzed_chunks}")
    print(f"Remaining chunks: {remaining_chunks}")
    print(f"Coverage: {coverage:.1f}%")

    print("\nGraph Objects Created:")
    print(f"- Concepts: {len(source_concept_ids)}")
    print(f"- Problems: {len(source_problem_ids)}")
    print(f"- Insights: {len(source_insights)}")

    print("\nExtracted Knowledge Elements:")
    print(f"- Examples: {count_nested_items(source_insights, 'examples_from_source')}")
    print(f"- Decision Rules: {count_nested_items(source_insights, 'decision_rules')}")
    print(f"- Patterns: {count_nested_items(source_insights, 'patterns')}")
    print(f"- Warnings: {count_nested_items(source_insights, 'warnings')}")
    print(f"- Application Patterns: {count_nested_items(source_insights, 'application_patterns')}")

    print("\nProcessing Status:")
    processing = source.get("processing", {})

    if processing:
        for key, value in processing.items():
            print(f"- {key}: {value}")
    else:
        print("- No processing metadata found.")