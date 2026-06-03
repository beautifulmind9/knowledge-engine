# Roadmap

## Phase 1: Knowledge Engine Foundation

### Completed

- PDF extraction
- Chunking
- AI prompt generation
- Knowledge graph storage
- Graph validation
- Graph cleaning
- Source exploration
- Concept exploration
- Chapter exploration
- Chapter group exploration
- Problem search
- Progress tracking
- Knowledge audit
- Streamlit prototype
- Knowledge Workshop prototype
- Writing Workshop Brief prototype

### Next

- Example Explorer
- Decision Rule Explorer
- Graph normalization
- Improve Knowledge Workshop outputs
- Add generated draft section
- Add public-safe sample data

---

## Phase 2: Knowledge Application Engine

Goal:

Move from knowledge retrieval to knowledge application.

Features:

- Apply knowledge to writing
- Apply knowledge to communication
- Apply knowledge to business decisions
- Apply knowledge to product development
- Apply knowledge to job searching
- Apply knowledge to founder storytelling
- Generate copywriting briefs
- Generate revision checklists
- Generate draft starters

Core workflow:

```text
Situation
↓
Relevant knowledge
↓
Chosen goal
↓
Usable output
```

---

## Phase 3: Multi-Source Synthesis

Goal:

Answer questions using knowledge from multiple sources.

Examples:

- How do I validate a startup idea?
- How do I write better copy?
- How do I communicate strategy?
- How do I explain Ovara clearly?

Output:

- Concepts
- Insights
- Decision Rules
- Patterns
- Examples
- Recommendations
- Drafts
- Playbooks

---

## Phase 4: Personal Knowledge Libraries

Goal:

Allow each user to build and maintain their own private library of books, articles, PDFs, reports, notes, and other sources.

User story:

As a user, I want to upload and organize my own books and sources into private libraries so that I can build a reusable knowledge base around topics I care about.

Example libraries:

- Copywriting
- Product Strategy
- Finance
- Founder Storytelling
- Research
- Learning

Core workflow:

```text
User
↓
Library
↓
Sources
↓
Extracted knowledge
↓
Workshop
↓
Saved outputs
```

Possible features:

- User accounts
- Private libraries
- Source uploads
- Topic folders
- Source processing status
- Search across one source
- Search across a full library
- Save generated briefs and drafts
- Reprocess a source
- Delete uploaded files and extracted knowledge
- Export outputs

Architecture implications:

- Move from local JSON files to a database
- Add user authentication
- Add file storage
- Add source retention settings
- Add deletion controls
- Separate user libraries from public demo data

Copyright and privacy direction:

- Users upload their own legally accessed materials.
- The app processes sources privately for that user.
- The app should not provide a shared public library of copyrighted books.
- Users should be able to delete uploaded files and generated knowledge.
- Public demos should use public-domain, licensed, or synthetic sample data.

---

## Phase 5: Productization

Possible products:

- Personal Knowledge Library
- Knowledge Workshop
- Founder Assistant
- Copywriting Assistant
- Learning Assistant
- Research Assistant
- Decision Support Assistant

Long-term product direction:

```text
Personal Knowledge Library
+
Knowledge Workshop
```

The strongest product direction is not only storing knowledge. It is helping users apply their own libraries to writing, decision-making, learning, strategy, and communication.
