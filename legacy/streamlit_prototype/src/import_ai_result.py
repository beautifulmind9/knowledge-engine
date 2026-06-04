import json
from pathlib import Path

from graph_manager import (
    add_concept,
    add_problem,
    add_insight,
    add_relationship,
)

RESULT_FOLDER = Path("outputs/analysis")
RESULT_FILES = sorted(RESULT_FOLDER.glob("chunk_*_ai_result.json"))


def load_json(file_path):
    text = file_path.read_text(encoding="utf-8").strip()

    if not text:
        return {}

    return json.loads(text)


def import_ai_result(result):
    concept_id_map = {}
    problem_id_map = {}

    for concept in result.get("concepts", []):
        saved_concept = add_concept(
            name=concept.get("name", ""),
            description=concept.get("description", ""),
            keywords=concept.get("keywords", []),
        )

        concept_id_map[concept.get("id", "")] = saved_concept["id"]
        concept_id_map[concept.get("name", "")] = saved_concept["id"]

    for problem in result.get("problems", []):
        saved_problem = add_problem(
            name=problem.get("name", ""),
            description=problem.get("description", ""),
        )

        problem_id_map[problem.get("id", "")] = saved_problem["id"]
        problem_id_map[problem.get("name", "")] = saved_problem["id"]

    for insight in result.get("insights", []):
        concept_ids = [
            concept_id_map.get(concept_id, concept_id)
            for concept_id in insight.get("concept_ids", [])
        ]

        problem_ids = [
            problem_id_map.get(problem_id, problem_id)
            for problem_id in insight.get("problem_ids", [])
        ]

        insight["concept_ids"] = concept_ids
        insight["problem_ids"] = problem_ids

        saved_insight = add_insight(insight)

        add_relationship(
            insight.get("source_id", ""),
            "contains",
            saved_insight["id"]
        )

        for concept_id in concept_ids:
            add_relationship(saved_insight["id"], "supports", concept_id)
            add_relationship(insight.get("source_id", ""), "contains", concept_id)

        for problem_id in problem_ids:
            add_relationship(saved_insight["id"], "addresses", problem_id)
            add_relationship(insight.get("source_id", ""), "discusses", problem_id)

        for concept_id in concept_ids:
            for problem_id in problem_ids:
                add_relationship(concept_id, "helps_solve", problem_id)

    for relationship in result.get("relationships", []):
        from_id = relationship.get("from", "")
        to_id = relationship.get("to", "")

        from_id = concept_id_map.get(from_id, problem_id_map.get(from_id, from_id))
        to_id = concept_id_map.get(to_id, problem_id_map.get(to_id, to_id))

        add_relationship(
            from_id=from_id,
            relationship=relationship.get("relationship", ""),
            to_id=to_id,
            evidence=relationship.get("evidence", ""),
        )


if __name__ == "__main__":
    print(f"Found {len(RESULT_FILES)} AI result file(s).")

    for result_file in RESULT_FILES:
        print(f"Importing: {result_file}")
        result = load_json(result_file)
        import_ai_result(result)

    print("All AI results imported into graph.")