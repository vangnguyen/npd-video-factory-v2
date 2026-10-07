# Read-only generation job recovery

The bridge exposes authenticated
`GET /v1/jobs/by-client-request/{client_request_id}`. It resolves only the exact
workspace-scoped key, returns a copy of the existing job and SHA256 of the
complete normalized frozen bridge request. Missing and foreign-workspace keys
return 404; authentication and bounded ASCII keys are required. No request
inputs, prompt, graph or secret are returned. Lookup does not dispatch, retry,
change a job or append events. Saved terminal jobs remain readable after the
bridge restarts with its execution backend disabled.

The neutral ComfyUI adapter's `reconcile(payload, provider_job_id=None)` computes
the same original scoped request key from workspace, project, Native job,
typed input and workflow. It reads that lookup and verifies the full request
fingerprint, client key and optional saved provider ticket before normal
workspace/workflow/project binding, lifecycle observation and binary retrieval.
Responses are bounded to 64 KiB and the configured timeout; duplicate JSON keys,
extra wrapper fields, wrong MIME/fingerprints/tickets and redirects reject.
Existing submit request bodies and fingerprints are preserved.

Reconciliation never calls the generation POST or bridge retry endpoint. It
cannot turn a missing or failed job into a new generation attempt. The caller
must retain its frozen scope/parameters; a saved ticket alone does not authorize
a different request. A trusted pending cancellation hook can cancel only the
verified existing job. Cancellation remains distinct from confirmation of
remote completion. Completed results still require exact authenticated
job/workflow/input-bound artifact metadata and actual bytes; rights remain
unknown, production eligibility false and GPU/billed costs null.

Fourteen new API wire cases and two bridge cases cover lost submission, request
and scope drift, optional ticket matching, absence/redirect/size/duplicate/MIME
rejection, targeted cancellation, workspace isolation, immutable copies and
restart with execution disabled. The affected bridge/API suite passes 173
tests; the final focused set passes 17, including the additional persistent
restart case (counts overlap). Native compatibility passes 22. The existing
actual-media ASGI check also recovers the same decoded artifact by lookup and
verifies authentication/foreign-workspace guards without another GPU write.

The source-reference rehearsal now supports `--reconcile`. Fresh owned Native
and bridge state, actual local source JPEGs, authenticated intake, actual
FFmpeg decoding and explicit mock GPU wires create two PNG/MP4 outputs. A lost
submission reply with no saved ticket recovers through lookup, and the second
known-ticket lookup returns the identical bytes. Exactly two bridge submission
writes and two GPU prompt writes remain. Seventeen exports and a separate
process's exact offline replay are retained under external recovery
`native-generation-references-n5`.

These are local-real bytes and explicit mocks, not real model/GPU/provider,
legal, cost, Owner UAT or deployment acceptance. No job result is manually
injected. The Native project, approval and canonical timeline are untouched.
Native durable jobs, independent worker, costs, result attachment and Assets
controls still require integration; this read path supplies their recovery
prerequisite without new generation authority.
