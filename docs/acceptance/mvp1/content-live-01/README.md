# VF-MVP1-CONTENT-CLOUD-BACKEND-MATERIALIZE-07

Source candidate only: `CONTENT_CLOUD_BACKEND_SOURCE_READY / OWNER_CANDIDATE_APPROVAL_REQUIRED`.
Owner execution approval is PENDING. `execution_authorized=false`. No provider
request, raw credential read, reservation, spend or production write is authorized.

The fixed backend is `codex-cloud-network-secret-content-v1`:
`secret://openai/video-factory-content-generation` → `NPD_VF_CONTENT_API_KEY`,
provider `openai-storyboard-content`, HTTPS destination `api.openai.com`.
Codex Cloud supplies an opaque Network Secret placeholder. The HTTPS proxy
substitutes the real key only for its configured credential destination. Local
code does not receive, inspect, hash or validate the real key. No key shape is
required. The backend checks only placeholder presence and non-empty value.
Diagnostics contain public identities and availability only.

`compose_disabled_content_cloud_candidate` is a trusted source composition
entrypoint. It accepts only a disabled, validated Content scope and injects the
fixed backend into `ProtectedResolverReference`. It is never selected by a
request, prompt, model output, Settings switch or ambient key. Default API and
worker composition remain without this backend. TTS and ASR cannot install it.
Only this exact concrete backend enables the Content adapter's inherited proxy
and CA settings; the header carries the unchanged placeholder. Other adapters
and historical transport behavior remain unchanged. This candidate factory
rejects live scopes. It does not install a live host, cross-process resolver
custody or new execution authority; those remain separate Owner/runtime work.

## Reproduction

With the repository's Python dependencies installed:

```sh
python scripts/materialize-content-cloud-candidate.py materialize --source-commit <implementation-commit>
python scripts/materialize-content-cloud-candidate.py verify
python scripts/materialize-content-cloud-candidate.py qualify
```

`verify` needs no credential or network. `qualify` checks the real environment
placeholder's availability, without displaying its value. It blocks HTTP and
socket requests and uses a repository that rejects any ledger access. It tests
the existing durable controller's disabled execution boundary; no budget is
reserved. It also proves the disabled resolver cannot hand off the placeholder.
Tests use labelled synthetic placeholder values and in-memory transports.
No `qualify` command attempts real-key validity, TLS or provider authorization.

The prompt is exactly the Owner text: UTF-8, LF paragraph breaks, no BOM or
terminal newline. A materialized differing prompt is refused, not rewritten.
The scope asset hash and rights asset hash are its raw-byte SHA. The operation
also pins the canonical ContentDocument SHA, including protected terms, facts,
instructions and approval state. Historical operations retain canonical
document hashing. This dual binding prevents unchanged prompt text from
authorizing a changed request document. The canonical request SHA is public
payload only; no header or placeholder contributes to any digest.

Profile prices are the Owner-provided Standard short-context planning inputs:
$0.10/$0.50 per million input/output tokens at 30,000 VND/USD. The serialized
profile uses 3,000/15,000 VND and a 5,000 VND operation envelope; the disabled
scope sets 20,000 VND per acceptance/day. These are planning inputs, not an
independent pricing fetch or actual provider usage. Exactly one operation,
one attempt, one concurrent call, no retry and no fallback are admitted as
disabled metadata. The future one-hour window is metadata only. All fact and
publication approvals remain human decisions; no media inputs are included.

The existing scope schema requires `decision=APPROVED` and an approval-shaped
identifier. `V3-01-APP-999907` is a candidate marker, not an allocated Owner
execution approval. Rights APPROVED records only the task's permission to use
this Owner-controlled prompt for an internal derivative proposal. It grants no
publication or provider execution. `CONTENT_CANDIDATE.json` separately and
explicitly records `owner_execution_approval=PENDING`.

## Source identity and policy

The implementation is committed first. Generated records are committed after
it and bind that exact implementation commit. A file cannot embed the SHA of
its own containing Git commit without circularity. The verifier requires the
pinned implementation to be an ancestor of HEAD and rejects any source change
outside this artifact directory. The final artifact HEAD and pinned source
commit are reported separately. CI verifies bytes and source ancestry; exact
child-branch push CI tests the final HEAD, not a PR merge SHA.

Credential isolation is the Network Secret's `allowed_domains=[api.openai.com]`;
package-manager destinations in general policy do not widen that substitution
rule. The script cannot introspect platform enforcement and reports
`NETWORK_POLICY_PLATFORM_MANAGED`. Platform environment-status evidence is
recorded separately when available. Unknown observations do not become PASS.

Historical runtime-only profile/scope/request hashes are not canonical inputs
to this materializer. Old evidence is unchanged. Approve the new reproducible
hashes before any later execution-authority work. This task does not claim
`CONTENT_ZERO_CALL_READY`, live backend custody or generated-content acceptance.
