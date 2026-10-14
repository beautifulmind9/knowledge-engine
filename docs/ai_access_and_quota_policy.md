# AI access and quota policy

Settled 2026-10-11. This is product/architecture policy, not authorization to implement multi-user access or quota changes. Slice 2B Step 2 has not begun.

## Provider ownership

Knowledge Engine owns and manages the AI integration:

```text
User → Knowledge Engine → server-side AI gateway → Gemini
```

Normal users do not need Google AI Studio accounts, Gemini keys, or provider configuration knowledge. Credentials remain server-side. Bring your own key (BYOK) is not part of the normal MVP/beta experience. Billing confirmation and provider configuration belong to the owner/admin.

## Immediate external acceptance

Support one trusted external tester at a time using KE's server credential and a **shared hosted allowance of 20 admitted AI attempts per Pacific accounting day**. There is no personal allowance claim. Preserve $0-only operation and no paid fallback. There are no automatic semantic retries, repair calls, model fallbacks or prompt mutation. A user-authorized operation may make one additional identical provider attempt for an explicitly transient HTTP 503; each provider attempt is separately allowance-gated and counted, and uncertain transport outcomes are never automatically retried. There is no automatic continuation.

This is a shared acceptance workspace, not a private individual account. The shared-password gate provides no individual identity, per-user authorization, ownership, data isolation, AI attribution, or quota attribution. Different browser sessions do not create separate private users. Gate participants can access shared materials/work, private backup export and shared controls, including usage resume. The owner can access tester material. Logout clears browser cookies; copied sessions require expiry or password/signing-secret rotation to revoke.

Before each invitation, the owner must independently verify:

- live hosted cap and configuration;
- billing remains disabled and operation remains $0-only;
- current tester/provider eligibility, including applicable region requirements;
- proposed shared material is appropriate under current provider terms;
- no private owner material is unintentionally exposed.

Provider limits and legal terms are externally governed and mutable. Verify them currently; this document does not freeze their values or substitute for that check.

## Current accounting implementation

The gateway uses one workspace usage counter, persisted with state: Postgres in hosted mode, SQLite locally. It records the accounting day, count, last-attempt timestamp and pause/reason, not individual users or action categories. It survives restart. Requests are serialized in the supported single-worker deployment; this is not a multi-user transactional quota ledger.

The accounting day follows `America/Los_Angeles`, including daylight-saving changes. The effective count resets when the day changes; the next admitted attempt persists the new day/count. A daily-cap pause ends with that reset. A persisted provider-quota pause requires explicit resume. Resume clears pause/reason, never the count, and cannot bypass the daily cap. A provider 429 currently can pause all AI even when caused by a temporary minute limit.

`GEMINI_DAILY_CALL_LIMIT` currently replaces the gateway default of 450; hosted acceptance uses 20. **450 is currently a configurable default, not a hard ceiling.** The future ceiling below is a requirement to implement later, not a claim about current enforcement. External calls using the same provider project are not measured by KE.

## Attempt inventory

An admitted attempt is counted before provider dispatch. Dispatch failures, timeouts and malformed returned output remain counted once. Pre-dispatch local validation/configuration/quota rejection consumes zero. An explicit retry is a new action and a new admitted attempt.

| Action | Provider attempts under accepted UI | Usage counted |
| --- | --- | --- |
| Home routing | 0 | No |
| Find ideas | 0 | No |
| Browsing, filtering, pagination, evidence inspection | 0 | No |
| Upload, deterministic read, chunking | 0 | No |
| Selecting prompt suggestions | 0 | No |
| Local interaction/understanding edits | 0 | No |
| Deterministic knowledge preparation/retrieval | 0 | No |
| Manual revision/import | 0 | No |
| Export | 0 | No |
| Recovery reset | 0 | No; does not build knowledge |
| Usage resume | 0 | No |
| Build one knowledge part | 1 if admitted | Yes |
| Ask with AI | 1 if admitted | Yes |
| Create | 1 if admitted | Yes |
| AI revision | 1 if admitted | Yes |
| Explicit retry of an AI action | 1 new attempt if admitted | Yes |

