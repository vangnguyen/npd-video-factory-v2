# Reviewed ComfyUI HTTP backend

Wave 5E now has a runtime-selectable HTTP backend. It reuses the existing
transport, approved graph compiler, bridge-owned job store and decoded binary
store. Default execution remains disabled. The checked-in graphs are still
non-executable placeholders and report NOT_CONFIGURED, even when endpoint
configuration is present. This increment does not certify real GPU generation.

Operator configuration selects `COMFYUI_BACKEND=http`, separately enables
`COMFYUI_EXECUTION_ENABLED`, and supplies `COMFYUI_API_ORIGIN`, the installation
contract pin `COMFYUI_SERVER_SOURCE_SHA256`, optional `COMFYUI_API_TOKEN`, and
explicit HTTP host allowlisting. The bridge service Bearer token is separate
from the upstream GPU credential. Startup selection does not make a network
request. An invalid origin/profile/configuration fails with a fixed error.
The optional GPU Compose profile carries these settings; the CPU stack remains
independent. Docker execution is unverified on this host.

HTTP readiness requires transport enablement, configured FFmpeg/FFprobe and
at least one structurally valid reviewed graph. Each submitted workflow is
admitted separately. File hashes, allowed node classes, output nodes and scalar
bindings are checked before execution. Explicit fixture graphs are permitted
only with injected MockTransport/ASGITransport. Production runtime selection
never injects those transports. A local `owner_approved` declaration and source
pin are configuration evidence; actual Owner admission, licensed model weights,
custom node safety and verification of the installed remote source remain
requirements for real-provider acceptance.

The bridge passes its own workspace/job/retry identity to the backend. A private
SQLite journal records that scope, remote UUID, input/compiled graph/configuration
hashes and dispatch state. A FULL synchronous commit precedes `/prompt`.
Prompt bodies and credentials are excluded from this dispatch journal and
public lifecycle audit. The original private request remains in the protected
bridge-owned database. Bridge lifecycle percentages do not represent GPU
sampling progress. Unavailable GPU cost stays null.

A lost reply, interrupted POST, timeout, absent remote job, changed origin or
corrupt journal requires review and reconciliation. Startup never replays an
external write. An explicit retry reads the saved prompt identity; it cannot
POST again while the prior dispatch is unresolved. Only definitive submission
rejection or confirmed remote failure/cancellation permits a new UUID on a
later explicit attempt. The prior attempt remains auditable. A completed job
with an incomplete local download/registration retries that local result path.
The remote UUID is an identity, not an upstream deduplication guarantee.

Cancellation exposes `cancellation_requested=true` while the job remains
queued/running. Before a fresh dispatch, the backend can confirm local
cancellation without a GPU write. After a saved write intent, it sends at most
one targeted cancellation request and reads the exact remote job. An ACK or
lost cancellation reply does not itself establish cancellation. A successful
completion race retains its actual result. Timeout or shutdown leaves remote
recovery required. No global interrupt or shared queue clearing is used.

Successful remote history must bind the exact prompt UUID and compiled graph,
report completed success, and provide exactly one supported artifact from an
allowlisted output node. Ambiguous batches, foreign graphs/history/jobs,
unsafe descriptors and unsupported media fail closed. PNG/JPEG/MP4 downloads
are bounded and pass MIME/magic checks, FFprobe and full FFmpeg decoding before
immutable scoped registration. Windows uses extended paths for the bridge's
hashed storage; this fixes registration of deeper artifact directories. Output
hashes, dimensions, frames, timing and declared workflow model provenance persist.
The model identifier comes from the reviewed manifest, not independent remote
model inspection. Rights remain unknown, production eligibility false, QC
uncertified and estimated/actual costs null.

Reference modes require a trusted workspace/project-bound resolver returning
verified upload tokens. [Physical reference staging](COMFYUI_REFERENCE_STAGING.md)
now includes authenticated bounded local byte intake, decoded scoped storage and
durable no-overwrite upload/readback reconciliation. Intake remains disabled by
default, leaving no default resolver. Native source admission and generation
queue/UI integration remain open. Arbitrary client URLs, graphs, credentials
and model weights do not authorize execution.

Evidence is indexed in `docs/north-star/comfyui-http-backend-evidence.json`.
The new tests exercise HTTP write reservation, lost replies, restart,
reconciliation, targeted cancellation, success races, timeouts, rejection,
scope/configuration drift, invalid outputs, actual decoding and the authenticated
neutral binary consumer. Synthetic PNG/JPEG/MP4 pixels are created locally with
FFmpeg; HTTP/GPU behavior is explicitly mocked. The fresh-root rehearsal creates
three artifacts through the backend without manually replacing any job result,
then verifies exact replay in a new offline process. These are implementation,
mock wire and local-real media tests, not AI output quality or GPU acceptance.

Official wire references used during implementation are
[ComfyUI server routes](https://github.com/Comfy-Org/ComfyUI/blob/master/server.py)
and [job/history normalization](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_execution/jobs.py).
Live acceptance must pin and verify the actual installed revision rather than
assume the current upstream branch matches its API.
