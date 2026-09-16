# Ownership, Licensing, and Public Expansion

## Creator and ownership

Knowledge Engine was created by **Taneen Lewis**.

Copyright © 2026 Taneen Lewis. All rights reserved except where a specific component is expressly licensed otherwise.

Knowledge Engine is currently a proprietary product. The repository is not an invitation to copy, commercialize, rebrand, host, distribute, or create derivative products from the proprietary core.

## Current beta position

The beta remains creator-controlled while the product, architecture, economics, and future community model are validated.

During this phase:

- the core product remains proprietary;
- unsolicited code and documentation contributions are not accepted;
- feedback, testing, feature ideas, and use cases may be collected;
- no contributor code is merged without explicit contributor terms;
- no component should be treated as open source unless its own file or directory expressly says so.

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
- manual or non-AI workflows where useful;
- a provider abstraction so Knowledge Engine is not permanently tied to one AI vendor.

The product's defensible core is the knowledge architecture, provenance, structured extraction, retrieval, synthesis, application workflows, and user experience — not a single model provider.

## Possible future openness

Opening parts of Knowledge Engine later should be a deliberate creator decision, component by component.

Potentially open or extensible areas may include:

- public schemas;
- an SDK or API client;
- plugin and integration interfaces;
- example integrations;
- public-safe utilities;
- developer documentation.

Potentially proprietary areas may include:

- hosted account infrastructure;
- retrieval and ranking logic;
- extraction and consolidation refinements;
- production orchestration;
- premium output systems;
- usage controls;
- other parts identified as the competitive core.

No future openness is implied by the visibility of the current repository.

## Attribution

Product-facing materials should identify the origin of the project consistently, using wording such as:

**Knowledge Engine — created by Taneen Lewis**

Attribution should remain visible even if the product later supports employees, contractors, community contributors, plugins, or third-party integrations.

## Contributor governance

Before accepting external copyrightable contributions, Knowledge Engine should adopt formal contributor terms that make ownership and licensing rights unambiguous.

Until then, outside participation should remain limited to feedback, testing, issue reports, and product discussion unless a contribution is explicitly invited and covered by written terms.

## Future legal and brand work

Before a broad public or commercial launch, obtain qualified legal review of:

- the proprietary license and terms of service;
- contributor terms;
- privacy and data-processing obligations;
- trademark strategy for the Knowledge Engine name and identity;
- commercial provider terms and user-facing AI disclosures.

This document records the intended product and governance direction; it is not a substitute for jurisdiction-specific legal advice.
