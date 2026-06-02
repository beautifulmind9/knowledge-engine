# Knowledge Engine

Knowledge Engine turns source material into reusable knowledge that can be searched, explored, and applied to real problems.

This project started as a way to extract useful ideas from books and PDFs. It is evolving into a knowledge application engine: a system that does not only summarize sources, but breaks them into concepts, problems, insights, examples, decision rules, patterns, warnings, and application methods.

The goal is simple:

> Help people use what they have learned when they actually need it.

---

## Why This Exists

People often read books, articles, papers, and reports but struggle to retrieve the right idea at the right moment.

The problem is not only information access.

The deeper problem is application:

- I know I read something useful, but I cannot remember where.
- I understand the idea, but I do not know how to apply it.
- I do not want to read five books before solving one practical problem.
- I need the decision rule, example, framework, or pattern hidden inside the source.

Knowledge Engine is built around that gap.

Instead of asking only, “What does this book say?” the system is being designed to answer:

- What problem does this help solve?
- What concept is being taught?
- What decision rule can I use?
- What example makes this clearer?
- How can I apply this to a real situation?

---

## What It Does

The current prototype can:

- Extract text from PDFs
- Split extracted text into chunks
- Generate AI analysis prompts for each chunk
- Import structured AI results into JSON graph files
- Store sources, concepts, problems, insights, and relationships
- Track decision rules, examples, warnings, patterns, and application patterns
- Validate and clean the graph
- Explore knowledge by source, concept, problem, chapter, and chapter group
- Track book processing progress
- Produce source-level summaries
- Run a basic Streamlit interface

---

## Knowledge Structure

The system currently organizes knowledge like this:

```text
Source
↓
Concepts
↓
Problems
↓
Insights
↓
Patterns
↓
Examples
```

Additional layers include:

- Decision Rules
- Warnings
- Application Patterns
- Relationships
- Source Classification
- Chapter Groups
- Extraction Lenses

This structure allows the same source to be explored in different ways.

For example, a user can ask:

- What does this source teach?
- What concepts appear in this source?
- What problems does this source help solve?
- What did this chapter teach?
- What examples support this idea?
- What decision rules can I apply?

---

## Example Use Case

A user has a real communication problem:

> I need to ask a friend for help, but I do not know how to say it clearly.

The system can apply knowledge extracted from communication books, such as:

- Find the core message
- Lead with the most important information
- Be concrete
- Make the ask clear
- Use intent-based communication

Instead of only summarizing a book, the system helps turn knowledge into action.

---

## Current Scripts

### Extraction

- `src/extract_pdf.py` — extracts text from PDFs
- `src/chunk_text.py` — splits text into manageable chunks
- `src/analyze_chunks.py` — generates structured analysis prompts
- `src/import_ai_result.py` — imports AI-generated JSON into the graph

### Graph Management

- `src/graph_manager.py` — handles adding graph objects
- `src/clean_graph.py` — removes exact duplicate graph entries
- `src/graph_validator.py` — checks graph health
- `src/knowledge_audit.py` — audits duplicate patterns, examples, and other nested items
- `src/find_similar_insights.py` — early experiment for similarity checking

### Exploration

- `src/explore_source.py` — explores a full source
- `src/explore_concept.py` — explores a concept and related insights
- `src/search_by_problem.py` — searches by problem
- `src/explore_chapter.py` — explores a chapter or section
- `src/explore_chapter_group.py` — explores a group of chapters
- `src/summarize_source.py` — creates a source-level summary
- `src/book_progress.py` — tracks extraction progress

### App

- `app.py` — early Streamlit interface

---

## Streamlit App

Install requirements:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
python -m streamlit run app.py
```

The first interface includes:

- Source Overview
- Explore Concept
- Search by Problem
- Apply Knowledge

---

## Current Status

This is an active prototype.

The project currently uses one source as a test case and is being expanded carefully to validate the schema before scaling to more books and domains.

The priority is not only adding more sources. The priority is making sure the knowledge structure is useful, reusable, and applicable.

---

## Roadmap

Near-term:

- Improve Streamlit interface
- Build Example Explorer
- Build Decision Rule Explorer
- Add graph normalization rules
- Improve Apply Knowledge workflow
- Add public-safe sample data
- Strengthen portfolio documentation

Medium-term:

- Support multiple sources on the same topic
- Generate topic-level playbooks
- Generate copywriting briefs
- Generate founder messaging drafts
- Generate learning paths
- Improve problem-to-knowledge retrieval

Long-term:

- Private upload workspace
- Temporary source processing
- User-controlled knowledge vault
- Multi-source synthesis
- Knowledge application assistant

---

## Portfolio Focus

This repo is intended to show more than code.

It demonstrates:

- Product thinking
- Knowledge architecture
- AI-assisted workflow design
- Information extraction
- Structured data modeling
- Iterative prototyping
- Human-centered application of knowledge

The project is being built in public as both a working tool and a record of the reasoning behind the tool.

---

## Copyright and Source Handling Note

The intended product direction is a private, user-controlled processing model.

Users should process sources they have the right to use. Future versions should avoid storing or redistributing copyrighted source text and should support temporary processing, deletion controls, and public-safe sample datasets.

---

## License

MIT License.
