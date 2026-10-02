# Provider-neutral zero-call qualifier V2 — source review candidate

Task: `VF-ASR-QUALIFIER-PROVIDER-NEUTRAL-SOURCE-REMEDIATION-01`.
Exact base: `993d44d238c95e1f22d5a0f83229a0f66c9cdbdf`.
Status: source-only candidate; Owner G-08 review required. No host is qualified
by this document or by the synthetic/offline tests.

## Confirmed RC27 defect

RC27 commit `76add7193926780add892128dbe373312fb54c56` includes the AssemblyAI
runtime adapter and provider credential mapping, but its qualifier still selects
OpenAI metadata, `openai-codex-video`, the corresponding encrypted-source path,
and `api.openai.com`. AssemblyAI metadata is rejected with
`SECRET_BINDING_POLICY_INVALID`. Changing private workflow YAML or systemd
wiring alone cannot change those public Python checks.

RC27 annotated object `e335e627c5b635b426f9a0e749d7c305b10d0649` remains immutable.
No historical receipts, secret bindings, backend qualification records,
RC25/RC26 evidence, promotions, or PR #103 contents are rewritten.

## Static identity, not a new caller input

`provider_credentials.provider_credential_binding()` is the sole source of the
provider-to-alias-to-systemd-ID mapping. The qualifier accepts exactly these
two provider keys; unknown providers fail before network or secret access.

| Provider | Credential alias | Systemd credential ID | TLS-only target |
| --- | --- | --- | --- |
| `openai-transcription` | `secret://openai/codex-video` | `openai-codex-video` | `api.openai.com:443` |
| `assemblyai-transcription` | `secret://assemblyai/stt-video-factory-benchmark` | `assemblyai-stt-video-factory-benchmark` | `api.assemblyai.com:443` |

The endpoint map is static/read-only. A workflow input cannot select a provider,
endpoint, credential ID, path, or command. Root-owned host configuration still
pins the canonical secret-binding metadata path. The encrypted-source path is
derived from the allowlisted credential ID below `/etc/credstore.encrypted`,
then compared exactly to metadata. Metadata never supplies a path to open.

## Historical V1

V1 retains `provider="openai"`, its exact field set, original task identifiers,
unbound-slot semantics and bound-source validation. The exact historical V1
backend receipt remains accepted only for OpenAI V1. Existing public constant
names remain import-compatible but now derive their values from the shared
credential mapping. Historical evidence bytes are not changed.

V1 qualification/promotion output retains its historical contract and task.
New AssemblyAI evidence cannot masquerade as V1 or reuse a V1 backend receipt.

## Strict V2 metadata

V2 replaces V1 `provider` with `provider_key`. Its exact field set is:

`version`, `provider_key`, `credential_alias`, `capability_scope`, `source_type`,
`source_locator`, `owner`, `expected_owner_uid`, `expected_owner_gid`,
`expected_mode`, `state`, `created_for`, `authority_granted`,
`secret_source_present`, `systemd_credential_id`, `encryption_key_type`,
`provider_runtime_reads`, `backend_qualification_receipt_sha256`.

Unknown fields and cross-provider aliases/IDs/paths are rejected. Bound V2
requires `version=2`, `capability_scope=["asr"]`, encrypted systemd source,
root UID/GID, mode `0400`, `authority_granted=false`, zero runtime reads, and
`created_for="VF-EXECUTOR-QUALIFICATION-V2"`. Boolean counters are not integers.
An unbound V2 slot can record metadata presence but cannot pass E7.

V2 backend evidence has the strict V1 custody/test field set plus `provider_key`
and `credential_alias`, with version/task changed to V2. It binds the canonical
systemd ID and encrypted-source path, mechanism `LoadCredentialEncrypted`, key
type `HOST`, root custody, synthetic encryption/name binding/service receive,
access isolation and cleanup. Actual provider credential decryption is false;
provider runtime reads and provider calls are zero. Each V2 value has the expected
type. The current systemd version is a bounded version string, not an assertion
that every future host must run the historical Ubuntu patch version.

The binding pins the exact SHA of the root-owned backend receipt. E7 reads only
non-secret metadata/receipt evidence, never the encrypted credential or host key.
Receipt identity/hash failure cannot produce
`PASS_SECRET_SOURCE_PRESENT_NOT_RESOLVED`.

## E6/E7 and evidence identity

Validated metadata selects the same canonical identity for E6 and E7. E6 performs
only a TLS handshake, checks for a certificate and records provider key, hostname,
port, `TLS_HANDSHAKE_ONLY`, zero HTTP requests and zero credential reads. Unit
tests mock the complete socket/TLS layer; no provider network connection occurs.

E7 revalidates metadata, requires unchanged metadata SHA and verifies backend
receipt SHA/identity. V2 report task is `VF-EXECUTOR-QUALIFICATION-V2`; its
`provider_identity` binds provider key, alias, systemd ID, secret-binding SHA,
backend-receipt SHA, hostname and port. The report remains a capability-probe
result with `execution_plane_qualified=false`, not Owner dispatch authority.

The independent security review retains all existing hostile-job checks,
workflow isolation, runner/source/executor identity, lock contention, engaged
kill switch and empty execution allowlist. V2 additionally carries this same
provider identity and checks metadata did not change during review.

Future V2 promotion and its evidence manifest retain version/task/provider
identity. Both creation and consumption cross-verify that identity against the
current sealed binding, probe E6/E7 and independent security review. A V2 artifact
cannot be relabeled, downgraded, or consumed as another provider's qualification.
The small change in `executor_execution.verify_qualification()` is limited to
this evidence admission check; dispatch, resolver one-shot, O2 and runtime
activation contracts are otherwise untouched.

Existing E1–E5/E8–E10 probe semantics remain unchanged. This patch does not assert
live AssemblyAI account validity or successful transcription. Live qualification
and any additional Owner host probes still require separate authority.

## Offline review matrix and boundaries

Tests cover historical OpenAI V1 slots/receipts and V2 for both providers; exact
aliases/IDs/paths; receipt hashes/custody; unknown/extra fields; version confusion;
cross-provider backend replay; static TLS mapping; no certificate; E6/E7 mismatch;
metadata drift; promotion identity persistence, consumer rejection and downgrade;
and independent security isolation. Explicit API-key environment/JSON assignments
and Authorization/Bearer material are rejected without flagging ordinary hashes.

Synthetic fixtures grant no execution authority. No real credential is read or
decrypted, and no provider HTTP request, audio upload, transcript job, reservation,
runtime activation, host deployment, qualification or promotion is performed by
this source task. AssemblyAI runtime/provider code and historical W0/W1/W2 paths
are unchanged; their regression suites must pass.

Executable drift is expected. RC27 cannot authorize deployment of this patch.
After Owner G-08 exact-head review: controlled merge, exact-main CI, a fresh
RC28 lock and RC CI, then governance closure are required. This task neither
merges nor creates RC28. PR #103 remains open/draft/frozen fallback.
