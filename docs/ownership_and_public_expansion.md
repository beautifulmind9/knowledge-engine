# Ownership, Licensing, and Public Expansion

## Creator and ownership

Knowledge Engine was created by **Taneen Lewis**.

Copyright © 2026 Taneen Lewis. All rights reserved except where a specific component is expressly licensed otherwise.

Knowledge Engine is currently a proprietary product. Repository or documentation visibility is not an invitation to copy, commercialize, rebrand, host, distribute, or create derivative products from the proprietary core.

## Open collaboration around a proprietary core

Knowledge Engine is intended to grow through an open-collaboration community without making the entire core product public.

Anyone may participate through the contribution paths that Knowledge Engine opens, including product ideas, research, testing, UX and design proposals, documentation, evaluations, schemas, prompts, public tooling, integrations, and extensions.

The private core remains creator-controlled. Contributors do not need full core-source access to participate. Public APIs, schemas, SDKs, examples, test harnesses, and other deliberate extension surfaces can provide room for experimentation while protecting the product's competitive and security-sensitive internals.

Official contribution and governance rules are documented in:

- [Contributing to Knowledge Engine](../../CONTRIBUTING.md)
- [Contribution Governance](contribution_governance.md)
- [RFC Process](rfc_process.md)
- [Extension Policy](extension_policy.md)
- [Contributor Rights and Commercialization](contributor_rights_and_commercialization.md)

## Stewardship

Knowledge Engine remains founder-stewarded.

**Founder and Product Steward: Taneen Lewis**

Community discussion and voting may inform major decisions through formal proposals and RFCs. Final product authority remains with the Product Steward or with a future stewardship team operating under written rules established by Knowledge Engine.

Over time, reviewers, Core Maintainers, Domain Maintainers, and a broader stewardship team may receive delegated authority for routine decisions. Delegation does not automatically transfer ownership, licensing authority, brand control, or commercialization authority.

## Public product does not require public source code

A future public Knowledge Engine can be offered as a hosted product while the core source remains proprietary.

A multi-user version would require clear tenant boundaries such as:

```text
Account / Organization
↓
Libraries
↓
Sources
↓
Knowledge Assets
↓
Workshop outputs
```

Every stored object and retrieval path must be scoped to the correct account or organization. Public expansion therefore requires authentication, authorization, tenant-aware storage, private object storage, server-side secret handling, deletion/export controls, auditability, rate limits, and per-user AI usage accounting.

## AI and API economics

The current Gemini configuration is a beta implementation detail, not the definition of the product.

A public version may support one or more of these models:

- product-funded AI usage included in a subscription or allowance;
- bring-your-own-provider credentials;
- limited free usage with stricter quotas;
- paid plans with larger allowances;
- manual or non-AI workflows where useful; and
- a provider abstraction so Knowledge Engine is not permanently tied to one AI vendor.

The product's defensible core is the knowledge architecture, provenance, structured extraction, retrieval, synthesis, application workflows, and user experience — not a single model provider.

## Extension model

Community members may build against public extension surfaces without seeing the full proprietary core.

A submitted extension may be:

- declined;
- partially accepted;
- accepted as a Community or Experimental extension;
- designated KE Approved;
- adopted as an Official extension; or
- integrated in whole or part into the proprietary product.

Knowledge Engine decides what becomes official and may later modify, deprecate, remove, or revoke official status from accepted work.

Public extension tooling may be forked under the license that accompanies that tooling. The private core may not be forked merely because extension interfaces exist.

## Commercialization

Commercialization of the official Knowledge Engine product and official extension ecosystem is controlled by Knowledge Engine.

Acceptance of a contribution does not automatically create a right to payment, royalties, revenue share, employment, partnership, or independent commercial exploitation. Any such arrangement must be separately agreed in writing.

The intended contributor-rights model preserves visible contributor credit while giving Knowledge Engine sufficient rights to maintain, adapt, distribute, relicense, and commercialize accepted work. The final legal form of those rights must be established in the operative contributor agreement before external copyrightable work is accepted into the proprietary core or official extension ecosystem.

## Possible future openness

Opening parts of Knowledge Engine later should remain a deliberate creator or stewardship decision, component by component.

Potentially open or extensible areas may include:

- public schemas;
- an SDK or API client;
- plugin and integration interfaces;
- example integrations;
- public-safe utilities;
- developer documentation; and
- test harnesses or compatibility fixtures.

Potentially proprietary areas may include:

- hosted account infrastructure;
- retrieval and ranking logic;
- extraction and consolidation refinements;
- production orchestration;
- premium output systems;
- usage controls; and
- other parts identified as the competitive or security-sensitive core.

No future openness is implied by visibility of the repository or by publication of extension tooling.

## Attribution and transparency

Product-facing materials should identify the origin of the project consistently, using wording such as:

**Knowledge Engine — created by Taneen Lewis**

That creator attribution should coexist with transparent recognition of meaningful community contributions through Git history, release notes, RFC records, extension listings, contributor records, or feature acknowledgements.

Contributors may accurately describe public contributions while respecting boundaries around private source code, confidential architecture, unreleased features, security-sensitive information, and private user data.

## Contributor governance

Anyone may submit proposals through the open contribution paths.

Material changes should use formal proposals or RFCs, public discussion where appropriate, an advisory community vote, and a final steward decision. Knowledge Engine may accept all, part, or none of a proposal.

Before any external copyrightable contribution is integrated into the proprietary core or adopted as an Official extension, the applicable contributor agreement must be in place.

## Future legal and brand work

Before the first external copyrightable contribution is formally accepted, and again before a broad public or commercial launch, obtain qualified legal review of:

- the proprietary license and terms of service;
- the contributor agreement and intended commercial-rights model;
- extension and developer terms;
- privacy and data-processing obligations;
- trademark strategy for the Knowledge Engine name and identity;
- commercial provider terms; and
- user-facing AI disclosures.

This document records the intended product and governance direction; it is not a substitute for jurisdiction-specific legal advice.
