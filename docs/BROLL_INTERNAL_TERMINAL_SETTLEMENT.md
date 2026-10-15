# Terminal internal B-roll intent settlement

This backend increment lets an authenticated editor explicitly release a held
intent for a known terminal internal resolution. It appends one settlement
receipt. It does not adopt output, undo prior work, cancel a job, change the
item selection, refund cost or modify the original operation, job, worker
claim, asset, output evidence or timeline.

The allowed persisted job states are `failed`, `cancelled` and `succeeded`.
Queued, running, unknown, missing and receipt-null requests remain held. This
increment does not infer whether an absent request executed. A successful
historical job remains successful even when the user releases its client
intent without adopting its output through settlement.

## Explicit API

The prefix is
`/api/v1/projects/{project}/media-plans/{plan}/items/{item}/internal-resolution-settlement`.

- `POST /inspect` accepts the exact held `intent_json` and its literal UTF-8
  `intent_sha256`. It performs no SQL mutation, queue operation, object read
  or provider call. A request body avoids putting the large intent in a URL.
- `POST /settle` adds `observation_sha256` and strict `acknowledged=true`.
  It appends a settlement only if the inspected terminal job and its proof
  still match. Explicit replay returns the same immutable receipt.
- `GET /settlements/{settlement_id}` reads only that exact scoped receipt.
  It needs no signing key or provider and never repairs or redispatches work.

The intent uses the existing `sql-broll-internal-pending.v1` envelope, including
the full non-null original admission receipt. Unknown fields, duplicate keys,
nonfinite values, invalid IDs and malformed bodies fail closed. The literal
intent hash preserves whitespace. A settled request cannot be relabeled with
a changed literal intent or request body.

## Authority and original proof

An existing authenticated admission in
`human:broll-internal-resolution.v1` supplies the original server proof. The
command verifies its immutable response, original receipt, private authority,
full original request digest, context and exact marked internal job. It does
not borrow a latest job or accept an unmarked, paid or external job.

Current authentication must be live and match the original actor, display
name, platform role and exact workspace roles. Token and expiry renewal are
allowed. An expired or removed original credential never authenticates a new
request. Current authority and switches are checked after SQL awaits and
immediately before insertion. A successful terminal job also needs its valid
private completion claim; failed or cancelled jobs may predate a claim.

The held record's raw-token and UI-core hashes are local binding metadata.
They do not authenticate anyone. The server never pretends that a raw-token
hash can be reconstructed from a Bearer-header hash. No witness-signing
scheme or new secret is introduced.

## Preservation and concurrency

The command preserves the exact original saved context while allowing the
current source, transcript, provider, rights, project metadata or timeline to
change. Settlement does not approve or adopt a stale output. It reads the
project's current workspace for authorization, but does not require the old
source to remain the current edit source.

The new schema0 namespace is
`human:broll-internal-terminal-settlement.v1`. Its key binds the workspace,
project, actor, original admission, original authority and original request
key. Mutable source context and renewed credentials do not change that key.
The compare-and-set observation binds the complete terminal job/cost
snapshot, original admission and private claim proof, exact held intent and
current inspecting authority. Changed evidence requires fresh inspection.

SQLite uses explicit transactions and `BEGIN IMMEDIATE` for settlement.
Production row locking starts with the project before fresh job/proof reads.
Admission replay and worker paths consult only this verified new namespace.
They cannot hand off, claim, complete, fail-overwrite or resurrect a sealed
request. An existing exact observation keeps the original receipt and job,
sets `can_adopt=false`, `output=null`, `needs_attention=true` and reports
`BROLL_INTERNAL_REQUEST_SETTLED`. Failed and cancelled observations retain
their corresponding states; a settled successful observation becomes
`unknown`. No existing observation fields are added or removed.

## Acceptance limits

Tests use owned SQLite, authenticated in-process ASGI, ephemeral fixture
credentials and synthetic source/media metadata. Internal worker byte checks
use owned local fixture objects. These tests establish no real provider,
PostgreSQL, browser, production deployment or Owner UAT acceptance.

The current Studio controller and UI remain independent of these new routes.
Client integration requires a separately reviewed ownership guard and exact
settlement proof before removing a held record. Local clearing of unknown or
foreign intents remains prohibited.