### Known interpret API contract gap

The accepted UI requests one part per Build knowledge action. However, `POST /sources/{source_id}/interpret` accepts `max_chunks` from 1 to 10. Values greater than one can dispatch several sequential provider attempts from one API request, stopping on failure. Each part still has its own isolated provider request and accounting increment.

Therefore **one provider attempt per explicit action is currently an accepted UI contract, not a universal API invariant**. Track closure of this gap as hardening before broader external/multi-user beta. This documentation checkpoint does not change the route.

## Future individually identifiable beta

Before genuine multi-user beta, establish:

- invite-only individual accounts and server-verified identity;
- server-derived private workspace ownership;
- authorization on every library/source/output read/write, retrieval, evidence, snapshot, export, deletion and artifact operation;
- private artifact namespaces and owner-bound prepared-evidence snapshots;
- revocable sessions and separate admin authorization;
- a transactional AI-attempt ledger and atomic per-user/global/minute reservations.

The present globally cached workspace collections and signed shared-gate cookie do not satisfy these requirements. Team sharing remains deferred.

### Quota hierarchy

Initial policy for the first identifiable invited cohort, subject to later usage evidence:

| Layer | Policy |
| --- | --- |
| Provider project ceiling | Externally governed and authoritative; currently verify in provider controls |
| KE hard global daily safety ceiling | 450 admitted provider attempts per Pacific day |
| Configured deployment cap | May lower the effective ceiling, never raise it above 450 |
| Initial personal allowance | 25 admitted AI attempts per user per Pacific day |
| Initial cohort | Up to 8 invited users |
| Global minute admission | 12 attempts per rolling 60 seconds |

All admin/test attempts also count toward the global ceiling. Provider quota, KE global safety quota and personal product allowance are different boundaries. KE can reach a provider limit before its own allowance is exhausted. The earlier 50/user/day proposal is not the initial policy; reconsider only after observing real usage.

These multi-user limits are **not implemented or authorized by this checkpoint**. Retain the current hosted 20-attempt cap. Prefer pre-dispatch temporary rejection with an explicit later user action over queues or automatic retries.

### Future input protection

Add local request-size/token estimation, bounded per-request input size, and a conservative rolling estimated input budget below the currently verified provider limit. Reject before dispatch when KE knows a request is too large. Do not create a user-facing token currency. Never silently trim Create's reviewed evidence snapshot. This hardening is outside Slice 2B.

## Future user experience

Prefer **AI attempts today: X of Y**, with explanation that a failed admitted attempt can count. Keep RPD/RPM/TPM, project quota and key management out of ordinary-user UI.

| Condition | User-facing behavior/copy |
| --- | --- |
| Personal allowance exhausted | You've used today's AI allowance. Available again at [appropriate local time]. |
| KE global daily ceiling exhausted | AI is unavailable for the rest of today. Your work is saved. |
| Temporary admission/rate limit | AI is busy. Try again in [time]. |
| Provider failure | AI couldn't complete this request. Your work is saved. |
| Administrative pause | AI is temporarily paused. You can keep working with your library. |

Preserve requests and completed work. Non-AI functionality remains usable whenever AI is unavailable. No paid fallback or request for a user's Gemini key is offered. Current shared acceptance must describe its allowance as shared, not personal.

## Future admin experience

Separate authorized admin diagnostics may show KE global attempts, per-user usage once identity exists, usage by action category, pause state/reason, reset timing, minute reservations, estimated input-budget reservations and safe provider error categories.

Clearly distinguish KE-measured usage from Google/project usage, which KE may not fully observe. Routine logs must never expose provider keys, cookies, raw source content, prompts or raw provider bodies.

## Implementation boundary

This checkpoint implements none of the future architecture: no Supabase Auth, ownership fields, RLS, personal quotas, AI ledger, queues, team sharing, TPM accounting or provider changes. It does not change the hosted cap. Material-first Slice 2B Step 2 can proceed after its own authorization without first implementing multi-user infrastructure. External invitation still requires the current acceptance checks above.
