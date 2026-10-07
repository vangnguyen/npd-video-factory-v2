# Scoped physical references for ComfyUI

Wave 5E now includes a bridge-owned reference store, authenticated byte intake,
and a trusted staging resolver. Native project lookup, physical asset/rights
admission, asynchronous generation jobs and Studio controls remain open. This
does not claim real-provider, legal, GPU or Owner acceptance.

Reference intake is disabled by default with
`COMFYUI_REFERENCE_INTAKE_ENABLED=false`. Its own volume directory is selected
by `COMFYUI_REFERENCE_ROOT`. Enabling intake permits local reference storage;
the separate GPU execution flag and reviewed workflow admission still control
external execution. CPU operation does not depend on this optional service.

`POST /v1/references` requires the bridge service Bearer token and workspace
header. The body contains PNG/JPEG bytes, bounded to 32 MiB with a 30-second
stream timeout. The fixed-size `X-VF-Reference-Admission` JSON header binds
workspace, project, asset ID, exact SHA256/MIME, source rights status, admission
kind, rights receipt SHA, issue/expiry times and a strict fixture flag. Duplicate
JSON keys, extra fields, graph/secrets/paths, scope/MIME mismatch, declared length
mismatch and oversized streams reject before storage. Intakes use magic checks,
FFprobe and full FFmpeg decode. Extensions do not establish validity.

Admission is an assertion by the authenticated production service. The bridge
does not share or query the Native/PostgreSQL database, prove that a source
project exists, independently verify licensing, or independently validate an
Owner decision from its hash. The authorizing service must check its actual
project, registered physical asset, current hash and saved rights decision
before issuing an admission. Native issuance is not wired yet. Browser clients
receive no service credential and cannot author these assertions through the
Native UI. A supplied rights receipt is a binding/audit reference, not evidence
of independent verification. No actual uncertain-rights asset was cleared in
this increment.

Restricted sources reject. Registered-rights admissions require owned/licensed/
verified source status. Unknown sources require an explicit Owner-override
admission from the trusted service; such an assertion cannot be marked fixture.
The authorizing service must have a genuine saved scoped Owner exception.
Validity is at most one hour, with bounded issue-clock skew. Expired admissions
cannot stage or upload. The store always retains
`rights_independently_verified=false` and `publishing_authorized=false`.
Reference permission does not change the original asset's license/status or
grant generated-output publication permission.

The reference URI is `vf-reference://<64-hex-admission-hash>`. Source bytes and
metadata are immutable, hash-checked and workspace/project scoped. Exact retry
returns the original receipt. The isolated store bounds registered references
to 512 and 2 GiB; cleanup/retention policy remains production-hardening work.
It reads no client URL or filesystem path. Source admission and image bytes
remain in this private bridge store; public GPU lifecycle records contain no
prompt bodies, credentials or image data.

The HTTP backend installs the resolver only when intake is explicitly enabled.
Reference workflows additionally require a trusted project identity. The neutral
adapter adds and verifies that project for registered-reference requests at
submission, polling and cancellation; legacy non-registered requests retain
their existing wire identity. The compiler requires matching workspace/project
tokens and binds only their verified uploaded filenames, including mask inputs.

Staging chooses a deterministic opaque filename bound to source reference,
workspace/project and configured target. It reads that input filename first.
A missing initial input causes a FULL-commit upload intent before one
`/upload/image` write with overwrite disabled. Exact server readback must match
source bytes and MIME. A lost reply is reconciled using that reserved filename;
an unresolved/absent prior upload or a missing previously confirmed input never
permits another upload. Changed bytes, corrupted journal or foreign scope
fail closed. A later explicit fresh admission may require separate review;
this resolver does not reset uncertainty or overwrite server files.

Prompt reservations also save the transport binding. Changed input or target
rejects before reference staging. Legacy text reservations without the new
field can reconcile through their existing full binding; unresolved legacy
reference intents without a target pin require review. Journal updates compare
validated prior state and its actual stored hash, preserving compatibility with
older absent optional fields. Unknown upload/generation costs stay null.

Fixtures cannot reach a live transport. Actual generated outputs stay unknown
rights, ineligible for production and uncertified by full QC. The retained
rehearsal uses local synthetic source/mask pixels and explicitly fake graph
nodes/model/approval references. Its GPU HTTP behavior is mocked; no real GPU,
paid provider, key, production state, publishing or legal acceptance is used.

Evidence: `docs/north-star/comfyui-reference-staging-evidence.json`. New checks
cover admission, bytes/decode, scope/expiry/corruption, default-off authenticated
streamed intake, upload intent/readback/restart/lost reply, source fixture/live
separation, target/input drift, project-bound neutral responses and legacy
dispatch compatibility. The fresh-root rehearsal exercises nine request variants
plus a lost-prompt replay: ten fully decoded mock outputs from two physically
staged images, with exactly two mock image upload writes. Lost upload/prompt
replies do not duplicate writes. A new offline process replays all ten outputs,
two image receipts and upload journals exactly.

Real model/workflow/source-pin verification, installed GPU behavior, license and
Owner decision acceptance remain external gates. Native request/worker/cost/
attachment/UI integration and production backup/retention/soak remain required.
