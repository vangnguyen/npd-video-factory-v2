# Native durable generation admission and claims

`NativeGenerationQueue` owns additive Native SQLite jobs, workspace binding,
events and reconciliation receipts. It freezes the strict request, project
revision/document, actual source-reference snapshot and selected protected
workflow/provider fingerprints. Request-key replay returns the original job;
a changed request conflicts. Concurrent identical admissions create one job.
Inactive/default configuration records `not_configured`; it does not execute,
inherit fixture acknowledgment or silently activate old requests. Histories are
bounded to 200 jobs per project and 5,000 per owned store.

This module does not start a worker or expose HTTP/UI routes. Result ingestion,
success receipts, explicit asset attachment and Assets controls are not yet
connected. A queued request is not a successful generation. Generated-media,
Mode A/B and implementation readiness remain incomplete.

The independent worker foundation permits one active claim in its workspace,
with a 900-second lease and private fence. Expired claims become
`recovery_required`; they are not automatically reclaimed or resubmitted. Old
claim holders cannot bind inputs or observations. Reopening without an enabled
factory preserves history and grants no claim. Configuration fingerprints must
still match before claiming. Native source editing/render jobs retain their
existing separate state and process behavior.

Only confirmed scoped bridge admissions supply reference URIs. Typed scalar
inputs, ordering and mask binding are checked against that actual source
snapshot before binding and again immediately before a dispatch intent.
Project/rights/configuration drift or a rehashed foreign URI fails. The dispatch
intent requires a unique Native cost operation bound to this generation ID,
provider, workflow model, request fingerprint, external-operation marker and
official/fixture accounting mode. One cost intent cannot authorize two
identical jobs. The FULL transaction precedes any future provider POST;
attempting to mark a second submission fails.

Trusted provider observations are typed, content-free and workspace/workflow/
version/ticket-bound. Identical observations are deduplicated. No client DTO
accepts an observation, provider body, secret, URI or graph. Cancellation of an
unstarted queued request can finish locally. Running cancellation remains
pending; it does not claim remote confirmation. An observed bound terminal
cancellation can finish that claim. A dispatched interruption retains uncertainty.
Budget rejection before dispatch retains `needs_approval` without call authority.

An explicit acknowledged reconciliation request binds the original request and
retains its frozen input/ticket. Its next claim's mode is `reconcile`, never
`create`; another generation dispatch is prohibited. A frozen idempotent
recovery receipt says `generation_submission_authorized=false`, limits recovery
attempts to three and causes no external call. Missing pre-dispatch work cannot
use that action as permission to start generation. The next worker must use
the neutral adapter's [read-only reconciliation](COMFYUI_JOB_RECONCILIATION.md).

Fourteen new queue cases exercise real isolated SQLite, concurrent admission/
claims, expiry/fencing, default-off reopen, scope/hash tampering, current-project
checks, actual owned image/reference binding with an explicit intake wire mock,
cost binding/reuse rejection, observations, cancellation and read-only recovery.
The affected Native queue/registry/reference/cost suite passes 49 tests. These
tests contain explicit mock observations and cost intents; no GPU generation or
billed outcome is inferred from them.

`scripts/north_star_native_generation_queue.py` creates three fresh-root jobs:
one inactive, one mock observed cancellation and one interrupted/reconciliation
case. It records two cost intents with unknown actual billing, zero paid
operations, zero external requests and zero generated result assets. The Native
project, approval and canonical timeline stay unchanged. Four exports under
external recovery `native-generation-queue-n2` include a separate-process exact
replay of projects, versions, jobs, events, costs and reconciliation receipts;
default execution stays disabled. No actual provider, paid call, legal clearance,
Owner UAT, publishing or production deployment is claimed.
