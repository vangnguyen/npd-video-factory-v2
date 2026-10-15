# Reviewed B-roll preparation

This increment exposes an explicit, source-bound way to prepare the existing
supporting B-roll resolver. It does not approve media, apply clips, download
stock, generate media, publish, or certify Mode B.

The normal default uses uploaded assets and the internal library. AI tiers
remain disabled, the AI budget is exactly zero, and stock requires a visible
opt-in plus a configured, enabled, unpaid official provider with the existing
wire quota guard. Rights are never inferred or overridden by this control.

## Backend registration and contract

Register `broll_plan_review_api.router` with the same human authentication and
authorization dependencies as the other `/api/v1` project routes. This change
does not register routes on the service/Agent Hub facade.

- `GET /api/v1/projects/{project_id}/broll-plan-review` reads a coherent source,
  selected transcript, canonical timeline/version, supporting asset metadata,
  runtime provider binding and human authority context. It performs no DML or
  provider operation. `context_json` contains its exact canonical JSON text;
  `context_sha256` hashes those UTF-8 bytes, avoiding Python/browser number
  representation differences.
- `POST` at the same path requires `request_key`, `context_sha256`, literal
  boolean `acknowledged=true`, `settings` and nullable `learning_snapshot_id`.
  Settings contain explicit booleans `allow_stock`, `allow_ai_image=false`,
  `allow_ai_video=false`, the string `max_ai_cost_vnd="0"`, and a unique ordered
  list of `user_asset`, `internal_library` and optionally `licensed_stock`.
  Including the stock tier requires `allow_stock=true` and vice versa.
- `GET .../requests/{request_key}` observes only the exact credential/authority
  namespace's durable request. Every route is project authorized; preparation
  requires editor or higher and the human write switch.

The existing `service_api_operations` table holds a separate
`human:broll-plan-review.v1` namespace. Receipt key digests include project and
credential/authority, so equal logical keys in two authorized project paths
remain independent. This is schema zero, with no service
authentication, migration or outbox event. A project writer lock and actual
SQLite `BEGIN IMMEDIATE` fence context validation and reservation. The receipt
commits before planning. Replays never dispatch again; partial/uncertain
outcomes stay `unknown`. A changed request under an existing key is rejected.
Only the reserving caller finishes the preparation receipt. An unknown result
requires inspection; this increment provides no automatic recovery/rebase.
Cached failed, cancelled, in-progress or incomplete empty plans cannot be
reported as prepared. They remain an unknown request outcome for inspection.

Preparation calls `MediaPlanningService.create(defer_stock_execution=True)`.
Existing callers retain their prior default behavior. Prepared official stock
schedules persist `review_required=true`: worker recovery, due enumeration and
direct unreviewed processing cannot claim them. Existing explicit human stock
retry, with the plan version/binding CAS, clears that flag in the same claim
transaction before a search. Disabled AI tiers perform zero cost-estimate
calls during reviewed preparation. The later stock search still has its own
provider quotas, source checks, audit history and cancellation controls.

Optional learning advice calls the existing scoped snapshot reader with the
project workspace and niche. It remains recommendation-only. The request and
receipt retain the selected snapshot; its feedback digest is checked against
the prepared plan and before completion.

## Studio integration

`initializeBrollPlanReview` from `broll-plan-review.mjs` accepts `api`,
`getState`, `getSessionToken`, `storage`, `onPrepared(plan,receipt)` and
`onStatus(text)`. `getState()` supplies workspace/project IDs, workspace slug,
the six public human session fields, canonical timeline, selected analysis,
assets, `busy`, `dirty`, and nullable `learning_snapshot_id`.

Construction performs no I/O. `reload()` reads the public session and context.
Present user/internal/stock choices with their order, availability and rights
limitations. Use `defaultBrollPlanSettings()` for defaults. Only the explicit
create action calls `prepare(settings,true)`. `onPrepared` may select the
returned plan and refresh the plan list; it must not apply it or start stock.

The controller freezes source, transcript, timeline, learning selection, public
authority and literal credential before POST. The session storage intent holds
credential/session hashes, not the bearer credential. A lost response retains
the exact request. `reconcile()` only reads its receipt; `resend(true)` is
available solely after a scoped 404 and unchanged context, and resends the
identical body/key. Unknown outcomes cannot start a fresh request. Context or
credential changes block adoption, reconciliation or resend.

## Evidence and remaining work

Tests use actual SQLite and authenticated ASGI with explicit synthetic source
metadata/contract transcripts. Official stock tests use HTTP MockTransport;
no genuine provider, model, paid media operation or media quality acceptance
is claimed. The frontend fixture preserves actual captured DTOs and is replayed
through a mock API in Node tests. Its captured clock is injected for expiry
checks. SQL, mocked wire and browser-controller evidence are distinct.

Common Studio shell wiring is performed separately. Existing direct B-roll
apply/resolve handlers and their polling are not hardened by this increment.
Approved generative planning, genuine stock-provider acceptance, nondeveloper
full Mode B usability, moving-footage E2E and Owner UAT remain separate work.
Nondeveloper recovery of a held intent after source/authority drift requires a
separate explicit server-backed abandonment/tombstone CAS with an audit trail;
discarding unsent form edits must never remove that held intent locally.
