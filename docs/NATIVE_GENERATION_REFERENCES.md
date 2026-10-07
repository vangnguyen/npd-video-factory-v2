# Native generation source admissions

`services/windows_native/generation_references.py` implements the Native source
binding prerequisite. The generation server routes, durable generation jobs,
independent worker, cost admission, cancellation/recovery, result attachment and
Assets controls still need integration. This module does not establish Mode A,
Mode B or generative-media readiness.

The server selects registered project assets by owned ID and exact SHA256. It
checks the editable revision and entire document digest, guards the actual
asset directory against links/junctions/hardlinks, bounds the read to 15 MiB,
checks PNG/JPEG magic, fully decodes the actual image and verifies registered
size and dimensions. Animated images and images outside the bridge's 8192-pixel
dimensions/16-Mpixel limit reject. No browser URL, path, graph, license, result,
endpoint or credential is accepted.

Unknown rights and copied assets marked `rights_review_required` require the
current enabled, unexpired, unretracted workspace/project/asset/bytes/rights
Owner exception. Registered owned/licensed/verified metadata otherwise supplies
the basis. An upload attestation alone cannot make an unknown source eligible.
Raw rights, license, production eligibility, approval and timeline are preserved.
A rights receipt digest binds the actual asset record and exact decision; it is
not independent licensing verification or permission to publish. Restricted
sources reject. Explicit fixture sources cannot reach official transport or
receive an Owner exception. Fixture transport requires explicit acknowledgment.

Frozen snapshots include typed parameters, selected references/mask, asset and
rights record fingerprints, provider configuration, project revision/document,
workspace and creation time. The protected factory checks credential/origin/
transport-mode and manifest/graph drift before network. Snapshot dates are
normalized before hashing. Workflow placeholders remain `NOT_CONFIGURED`.

The additive private SQLite admission journal freezes each service assertion,
including its deterministic bridge reference ID, before external work. Its
30-minute expiry cannot exceed the Owner exception's expiry. Repeated issuance
returns that assertion; it does not silently refresh an expired authority.
The client uses the protected bridge origin/token and workspace/project headers,
with redirects/environment proxies disabled. Responses are capped at 64 KiB
and 35 seconds and must match the full admission, ID, bytes, dimensions and
decoded-media markers. Secrets and response error bodies are not persisted.

An exact metadata read precedes upload. A FULL SQLite `dispatching` intent is
committed before the first POST. Lost replies are reconciled by the immutable
reference ID. A saved ambiguous intent followed by absence requires recovery;
it never uploads again automatically. Source bytes, project, rights and
configuration are checked again before dispatch and confirmation. The provider
input contains only the confirmed scoped URIs, preserving order and mask
binding. This staging prerequisite does not invoke a generation provider itself.

Fifteen new Native cases cover real owned pixels/SQLite and explicit mocked
service wires: unknown attestation rejection, source/decode/metadata/scope/link
checks, fixture isolation, current Owner exceptions, copied-asset review, expiry,
provider/project drift, journal tampering, bounded/foreign/redirect responses,
reference-dependent modes and lost-upload/new-service recovery. The affected
Native suite passes 40 tests; affected bridge/API suite passes 58 tests,
including the known-status scoped-exception contract. Broader accepted suites
retain their prior results; these changes do not certify untouched integrations.

The reproducible `scripts/north_star_native_generation_references.py` rehearsal
uses fresh owned state, two locally created images, actual Native JPEG intake,
actual authenticated ASGI bridge intake, actual FFmpeg decoding/storage and
two explicit mock-GPU outputs (PNG/MP4). Three Native admissions and three GPU
input uploads precede two prompt writes. A deliberately lost Native intake
reply is reconciled without repeating that POST. No job result is manually
injected. The Native project and canonical timeline stay unchanged. Sixteen
exports are retained under the external recovery directory's
`native-generation-references-n4`; a separate process verifies exact bytes,
projects/versions/admissions and bridge output/upload journals without external
requests. The recovery check ran within the admission TTL; expired assertions
must not be used to resume external work.

All nodes/models, rights metadata/decisions and GPU/service wires in this evidence
are explicit fixtures. Generated rights remain unknown, production eligibility
false and actual billed costs null. No real model/GPU/provider credentials,
payment, legal clearance, Owner UAT, external publication or deployment is
claimed. Native HTTP/UI and cost integration remain next.

The neutral adapter now supplies [read-only job reconciliation](COMFYUI_JOB_RECONCILIATION.md)
for a lost generation submission reply, including full frozen-request binding
and actual binary recovery without another submission. The `--reconcile`
rehearsal retains a separate evidence bundle; Native queue/worker/UI remain next.

The [Native durable queue](NATIVE_GENERATION_QUEUE.md) now persists admission,
fenced claims, inputs, cost binding, observations, cancellation and read-only
recovery requests. Worker execution, result ingestion/attachment and HTTP/Assets
integration remain next.
