# User Stories

## Apply Knowledge to a Real Situation

As a user,

I want to describe a real-world situation,

So that the system can retrieve relevant concepts, insights, examples, patterns, and decision rules and help me take action.

Example:

Improve a message asking a friend for help.

---

## Use Knowledge in a Workshop

As a user,

I want to choose what I want to do with gathered knowledge,

So that the system can transform retrieved concepts, insights, examples, patterns, decision rules, and warnings into a useful output.

### Why This Matters

Retrieving knowledge is useful, but users usually want to do something with it.

They may want to write, decide, study, plan, explain, teach, present, or build.

The app should therefore behave less like a static search tool and more like a workspace where gathered knowledge can be shaped into an outcome.

### Example Goal

Create and edit writing.

### Example Use Case

The user is building Ovara and wants to communicate the product clearly on LinkedIn, in website copy, or in a founder story.

The system retrieves relevant knowledge from communication and copywriting sources, then turns that knowledge into a writing brief, draft starter, and revision checklist.

### Input

- Situation
- Goal
- Audience
- Constraints
- Output type
- Tone or style preferences

### Possible Output Modes

- Create or edit writing
- Generate a copywriting brief
- Make a decision
- Create a study guide
- Build a playbook
- Prepare a presentation
- Generate product messaging
- Create a founder narrative

### Output for Writing Mode

- Writing goal
- Audience
- Core message
- Audience problem
- Relevant concepts
- Decision rules to apply
- Examples to learn from
- Warnings to avoid
- Draft starter
- Revision checklist

### Product Insight

The core product is not only knowledge retrieval.

The stronger product is knowledge application.

A user should be able to gather knowledge from books and sources, then enter a workshop mode that helps them turn the knowledge into something they can use.

---

## Preserve Individuality While Using Creative Knowledge

### User Story

As a creator,

I want Workshop to use knowledge from film, photography, editing, design, storytelling, and other creative sources to help me understand and explore creative choices without optimizing me toward generic best practices,

So that I can make more intentional decisions while preserving my own visual language, personality, memories, cultural context, imperfections, instincts, and preferences.

### Context

Creative sources often describe principles, conventions, examples, patterns, and techniques that explain why particular choices work. Those sources are useful as a vocabulary for thinking, but they should not become a hidden scoring system for what a creator's work ought to look like.

Workshop should therefore use creative knowledge to expand the creator's option space. It should explain effects, trade-offs, precedents, and possible directions while keeping the creator's intent and identity authoritative.

A convention is evidence that a choice can work in a particular context. It is not automatically a prescription.

### Example Use Case

The creator is editing a personal video and asks how to approach the color grade.

Workshop retrieves relevant knowledge about color relationships, contrast, mood, visual hierarchy, and examples from film.

The footage already has a warm, slightly uneven home-video quality that carries personal meaning.

Instead of deciding that the footage should be corrected into a conventional cinematic palette, Workshop explains several viable directions. It may explain what stronger complementary contrast would do, what preserving the existing warmth would do, what desaturation would change, and what may be lost if the footage is made technically cleaner.

The creator can then choose, combine, reject, or deliberately invert those directions.

### Preconditions

- Relevant creative knowledge has been extracted from one or more sources.
- The creator has provided a creative task, work-in-progress, or enough project context to describe the decision being made.
- The creator can provide intent, feeling, references, constraints, or preferences when those are important to the decision.
- When creator preferences are unknown, Workshop must not invent a personal style profile and present it as fact.

### Inputs That May Matter

- Creative work or project context
- Creator's goal or intended feeling
- Relevant source knowledge
- Creator-provided references
- Known creator preferences or prior choices, where available and appropriate
- Cultural or personal context the creator chooses to provide
- Constraints such as platform, duration, format, audience, equipment, or editing limits
- Elements the creator explicitly wants preserved

### Expected Workshop Behavior

Workshop should:

- Explain why a creative choice may work and under what conditions.
- Distinguish conventions, precedents, and common techniques from requirements.
- Offer multiple meaningful directions when more than one direction could satisfy the creator's intent.
- Explain the trade-offs, emotional effects, or communicative consequences of those directions.
- Use source knowledge as a lens for understanding rather than a hidden aesthetic ranking system.
- Respect explicit creator preferences and project intent over generalized best-practice defaults.
- Avoid automatically correcting unusual choices merely because they depart from convention.
- Recognize that imperfection can carry meaning, memory, intimacy, cultural texture, spontaneity, or identity.
- Make clear when a suggestion is a source-grounded principle versus a generator-created creative option.
- Allow the creator to reject, combine, invert, exaggerate, or deliberately break learned principles.
- Treat the creator's final decision as authoritative.

