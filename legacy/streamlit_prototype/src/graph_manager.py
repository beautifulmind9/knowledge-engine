import json
from pathlib import Path

DATA_FOLDER = Path("data")

CONCEPTS_FILE = DATA_FOLDER / "concepts.json"
PROBLEMS_FILE = DATA_FOLDER / "problems.json"
INSIGHTS_FILE = DATA_FOLDER / "insights.json"
RELATIONSHIPS_FILE = DATA_FOLDER / "relationships.json"


def load_json(file_path):
    if not file_path.exists():
        return []

    text = file_path.read_text(encoding="utf-8").strip()

    if not text:
        return []

    return json.loads(text)


def save_json(file_path, data):
    file_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def make_id(prefix, existing_items):
    next_number = len(existing_items) + 1
    return f"{prefix}_{next_number:03}"


def find_by_name(items, name):
    name_clean = name.strip().lower()

    for item in items:
        if item.get("name", "").strip().lower() == name_clean:
            return item

    return None


def add_concept(name, description="", keywords=None):
    concepts = load_json(CONCEPTS_FILE)

    existing = find_by_name(concepts, name)

    if existing:
        return existing

    new_concept = {
        "id": make_id("concept", concepts),
        "name": name,
        "description": description,
        "keywords": keywords or []
    }

    concepts.append(new_concept)
    save_json(CONCEPTS_FILE, concepts)

    return new_concept


def add_problem(name, description=""):
    problems = load_json(PROBLEMS_FILE)

    existing = find_by_name(problems, name)

    if existing:
        return existing

    new_problem = {
        "id": make_id("problem", problems),
        "name": name,
        "description": description
    }

    problems.append(new_problem)
    save_json(PROBLEMS_FILE, problems)

    return new_problem


def add_insight(insight):
    insights = load_json(INSIGHTS_FILE)

    insight["id"] = make_id("insight", insights)

    insights.append(insight)
    save_json(INSIGHTS_FILE, insights)

    return insight


def add_relationship(from_id, relationship, to_id, evidence=""):
    relationships = load_json(RELATIONSHIPS_FILE)

    new_relationship = {
        "from": from_id,
        "relationship": relationship,
        "to": to_id,
        "evidence": evidence
    }

    relationships.append(new_relationship)
    save_json(RELATIONSHIPS_FILE, relationships)

    return new_relationship


if __name__ == "__main__":
    concept = add_concept(
        name="Storytelling",
        description="Using narrative to make ideas easier to understand, remember, and share.",
        keywords=["stories", "narrative", "memory", "communication"]
    )

    problem = add_problem(
        name="People forget abstract information",
        description="Important ideas are not remembered because they are too vague, complex, or disconnected from experience."
    )

    insight = add_insight({
        "source_id": "source_001",
        "source_title": "Made to Stick",
        "author": "Chip Heath & Dan Heath",
        "chunk_file": "outputs/chunks/Made to Stick - Chip and Dan Heath/chunk_001.txt",
        "chapter_or_section": "Introduction - What Sticks?",
        "concept_ids": [concept["id"]],
        "problem_ids": [problem["id"]],
        "title": "Stories make ideas easier to remember and retell",
        "knowledge_type": "Principle",
        "what_it_says": "Stories are easier to understand, remember, and retell than abstract explanations.",
        "how_to_apply": [
            "Use a concrete situation.",
            "Create a clear sequence of events.",
            "Include memorable details.",
            "Make the outcome easy to retell."
        ],
        "examples": [
            "The Kidney Heist urban legend."
        ],
        "when_to_use": [
            "When explaining an idea people need to remember.",
            "When trying to make information easier to retell.",
            "When communicating with a broad audience."
        ],
        "when_not_to_use": [
            "When precision matters more than memorability.",
            "When a technical specification is required."
        ],
        "tradeoffs": [
            "Stories improve recall but may simplify complex ideas."
        ],
        "keywords": [
            "storytelling",
            "memory",
            "communication",
            "retelling"
        ],
        "confidence_score": 5,
        "importance_score": 5,
        "novelty_score": 3,
        "evidence": "The Kidney Heist is a story that sticks. We understand it, we remember it, and we can retell it later.",
        "extraction_date": "2026-05-31"
    })

    add_relationship("source_001", "contains", concept["id"])
    add_relationship("source_001", "discusses", problem["id"])
    add_relationship(insight["id"], "supports", concept["id"])
    add_relationship(concept["id"], "helps_solve", problem["id"])

    print("Graph updated.")