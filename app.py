import json
from pathlib import Path
import streamlit as st

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


sources = load_json(SOURCES_FILE)
concepts = load_json(CONCEPTS_FILE)
problems = load_json(PROBLEMS_FILE)
insights = load_json(INSIGHTS_FILE)

st.set_page_config(
    page_title="Knowledge Engine",
    layout="wide"
)

st.title("Knowledge Engine")
st.write("Turn books into concepts, problems, insights, examples, patterns, and decision rules.")

page = st.sidebar.radio(
    "Choose a view",
    [
        "Source Overview",
        "Explore Concept",
        "Search by Problem",
        "Apply Knowledge"
    ]
)


def get_source_insights(source_id):
    return [
        insight for insight in insights
        if insight.get("source_id") == source_id
    ]


def get_items_by_ids(items, ids):
    return [
        item for item in items
        if item.get("id") in ids
    ]


if page == "Source Overview":
    st.header("Source Overview")

    source_titles = [source["title"] for source in sources]
    selected_title = st.selectbox("Select a source", source_titles)

    source = next(
        source for source in sources
        if source["title"] == selected_title
    )

    source_insights = get_source_insights(source["id"])

    st.subheader(source["title"])
    st.write(f"Author: {source.get('author')}")
    st.write(f"Type: {source.get('source_type')}")
    st.write(f"Insights extracted: {len(source_insights)}")

    concept_ids = sorted(
        set(
            concept_id
            for insight in source_insights
            for concept_id in insight.get("concept_ids", [])
        )
    )

    problem_ids = sorted(
        set(
            problem_id
            for insight in source_insights
            for problem_id in insight.get("problem_ids", [])
        )
    )

    source_concepts = get_items_by_ids(concepts, concept_ids)
    source_problems = get_items_by_ids(problems, problem_ids)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Concepts")
        for concept in source_concepts:
            st.write(f"**{concept.get('name')}**")
            st.write(concept.get("description"))

    with col2:
        st.subheader("Problems")
        for problem in source_problems:
            st.write(f"**{problem.get('name')}**")
            st.write(problem.get("description"))

    st.subheader("Insights")

    for insight in source_insights:
        with st.expander(insight.get("title", "Untitled insight")):
            st.write("**What it says**")
            st.write(insight.get("what_it_says", ""))

            st.write("**Why it matters**")
            st.write(insight.get("why_it_matters", ""))

            st.write("**Evidence**")
            st.write(insight.get("evidence", ""))


if page == "Explore Concept":
    st.header("Explore Concept")

    concept_names = [concept["name"] for concept in concepts]
    selected_concept_name = st.selectbox("Select a concept", concept_names)

    concept = next(
        concept for concept in concepts
        if concept["name"] == selected_concept_name
    )

    concept_insights = [
        insight for insight in insights
        if concept["id"] in insight.get("concept_ids", [])
    ]

    st.subheader(concept["name"])
    st.write(concept.get("description"))

    st.write("### Related Insights")

    for insight in concept_insights:
        with st.expander(insight.get("title", "Untitled insight")):
            st.write(insight.get("what_it_says", ""))

            st.write("**Decision Rules**")
            for rule in insight.get("decision_rules", []):
                st.write(f"- {rule.get('rule')}")

            st.write("**Patterns**")
            for pattern in insight.get("patterns", []):
                st.write(f"- {pattern.get('pattern_name')}: {pattern.get('description')}")

            st.write("**Examples**")
            for example in insight.get("examples_from_source", []):
                st.write(f"- {example.get('example_name')}: {example.get('transferable_lesson')}")


if page == "Search by Problem":
    st.header("Search by Problem")

    query = st.text_input("What problem are you trying to solve?")

    if query:
        matching_problems = []

        for problem in problems:
            text = f"{problem.get('name', '')} {problem.get('description', '')}".lower()

            if any(word in text for word in query.lower().split()):
                matching_problems.append(problem)

        if not matching_problems:
            st.warning("No matching problems found yet.")
        else:
            for problem in matching_problems:
                st.subheader(problem["name"])
                st.write(problem["description"])

                related_insights = [
                    insight for insight in insights
                    if problem["id"] in insight.get("problem_ids", [])
                ]

                for insight in related_insights:
                    with st.expander(insight.get("title", "Untitled insight")):
                        st.write(insight.get("what_it_says", ""))

                        st.write("**Application Patterns**")
                        for pattern in insight.get("application_patterns", []):
                            st.write(f"- {pattern.get('pattern_name')}")
                            for step in pattern.get("steps", []):
                                st.write(f"  - {step}")


if page == "Apply Knowledge":
    st.header("Apply Knowledge")

    st.write("Describe a real situation. The app will help you think through relevant concepts, decision rules, and patterns.")

    situation = st.text_area("What are you trying to do?")

    if situation:
        st.subheader("Suggested lenses to consider")

        keywords = situation.lower().split()

        matching_insights = []

        for insight in insights:
            searchable_text = " ".join([
                insight.get("title", ""),
                insight.get("what_it_says", ""),
                insight.get("why_it_matters", ""),
                " ".join(insight.get("keywords", []))
            ]).lower()

            if any(word in searchable_text for word in keywords):
                matching_insights.append(insight)

        if not matching_insights:
            st.warning("No direct matches found yet. Try using words like communication, message, attention, simplicity, decision, or audience.")
        else:
            for insight in matching_insights[:10]:
                with st.expander(insight.get("title", "Untitled insight")):
                    st.write("**What it says**")
                    st.write(insight.get("what_it_says", ""))

                    st.write("**Decision Rules**")
                    for rule in insight.get("decision_rules", []):
                        st.write(f"- {rule.get('rule')}")

                    st.write("**Application Patterns**")
                    for pattern in insight.get("application_patterns", []):
                        st.write(f"- {pattern.get('pattern_name')}")
                        for step in pattern.get("steps", []):
                            st.write(f"  - {step}")

                    st.write("**Examples**")
                    for example in insight.get("examples_from_source", []):
                        st.write(f"- {example.get('example_name')}: {example.get('transferable_lesson')}")