### Anti-Behavior

Workshop should not:

- Present one aesthetic as objectively best when several choices are viable.
- Treat popularity, conventional polish, cinematic appearance, technical cleanliness, or engagement optimization as automatic proxies for quality.
- Flatten culturally specific or personally meaningful choices into generic visual trends.
- Infer that an irregularity is an error without considering whether it may be intentional.
- silently replace the creator's stated preferences with source conventions.
- Use examples from admired work as templates that the creator is expected to imitate.
- Claim to know the creator's style when the system does not have enough evidence.

### Key Product Question

**What here should not be improved away?**

Workshop should consider this alongside "What could be improved?" whenever a creative decision involves correction, refinement, optimization, or normalization.

### Acceptance Criteria

#### AC1 — Convention is not prescription

**Given** the retrieved source knowledge describes a commonly used creative technique,

**When** Workshop applies that knowledge to a creator's project,

**Then** it must explain the technique as one possible approach unless the creator explicitly asks for the conventional or technically standard solution.

#### AC2 — Creator intent remains authoritative

**Given** the creator states an intended feeling, preference, or element they want preserved,

**When** source guidance points toward a different conventional treatment,

**Then** Workshop must preserve the stated creator intent and explain the trade-off rather than silently overriding it.

#### AC3 — Multiple viable directions remain visible

**Given** more than one creative direction could plausibly satisfy the project goal,

**When** Workshop provides guidance,

**Then** it should surface materially different options and explain what each option changes rather than collapsing them into a single optimized recommendation.

#### AC4 — Imperfection is not automatically treated as defect

**Given** the work contains an irregular, rough, imperfect, or non-standard element,

**When** Workshop evaluates possible changes,

**Then** it must consider whether that element contributes meaning, identity, intimacy, memory, cultural texture, or intentional style before recommending its removal or correction.

#### AC5 — Source knowledge and generated choices remain distinct

**Given** Workshop derives a creative suggestion that is not directly stated in the supplied knowledge,

**When** the suggestion is presented,

**Then** it must be framed as an option, adaptation, or design choice rather than as a source-backed rule.

#### AC6 — Same knowledge does not imply same aesthetic

**Given** two creators use the same underlying source knowledge for comparable creative tasks,

**When** their goals, preferences, context, or existing work differ,

**Then** Workshop should be capable of producing different creative directions rather than converging both creators toward the same aesthetic treatment.

#### AC7 — The creator can deliberately break the rule

**Given** Workshop explains a principle or convention,

**When** the creator chooses to violate, invert, or exaggerate that principle intentionally,

**Then** Workshop should help them understand the likely effect and work with that decision rather than repeatedly steering them back toward conformity.

### Edge Cases

- If the creator asks for a technically standardized result, Workshop may recommend the relevant standard while still identifying where the recommendation comes from.
- If a choice creates a genuine technical, accessibility, legal, safety, or platform constraint, Workshop should surface that constraint clearly rather than treating every preference as equally feasible.
- If the creator provides no style preferences or project intent, Workshop should ask through the product flow or present exploratory options instead of fabricating a personal aesthetic.
- If source knowledge conflicts, Workshop should preserve the tension and explain the different assumptions or contexts rather than synthesizing a false universal rule.

### Non-Goals

This story does not require Workshop to:

- imitate a named creator's exact style;
- decide whether art is objectively good;
- automatically edit photo or video files;
- infer private personal history or cultural identity that the creator has not provided;
- avoid all recommendations — it should still make recommendations when useful, but frame them in relation to creator intent, evidence, and alternatives.

### Success Signal

Workshop succeeds when the creator leaves with more options, clearer reasoning, and stronger intentionality — not merely a more conventionally "correct" edit.

Two creators using the same source knowledge should not be pushed toward the same aesthetic outcome unless their own choices lead them there.

---

## Learn Without Reading Every Book

As a user,

I want to benefit from books on a topic without reading every book cover to cover,

So that I can apply knowledge faster.

Example:

Learn copywriting from multiple books without reading all of them.

---

## Improve Product Messaging

As a founder,

I want to use knowledge from communication, persuasion, strategy, and marketing books,

So that I can explain my product clearly.

Example:

Ovara.

---

## Solve Problems Using Existing Knowledge

As a user,

I want to start with a problem,

Not a book,

So that I receive actionable recommendations rather than summaries.

Example:

How do I communicate this idea better?
