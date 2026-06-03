# Product Vision

## Working Name

Knowledge Engine

## Core Idea

Knowledge Engine turns books, articles, PDFs, and other sources into reusable knowledge that can be searched, explored, and applied to real problems.

The goal is not only to summarize books. The goal is to extract concepts, problems, insights, patterns, examples, decision rules, warnings, and application methods so users can apply knowledge without needing to reread or manually synthesize every source.

## Core Product Shift

Traditional reading tools help users store information.

This product helps users apply information.

The product is moving from a knowledge graph prototype toward a combined system:

```text
Personal Knowledge Library
+
Knowledge Workshop
```

## Main User Need

Users often consume books, courses, articles, and research but struggle to retrieve and apply what they learned when facing a real decision, writing task, communication problem, business challenge, or learning goal.

Many users also do not want to read every book cover to cover. They want to benefit from trusted sources, understand the useful ideas, and apply those ideas to their own goals.

## Core Workflow

1. User uploads or processes a source.
2. The system extracts reusable knowledge.
3. The user organizes sources into a personal library.
4. The user searches by source, concept, problem, chapter, chapter group, example, or decision rule.
5. The user chooses what they want to do with the gathered knowledge.
6. The system helps transform relevant knowledge into a usable output.

## Key Differentiator

The product is not only a chat-with-PDF tool.

It builds a structured knowledge layer:

- Sources
- Concepts
- Problems
- Insights
- Decision Rules
- Patterns
- Examples
- Warnings
- Application Patterns
- Relationships

The product then uses that structured layer inside a workshop experience where users can create, edit, decide, study, plan, and communicate.

## Personal Knowledge Library

Each user should eventually be able to create their own private library of sources.

Example libraries:

- Copywriting
- Product Strategy
- Finance
- Founder Storytelling
- Research
- Learning

A user might upload books, PDFs, reports, papers, articles, notes, or internal documents and organize them around topics they care about.

The library is not meant to be a shared public archive of books. It is a private workspace where users process and apply their own sources.

## Knowledge Workshop

The Knowledge Workshop is where retrieved knowledge becomes useful output.

Instead of only asking:

```text
What does this source say?
```

The user can ask:

```text
What do I want to do with this knowledge?
```

Possible workshop modes:

- Create or edit writing
- Generate a copywriting brief
- Make a decision
- Create a study guide
- Build a playbook
- Prepare a presentation
- Generate product messaging
- Create a founder narrative

## Example Use Case: Asking for Help

A user wants to ask a friend for help but is unsure how to communicate clearly.

The system retrieves ideas from communication books such as:

- Find the core
- Lead with the most important message
- Be concrete
- Make the ask clear
- Use intent-based communication

The system then helps the user draft a clearer message.

## Example Use Case: Ovara Messaging

A user wants to explain Ovara clearly on LinkedIn, in website copy, or in a founder story.

The system retrieves relevant ideas from communication, copywriting, business, and strategy sources.

It then produces a workshop brief with:

- Core message
- Audience problem
- Concepts to use
- Writing rules
- Examples to borrow from
- Warnings to avoid
- Draft starter
- Revision checklist

## Long-Term Vision

A user should be able to ask:

- How do I communicate Ovara clearly?
- How do I validate this product idea?
- How do I write a better landing page?
- How do I make this message more persuasive?
- How do I apply what I learned from my copywriting library?
- How do I use my product strategy library to make a decision?

The system should synthesize relevant knowledge from multiple books and sources into:

- Recommendations
- Drafts
- Decision rules
- Playbooks
- Examples
- Action plans
- Study guides
- Copywriting briefs
- Founder messaging

## Product Direction

The strongest direction is a Knowledge Application Engine.

The user does not only ask what a book says. The user describes a real problem, chooses a goal, and the system retrieves relevant knowledge and helps them apply it.

The strongest product model is:

```text
User
↓
Private Library
↓
Sources
↓
Extracted Knowledge
↓
Workshop
↓
Saved Outputs
```

## Interface Direction

The current Streamlit app is a prototype interface. It is useful for validating the workflows quickly.

The long-term interface should likely move toward a custom web application because the product experience is becoming a workspace, not a dashboard.

Future interface needs may include:

- User accounts
- Private libraries
- Source upload flows
- Processing status
- Search across a library
- Side-by-side knowledge and writing panels
- Editable writing canvas
- Saved drafts
- Export options
- Project folders
- Better navigation and visual hierarchy

## Copyright and Source Handling Direction

The intended product direction is private, user-controlled processing:

- Users upload their own legally accessed materials.
- The app processes sources privately for that user.
- The system avoids storing or redistributing original copyrighted text.
- The product stores structured user-generated knowledge only where appropriate and with user control.
- Future versions should support temporary workspaces, deletion controls, source retention settings, and public-safe sample data.

## Why This Matters

People do not only need more information.

They need better ways to turn information into:

- Clearer writing
- Better decisions
- Stronger communication
- Faster learning
- Practical action
- More confident execution

Knowledge Engine exists to help users move from reading and collecting knowledge to actually using it.
