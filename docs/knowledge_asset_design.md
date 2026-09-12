# Knowledge Asset Design

## Purpose

Knowledge Engine should not only summarize source material. It should turn useful ideas into small, reusable knowledge assets that can later be searched, connected, and assembled in the Workshop.

This design is based on what we learned from the original *Made to Stick* prototype.

## Core rule

A knowledge asset should help answer four practical questions:

1. What is this idea?
2. Why does it matter?
3. When or how should it be used?
4. Where did it come from?

## Asset types

The first supported asset types are:

- concept
- problem
- principle
- insight
- decision rule
- pattern
- example
- warning
- framework
- mental model
- process

The goal is to avoid storing one giant insight object containing everything. Instead, each useful thing becomes its own asset while staying linked to the source and chunk it came from.

For example, one source chunk could produce:

- Principle: Use intent instead of detailed plans.
- Decision rule: State the desired outcome rather than every step.
- Warning: Overly detailed plans become obsolete.
- Example: Military Commander's Intent.
- Process: Intent-Based Leadership.

## Information shared by all assets

Every asset should have:

- asset type
- title
- what it says
- why it matters, when useful
- source ID
- chunk ID
- chapter or section, when known
- evidence from the source, when useful
- how to apply it
- when to use it
- when not to use it
- trade-offs
- keywords
- confidence score

Not every optional field has to be filled in.

## Type-specific information

Some asset types need extra structure.

### Decision rule

- condition: when the rule applies
- action: what to do
- rationale: why that action makes sense

### Warning

- consequence: what can go wrong
- prevention: how to avoid it

### Example

- what happened
- transferable lesson
- concept demonstrated

### Process / framework / pattern

- steps
- adaptation notes

## What changed from the old prototype

The original prototype proved that fields such as `what_it_says`, `why_it_matters`, decision rules, warnings, examples, application guidance, trade-offs, and evidence are useful.

The new model simplifies the structure by making each reusable item its own asset instead of nesting many different knowledge objects inside a single insight.

The new model also avoids repeating source title and author on every asset. The `source_id` links back to that information. Likewise, `chunk_id` replaces the old chunk file path.

For now, confidence remains part of the model. Importance and novelty are left out because they are more subjective and can be revisited later.

## Cost rule for the development build

The development build should not require paid AI API usage.

The current automatic extraction path uses the Gemini API free tier. The provider remains replaceable so Knowledge Engine is not permanently tied to one model company. If the free tier changes or its quota is exhausted, the system should fail clearly rather than silently incur paid usage.

Free-tier model access can have lower rate limits and different data-use terms than paid plans, so that trade-off should remain visible when choosing what source material to process.

## Current pipeline

```text
Library
  -> Source
      -> Extracted Text
          -> Chunk
              -> Knowledge Extraction Job
                  -> Knowledge Assets
                      -> Workshop
                          -> Outputs
```

## Current build status

The Knowledge Asset schema and Knowledge Extraction Job backbone are implemented.

A knowledge extraction job can:

- point to one source chunk
- expose the chunk and the extraction instructions
- define the exact structured output expected from the model
- run automatically through the current free-tier model provider
- validate returned assets and their provenance
- assign asset IDs and timestamps
- store validated assets in the current prototype store
- retrieve assets by source, chunk, or asset type

The model provider is kept behind a service boundary so it can be changed later without redesigning Knowledge Assets or the Workshop.
