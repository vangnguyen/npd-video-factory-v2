# Native storyboard media resolution

Saved storyboard MediaPlan decisions now create explicitly requested jobs in the
existing stock and generation workers. The resolver owns an immutable journal,
not another worker, billing authority, provider result store or edit timeline.

## Binding and execution

`native_media_resolutions` binds workspace/project, exact plan/version/SHA/input,
shot, project revision/document, normalized request and existing child job/hash.
Job insertion, its event, the binding and its content-free event commit in the
same SQLite FULL transaction. A failed plan check or journal write rolls back the
child job. Concurrent identical requests commit one binding and one child. Exact
lost-response replay returns the original receipt with fresh local child status,
including after later project edits; changed request bodies conflict.

The optional admission callback is internal Python code only. Existing direct
stock and generation endpoints retain their behavior. Queue creation performs
no provider operation; a committed job may subsequently run in its existing
worker. Protected configuration, source acknowledgement, pre-dispatch cost
guards, approved manifests, local decoding and recovery remain those workers'
responsibility. The resolver accepts no client graph, origin, URI, billing price,
license claim or provider result.

| Endpoint | Permission | Behavior |
| --- | --- | --- |
| GET `/api/projects/{id}/media-resolutions[/{nmr}]` | read | Scoped local history/status |
| POST `/api/projects/{id}/media-plans/{nmp}/resolve/generate` | edit | Saved AI prompt/aspect/seed and exact supported duration |
| POST `/api/projects/{id}/media-plans/{nmp}/resolve/search` | manage | Saved query/media type/orientation; selected configured provider |
| POST `/api/projects/{id}/media-plans/{nmp}/resolve/download` | manage | Exact saved search/result/candidate SHA and unchanged parent plan |
| POST `/api/projects/{id}/media-resolutions/{nmr}/import` | edit | Acknowledged exact binding/result import via existing receipt |

Human session, CSRF and origin checks run before unauthorized request bodies.
Stock execution retains Owner/manage permission. Reviewers/viewers may read.
Source-footage projects retain their existing Source B-roll workflow.

The latest current-policy plan and physical inputs must still match at job
admission. Selected existing media are reused instead of creating another job.
Unpriced new AI is blocked under any finite budget. Video scenes above the
existing provider's 30-second limit are rejected without shortening the scene.
Subsequent cost/result observations may legitimately stale a plan; explicit
import therefore checks immutable child binding and current project CAS rather
than requiring the original plan to remain current.

## Studio and import

The Assets storyboard panel requests stock/AI per saved shot, displays scoped
history, offers the existing authenticated local media review endpoint, and
requires an import acknowledgement. Edited unsaved strategy/query/prompt cannot
be submitted. No provider request happens on initialization, panel read, refresh
or result display. Uncertain responses retain an explicit replay of the same
body/key; no automatic POST retry occurs. Foreign/late responses are discarded.

Import registers the media and clears project approval. It does not choose or
place the asset in a shot. The existing canonical timeline version can advance
with project synchronization while its snapshot, SHA and shot placement remain
unchanged. Rights stay as the existing stock/generation worker recorded them.
Create a fresh plan, review rights, select eligible media, and explicitly apply
through the existing canonical shot adapter before preview and approval.

History is limited to 200 resolutions per project/5,000 per store. Additive
workspace-bound tables are included in backup counts. Existing active child jobs
block backup; restored configuration defaults to disabled. No live migration,
main merge, external publication or production deployment is part of this work.

## Evidence and remaining work

See `docs/north-star/native-media-resolution-evidence.json` for exact source/log
and export hashes. Backend cases cover concurrent deduplication, rollback, CAS,
strict fields, stale parent plan, scope/hash tampering, default-off behavior,
unknown-price finite budgets, rights and over-limit duration. DOM cases cover
role/acknowledgement, saved input, literal text, late responses, same-key recovery
and import/replan guidance. DOM/HTTP evidence is not browser or Owner UAT.

The generation rehearsal connects actual Native human HTTP/worker and private
bridge graph compilation/registration to synthetic GPU wires. It produces three
decoded local outputs; the first is bound to a saved storyboard plan. Lost-submit
lookup and a separate post-stage interruption recover without duplicate submits.
Explicit import, rights-blocked replanning, actual backup/restore and separate
process replay pass. Results are not manually injected into Native state.

The stock rehearsal connects a technology channel's authored storyboard to the
actual independent stock worker through official adapter wire fixtures, selected
download, decoded pixels, review/import, rights-blocked replanning and exact
source/restored restart. Its three API/media requests are mocked; licensing and
actual cost remain unknown. No imported fixture becomes publishable.

Genuine provider/GPU/model/quality/legal/billing acceptance, semantic Vision,
researched and spoken full Mode A, full original Mode B, publishing, analytics,
winner/learning/Trend Radar, Agent Hub, hardening and final A/B/C/Owner acceptance
remain governed by the full capability matrix. IMPLEMENTATION_COMPLETE = NO;
REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.
