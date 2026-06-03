# Interface Strategy

## Current Interface

The current interface is built with Streamlit.

Streamlit is being used as a prototype interface because it allows the project to move quickly while the product workflow is still being discovered and validated.

The current Streamlit app is useful for testing:

- Source exploration
- Concept exploration
- Problem search
- Knowledge Workshop workflows
- Writing Workshop briefs
- Retrieval quality
- Early product assumptions

## Why Streamlit Was Used First

At this stage, the most important question was not visual polish.

The most important question was whether the system could:

1. Extract useful knowledge from sources.
2. Organize that knowledge into reusable structures.
3. Retrieve relevant concepts, problems, insights, examples, and decision rules.
4. Apply retrieved knowledge to a real user goal.

Streamlit helped validate those workflows quickly without requiring a full frontend, backend API, authentication, database, and deployment stack.

## Limitations of Streamlit

Streamlit is useful for prototypes, but it is limited for the long-term product vision.

The product is becoming a workspace, not a dashboard.

A real Knowledge Workshop needs:

- Editable writing canvas
- Saved drafts
- Side-by-side knowledge and output panels
- Private user libraries
- Source upload flows
- Processing status
- Better navigation
- Project folders
- User accounts
- Authentication
- Export options
- Version history
- More polished interaction design

Streamlit can simulate some of these ideas, but the experience will become clunky as the product grows.

## Long-Term Interface Direction

The long-term direction should likely move toward a custom web application.

Suggested architecture:

```text
Frontend
- Next.js or React
- Custom workspace UI
- Editable writing canvas
- Library dashboard
- Workshop views

Backend
- Python
- FastAPI
- Knowledge extraction pipeline
- Retrieval logic
- Workshop generation logic

Database
- PostgreSQL or Supabase
- Users
- Libraries
- Sources
- Concepts
- Problems
- Insights
- Workspaces
- Outputs

File Storage
- Supabase Storage, S3, or equivalent
- User-uploaded source files
- Temporary processing files
```

## Target Product Experience

The target experience is:

```text
Personal Knowledge Library
+
Knowledge Workshop
```

A user should be able to:

1. Upload and organize sources into private libraries.
2. Extract reusable knowledge from those sources.
3. Search across books, topics, concepts, problems, examples, and decision rules.
4. Choose what they want to do with the gathered knowledge.
5. Generate, edit, save, and export useful outputs.

## Example Future Layout

```text
Left Panel
- Libraries
- Sources
- Topics
- Search

Center Panel
- Writing canvas
- Draft
- Brief
- Playbook
- Study guide

Right Panel
- Relevant concepts
- Decision rules
- Examples
- Warnings
- Source evidence
```

## Current Decision

Continue using Streamlit only for early validation.

Do not treat Streamlit as the final product interface.

Once the Knowledge Workshop workflow is validated, plan a migration toward a custom frontend and backend architecture.

## Near-Term Interface Goals

Before migration, use Streamlit to test:

- Generated Draft section
- Copywriting brief output
- Editable draft assumptions
- Example Explorer
- Decision Rule Explorer
- Source selection for workshops
- Multi-source workshop behavior

## Product Principle

The interface should not feel like a database viewer.

It should feel like a workspace where users turn their private knowledge libraries into writing, decisions, learning materials, presentations, and plans.
