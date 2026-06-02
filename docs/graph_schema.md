# Graph Schema

## Purpose

The graph stores reusable knowledge extracted from books, articles, research papers, reports, documentation, and other sources.

The goal is not to store summaries.

The goal is to connect concepts, problems, insights, evidence, and applications in a way that supports learning, decision-making, research, writing, and strategy.

---

# Node Types

## Source

A source is where information originates.

Examples:

* Made to Stick
* Atomic Habits
* Thinking, Fast and Slow
* Research paper
* Market report
* Internal documentation

Attributes:

* id
* title
* author
* source_type
* publication_date
* file_name

---

## Concept

A reusable idea that can appear across many sources.

Examples:

* Storytelling
* Simplicity
* Credibility
* Curiosity
* Habit Formation
* Confirmation Bias

Attributes:

* id
* name
* description
* keywords

---

## Problem

A challenge, obstacle, question, or decision that people face.

Examples:

* People forget abstract information
* Audiences do not trust unsupported claims
* Users fail to adopt a new habit
* Investors make emotional decisions

Attributes:

* id
* name
* description

---

## Insight

A specific piece of knowledge extracted from a source.

An insight explains what a source says about a concept and/or problem.

An insight should not only store the idea. It should also store how the source explains, demonstrates, and applies the idea.

Examples:

- Stories are easier to remember than abstract explanations.
- Concrete examples improve understanding.
- Simple ideas are easier to retell.

Attributes:

- id
- source_id
- concept_ids
- problem_ids
- title
- knowledge_type
- what_it_says
- why_it_matters
- examples_from_source
- decision_rules
- patterns
- warnings
- application_patterns
- when_to_use
- when_not_to_use
- tradeoffs
- evidence
- confidence_score
- importance_score
- novelty_score
---

## Insight Example Structure

examples_from_source should capture examples used by the author.

Each example should include:

- example_name
- what_happened
- why_it_matters
- concept_demonstrated
- transferable_lesson

application_patterns should capture reusable ways to apply the insight.

Each application pattern should include:

- pattern_name
- when_to_use
- steps
- adaptation_notes

decision_rules should capture explicit or implied decision-making logic.

Each decision rule should include:

- rule
- condition
- action
- rationale

patterns should capture repeatable structures.

Each pattern should include:

- pattern_name
- description
- steps

warnings should capture mistakes, misconceptions, or risks.

Each warning should include:

- warning
- consequence
- prevention

# Relationship Types

## contains

Source → Concept

Example:

Made to Stick contains Storytelling

---

## discusses

Source → Problem

Example:

Made to Stick discusses why people forget information

---

## supports

Insight → Concept

Example:

Stories are easier to remember supports Storytelling

---

## helps_solve

Concept → Problem

Example:

Storytelling helps solve People forget abstract information

---

## related_to

Concept → Concept

Example:

Storytelling related_to Emotion

---

## extends

Insight → Concept

Example:

A new source adds depth to an existing concept

---

## contradicts

Insight → Insight

Example:

Two sources provide conflicting recommendations

---

# Knowledge Types

* Principle
* Framework
* Mental Model
* Process
* Heuristic
* Observation

---

# Future Queries

The graph should eventually answer questions such as:

* What concepts help solve this problem?
* What do multiple sources say about this concept?
* Which concepts appear most frequently?
* Which concepts contradict each other?
* How can I apply this concept?
* What evidence supports this insight?
* What concepts are related to this concept?
* Which sources discuss this problem?

# Concept Rules

A concept should be:

- Reusable
- General enough to appear in multiple sources
- Distinct from examples
- Distinct from problems

Good Concepts

- Storytelling
- Simplicity
- Curiosity
- Credibility
- Habit Formation
- Confirmation Bias

Not Concepts

- Kidney Heist
- Atlantic City Traveler
- Chapter 1 Example

Examples support concepts.
They are not concepts.

# Problem Rules

A problem should describe:

- A challenge
- A question
- A failure mode
- A decision

Good Problems

- People forget abstract information
- Audiences distrust unsupported claims
- Users fail to adopt new habits

Not Problems

- Storytelling
- Curiosity
- Simplicity

Those are concepts.

# Graph Rules

## Concept Matching Rules

### Exact Match
If a new concept has the same name as an existing concept, reuse the existing concept.

Example:
Storytelling = Storytelling

### Similar Match
If a new concept is similar but not identical, store it as a separate concept and create a relationship.

Example:
Storytelling related_to Narrative Communication

### Different Concept
If the new concept is clearly different, create a new concept with no relationship unless the source clearly connects them.

---

## Why We Do Not Auto-Merge Similar Concepts

Similar concepts may overlap without being identical.

The system should preserve nuance first.

Merging can happen later after review.

---

## Relationship Rule

When two concepts are similar, connected, or often used together, use:

related_to

## Duplicate Review Rule

Repeated examples, patterns, or application patterns are not automatically deleted.

If the same example appears in multiple insights, keep it unless the entries are identical and add no new lesson.

Repeated examples may indicate that the source is using one example to support multiple concepts.