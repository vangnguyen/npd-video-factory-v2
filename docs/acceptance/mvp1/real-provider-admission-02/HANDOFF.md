# VF-MVP1-REAL-PROVIDER-ADMISSION-02

Source/admission integration only. No real-provider or MVP1 acceptance.

## Source ancestry

Provider branch: `codex/vf-mvp1-real-provider-enablement-01`.
Previous candidate: `a036f39ef71c0175ff3954ab870f92ecc0cfe3c2`.
Dependency: PR #108, `codex/vf-mvp1-multi-input-01`,
`57f6e507f9cc3d26f6db61da41012eafdb7936ba`.
The provider PR must be stacked on that branch, not main. PR #108 is not
merged or edited by this task. Exact final head/remote CI are recorded in the
external closeout receipt after this document's commit, not inferred here.

## Independent public admission contracts

`Mvp1AdmissionScope` version 1 is separate from historical ASR gates and RC28
acceptance lineage. Content and TTS each have their own root-custody,
raw-file-hash-pinned loader and Owner-selected profile. Disabled defaults load
no admission files. No production model, voice, input, approval ID, window or
budget is selected/allocated by this task.

The scope binds source commit, project/workspace, immutable input version/hash,
exact purpose/rights hash, provider/model/profile, one-attempt/no-fallback
limits, UTC window/day and budget. Content uses token planning rates/output
ceiling; TTS uses per-character planning rate and exact narration-unit hashes.
Planning rates are not measured usage or billed cost.

Public request preparation calls neither `preflight()` nor `execute()` and
does not resolve keys/reserve budget. `execution_authorized=false` scopes may
pass public preparation but cannot execute. A future live scope additionally
requires explicit paid/external flags, protected backend injection and its own
Owner authority. MVP1 capability scopes cannot enable historical ASR/Vision.

Raw file SHA pins the bytes/custody loader. Canonical scope SHA is a distinct
semantic digest. Both are carried in the protected resolver reference. There
is no arbitrary endpoint, source locator or plaintext credential in this
contract. Unknown provider/alias/lane and scope substitutions fail closed.

## Content generation

The existing static Responses adapter receives its lane's verified controller
and public resolver reference from API/worker construction. Real transport
remains disabled without the separately admitted protected backend. Generation
uses the existing durable/versioned job, cancellation, restart recovery,
proposal/diff/apply and user approval lifecycle. Generated facts remain
unverified; proposals cannot approve themselves or replace later edits.

Zero-call preparation builds the real request body and validates input/profile/
cost metadata. It is not full live preflight and uses no successful provider
response to establish admission.

## Vietnamese TTS

The existing production adapter now receives verified narration units via the
separate TTS loader. Render-scoped cloning binds workspace/project/content
version and actual render job ID. Cancellation and current-version checks run
before each synthesis unit. No ambient key or ASR credential alias is reused.

Persisted audio/raw response, decoding and actual duration are retained from
the enablement candidate. `PROVIDER_MEASURED`, `FORCED_ALIGNMENT` and
`ESTIMATED_SEGMENT` remain distinct timing sources. Historical
`MEASURED_PROVIDER` spelling is loadable; new evidence uses the canonical
spelling. This WAV adapter supplies no measured words: `WORD_ALIGNMENT_OPEN`.
There is no added aligner, fabricated word timing or eSpeak quality acceptance.
Owner production provider/model/voice selection and human review remain open.

## Resolver and runtime limits

`ProtectedResolverReference` is identity wiring/DI, not an installed secret
resolver or an approved credential backend. Default application construction
injects no protected transport, so live adapter readiness remains blocked.
The local one-shot guard is claimed before transport ambiguity; it is NOT a
replacement for a future protected backend's atomic cross-process spent claim.
That backend must be separately qualified and cannot be selected by prompt,
workflow command, environment key or caller endpoint. No runtime backend,
credential load validation, live scope or host authority is installed here.

## ASR source-only remediation package

Candidate exact unit: `npd-vf-secret-resolver.service`.
Additive drop-in:
`deploy/executor/npd-vf-secret-resolver.service.d/20-assemblyai-credential.conf`.
It adds only
`LoadCredentialEncrypted=assemblyai-stt-video-factory-benchmark:/etc/credstore.encrypted/assemblyai-stt-video-factory-benchmark`.
It does not reset/remove the historical OpenAI mapping. Static tests reject
wrong unit/ID/source, mount reset, plaintext mounts, commands and environment
expansion. Future expected custody is root:root, regular non-symlink, mode0644.
Windows-mounted source modes are not deployed host custody evidence.

The earlier uninstalled reset-style candidate is superseded only on this dev
branch (recoverable in its parent commit). Historical units, RC28 source/tag,
evidence, spent context and authority remain unchanged. No service installation,
reload/start, credential bytes, TLS probe or provider use occurs here.
Lane maximum status: `HOST_REMEDIATION_PACKAGE_READY`, not ASR call readiness.

## Admission matrix (remote CI recorded in closeout receipt)

| Capability | Source adapter | Scope loader | Resolver wiring | Selection | Credential runtime validation | Execution authority | Live call | Quality acceptance | Smallest next action |
|---|---|---|---|---|---|---|---|---|---|
| Content | PASS | PASS (synthetic public scope) | PASS (public reference); protected backend NOT_RUN | SELECTION_REQUIRED | NOT_RUN | AUTHORITY_REQUIRED | NOT_RUN | NOT_RUN | Owner choose exact model/profile, bounded inputs and budget, then authorize separate protected-backend qualification |
| TTS | PASS | PASS (synthetic units) | PASS (public reference); protected backend NOT_RUN | SELECTION_REQUIRED | NOT_RUN | AUTHORITY_REQUIRED | NOT_RUN | NOT_RUN; WORD_ALIGNMENT_OPEN | Owner choose provider/model/voice, bounded narration and budget; keep timing limitation explicit |
| ASR | PASS (existing adapter) | NOT_APPLICABLE (no fresh ASR scope) | HOST_REMEDIATION_REQUIRED | NOT_APPLICABLE (sealed model only) | NOT_RUN | AUTHORITY_REQUIRED | NOT_RUN | NOT_RUN (benchmark is not acceptance) | Separate Owner authority to install the additive mapping and perform protected zero-call credential-load validation; no old-context retry |

## Verification interpretation

Test fixtures are synthetic public contracts, not allocated approvals, real
rights, live windows or production authority. The root local loader tests use
actual ownership. Unprivileged CI unit tests simulate only UID0 stat metadata
for the named synthetic public fixture (all actual bytes/hash/mode/inode checks
remain); this is not host custody proof. A separate real non-root test proves
self-owned admission files are rejected, and another proves read-only evidence
blocks writes. Counts from overlapping suites must not be added.

No schema migration is added. Migration replay still covers existing 0016.
Exact command outcomes, skips, PostgreSQL/concurrency, renderer/Studio, remote
five-job CI, Docker E2E artifacts and PR state belong to the dated external
receipt. Prior task's tests/proof are not relabeled as this task's evidence.

## Zero-use boundary

Task provider calls/key reads/spend/production writes: zero. Source/dependency/
GitHub network reads are nonzero and separate from provider network. Disposable
fixture ledgers/database rows are not live reservations or production writes.
Host lifetime counters are NOT_VERIFIED. No merge, deployment, publication,
release/RC, authority allocation, runtime activation or provider acceptance.
