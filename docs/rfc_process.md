# Knowledge Engine RFC Process

## When to use an RFC

Use an RFC for changes that are material, cross-cutting, hard to reverse, likely to affect compatibility, or important to the community.

Examples include:

- new extension capabilities;
- significant knowledge-schema changes;
- major retrieval or synthesis behavior changes;
- new public APIs or breaking API changes;
- governance changes;
- new official integration categories;
- privacy, security, or data-handling changes;
- substantial UX or workflow redesigns; and
- proposals that affect commercialization, licensing, or official product boundaries.

Small bug fixes, typo corrections, narrow documentation changes, and routine maintenance generally do not need an RFC.

## RFC structure

An RFC should contain:

1. **Title**
2. **Author(s)**
3. **Status**
4. **Problem** — what is not working or what opportunity exists?
5. **Proposal** — what should change?
6. **Why it matters** — what user, product, research, or technical value does this create?
7. **Scope** — what is included and explicitly excluded?
8. **Compatibility** — what existing workflows, APIs, data, or extensions could be affected?
9. **Privacy and security** — what new risks or trust boundaries exist?
10. **Intellectual-property and provenance notes** — what third-party or AI-generated material is involved?
11. **Alternatives considered**
12. **Risks and tradeoffs**
13. **Testing or evaluation plan**
14. **Open questions**
15. **Community feedback summary**
16. **Advisory vote result**
17. **Steward decision**

## Status values

An RFC may move through these states:

- Draft
- Discussion
- Advisory Vote
- Accepted
- Accepted with Changes
- Partially Accepted
- Deferred
- Rejected
- Withdrawn
- Superseded
- Implemented

## Discussion period

The default public discussion period is **7 calendar days** once an RFC is ready for review.

The Product Steward may shorten or extend the period when urgency, complexity, security, low community participation, or the need for additional research makes a different period more sensible.

There is no fixed quorum requirement during beta. A lack of votes does not prevent a decision.

## Advisory voting

Community voting is advisory rather than binding.

The vote should be recorded publicly when practical using the repository's available discussion or issue mechanisms. Participants are encouraged to explain reasoning, not only register support or opposition.

The Product Steward or delegated maintainers may consider:

- strength of reasoning;
- evidence and testing;
- affected-user impact;
- security and privacy;
- compatibility;
- maintenance burden;
- strategic fit;
- implementation quality; and
- the advisory vote.

A majority vote does not compel acceptance, and a minority position is not automatically rejected if its reasoning or evidence is stronger.

## Steward decision

After discussion and the advisory vote, the Product Steward records one of the recognized outcomes and, for material decisions, a concise rationale.

The decision may accept the proposal exactly as written, require modifications, accept only selected parts, designate it as experimental, defer it, or reject it.

## Changes after acceptance

Implementation may reveal information that was not available during review.

If implementation materially departs from the accepted RFC, the change should return to review or be documented as an amendment. Minor implementation details do not require reopening the RFC.

## Security-sensitive RFCs

A proposal that would expose vulnerabilities, private architecture, credentials, private user data, or other security-sensitive information should not be discussed publicly in full.

The public record may use a limited summary while detailed review occurs through an authorized private process.

## RFC template

A copyable RFC template is available at [`docs/rfcs/0000-template.md`](rfcs/0000-template.md).
