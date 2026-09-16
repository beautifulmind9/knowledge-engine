# Knowledge Engine Extension Policy

## Purpose

Knowledge Engine is designed to support experimentation and community perspectives without exposing the entire proprietary core.

Extensions should be built through public interfaces such as documented APIs, schemas, SDKs, examples, and test harnesses that Knowledge Engine deliberately makes available.

## Extension statuses

An extension may have one of the following statuses:

- **Community** — independently created using public extension surfaces; not reviewed or endorsed by Knowledge Engine.
- **Under Review** — submitted for possible official recognition or integration.
- **Experimental** — accepted for limited testing but not yet treated as stable or generally supported.
- **KE Approved** — reviewed and approved for compatibility, quality, security, or other published criteria, but not necessarily maintained by Knowledge Engine.
- **Official** — adopted, maintained, distributed, or formally endorsed as part of the Knowledge Engine ecosystem.

Only Knowledge Engine may assign the labels **KE Approved** or **Official**.

## Building extensions

Public extension tooling may be forked and adapted under the license accompanying that tooling.

The existence of an SDK, API, schema, example, or extension interface does not grant access to, or a license to copy, the private Knowledge Engine core.

Extensions should avoid assumptions about undocumented internal behavior. Compatibility is only promised for interfaces Knowledge Engine explicitly identifies as public and supported.

## Submission and review

Anyone may submit an extension for review.

Knowledge Engine may:

- decline it;
- request changes;
- accept selected parts only;
- approve it as a community or experimental extension;
- mark it KE Approved;
- adopt it as an Official extension; or
- integrate some or all of it into the proprietary core.

Submission does not guarantee acceptance or compensation.

## Publication after non-acceptance

If an extension was built entirely against public Knowledge Engine interfaces and does not contain private or proprietary Knowledge Engine material, a contributor may publish it as an **unofficial, non-commercial community extension** subject to the license terms of the public tooling used.

It must not:

- imply endorsement or official status;
- use Knowledge Engine trademarks, logos, or trade dress in a misleading way;
- disclose private source code or confidential information;
- bundle proprietary Knowledge Engine code;
- bypass access, usage, payment, security, or privacy controls; or
- be commercially sold, licensed, monetized, or offered as a paid Knowledge Engine extension without written authorization from Knowledge Engine.

A rejected or unreviewed extension must be described clearly as unofficial.

## Commercialization

Commercialization of the official Knowledge Engine product and official extension ecosystem is controlled by Knowledge Engine.

A contributor or third party may not independently sell, license, monetize, bundle, or commercially distribute an extension as part of the Knowledge Engine ecosystem unless Knowledge Engine grants written authorization.

Any compensation, bounty, revenue share, royalty, contract, partnership, or other commercial arrangement must be documented separately in writing. Acceptance or approval alone does not create a payment obligation.

## Branding

Community extensions may accurately state compatibility in plain text, for example:

> Unofficial community extension compatible with Knowledge Engine.

They may not describe themselves as "official," "approved," "certified," "partner," or equivalent unless Knowledge Engine has granted that designation.

Brand rules may become more detailed if Knowledge Engine registers trademarks or launches a formal extension directory.

## Security and privacy

Extensions must not:

- collect more user data than needed for their documented function;
- transmit private source material without clear user authorization;
- expose credentials, API keys, or secrets;
- weaken tenant, account, or library boundaries;
- bypass provider or Knowledge Engine usage controls; or
- conceal meaningful external data transmission.

An extension may be denied or lose official status because of security, privacy, provenance, reliability, compatibility, maintenance, or trust concerns.

## Directory and review criteria

A future Knowledge Engine Extensions directory may list Community, Experimental, KE Approved, and Official extensions separately.

Review criteria may include:

- clear purpose and documentation;
- compatibility with supported interfaces;
- secure secret handling;
- privacy transparency;
- provenance and licensing clarity;
- test coverage;
- accessibility and usability;
- maintainability;
- responsible AI behavior where applicable; and
- absence of misleading branding.

Listing in a directory does not create permanence. Knowledge Engine may change status or remove a listing when the extension no longer meets the applicable criteria.

## Integration into Knowledge Engine

If Knowledge Engine wants to adopt all or part of an extension into the official product, the accepted copyrightable material must be covered by the applicable contributor agreement before integration.

Partial acceptance applies only to the portions Knowledge Engine actually agrees to adopt.
