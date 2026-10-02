# RC28 provider-neutral qualifier V2 — governance closure candidate

Task: `VF-ASR-QUALIFIER-V2-G08-MERGE-RC28-01`.
Status: `RC28_SOURCE_LOCKED / GOVERNANCE_CLOSURE_CANDIDATE_READY`.
This document is source/release governance only. It neither qualifies an executor
host nor grants provider, credential, deployment, runtime or production authority.

## Exact source and approval closure

PR #106: `V3-01: make zero-call qualifier provider-neutral v2`.
Reviewed base: `993d44d238c95e1f22d5a0f83229a0f66c9cdbdf`.
Reviewed head: `4ddd6571f13344b4b94718507519592d648a4151`.
Reviewed scope: 8 files, 761 additions, 37 deletions, one source commit.
Pre-merge identity, paths, mergeability and exact-head CI were re-read after
APP-110 was sealed, including after the authorized Draft-to-Ready transition.

G-08 approval: `V3-01-APP-110`, decision `APPROVED`.
Record SHA-256:
`7b1cddbf7039233274325e4b9fb893f28ec9a2d1d5f99221aea833ac366cd367`.
The Owner-accepted five-store registry rescan established global highest APP-109
and APP-110 absent, unallocated and unreserved. Registry proof SHA-256:
`43641400d7bf9355afc4087e1ebf33a51bc5aba61baa1ec891222600d66bbbd4`.
No historical approval was overwritten, reused or repaired.

Source merge commit: `96a2d15beeb74abce72faede78ae7591719d2c83`.
Merge method: merge commit, not squash or rebase.
Parent 1: `993d44d238c95e1f22d5a0f83229a0f66c9cdbdf`.
Parent 2: `4ddd6571f13344b4b94718507519592d648a4151`.

## Executable source lock and source-side CI

Reviewed exact-head CI: `36963320478`, PASS 5/5, 1672 passed.
Fresh exact-main CI: `36967058083`, PASS 5/5, 1672 passed.
RC28 CI: `36967501986`, PASS 5/5, 1672 passed.
Python and Docker job logs verify the exact expected and checked-out SHA.
RC28 CI additionally verifies `GITHUB_REF=refs/tags/vf-v3-01-rc28`.

Annotated tag: `vf-v3-01-rc28`.
Tag object: `ab53af42f2d4c1e0a80e421c6c2d6844a5702212`.
Dereferenced commit: `96a2d15beeb74abce72faede78ae7591719d2c83`.
The tag was created only after exact-main CI passed, without changing RC27.

Canonical executable tree SHA-256:
`9e5a37e5118dd6e49c6ea0e1becd30f45d5bc8aca2a9a7a9c8d6bb4818dc095d`.
Executor executable tree SHA-256:
`88e55b06b053f2467c99f11b50b1fdfc9b4cd6459acd54b44ff4890ded9ae3f3`.
Workflow tree object:
`a7acb6b4574314f2a603fff276ddb03ce95e41e4`.
The governance closure candidate changes no executable, executor or workflow bytes.

Source provenance: `evidence/v3-01/vf-qualifier-v2-rc28-01/rc28-source-provenance.json`.
Source provenance SHA-256:
`fa85d27b94a24d028653ae5479281d874314caa183cf0ef8db74e56f0256edda`.
It binds all three source-side CI runs, the approval, registry proof, tag, topology,
source identities, historical compatibility and zero-use boundary.

## Qualification contract and historical firewall

New source contract: `VF-EXECUTOR-QUALIFICATION-V2`.
The qualifier uses a static provider allowlist and the shared provider credential
map. E6/E7 and qualification/security/promotion identities must agree.

| Provider | Alias | Systemd credential ID | TLS-only target |
| --- | --- | --- | --- |
| `openai-transcription` | `secret://openai/codex-video` | `openai-codex-video` | `api.openai.com:443` |
| `assemblyai-transcription` | `secret://assemblyai/stt-video-factory-benchmark` | `assemblyai-stt-video-factory-benchmark` | `api.assemblyai.com:443` |

These are non-secret source identifiers, not deployed bindings. Offline tests
mock network transport and use synthetic non-secret metadata/receipt fixtures.
No real TLS qualification probe, encrypted provider credential read/decryption,
HTTP provider request or transcription operation occurred in this task.

Historical OpenAI V1 keeps its exact field set, task identifiers and backend
receipt admission. W0/W1/W2 evidence is unchanged and remains compatible.
V2 cannot be replayed across providers or downgraded to V1 authority.
Unknown providers, alias/ID/path substitutions, metadata drift, receipt mismatch,
E6/E7 disagreement and cross-provider promotion reuse fail closed.

RC27 annotated tag object remains `e335e627c5b635b426f9a0e749d7c305b10d0649`,
at commit `76add7193926780add892128dbe373312fb54c56`.
PR #103 remains open/draft/frozen fallback at
`827c53cb2c022f48b056c48d8c6951e26d0fcf1e`; it was not modified, merged or closed.
No historical authority transfers to RC28.

## Stop boundary

This governance PR is Draft and must remain unmerged until a separate Owner gate.
Final RC28 dual-CI provenance is **NOT_CREATED**. The exact-main and RC CI above
are source-side evidence and do not replace post-governance-merge main CI.

Host mutation/deployment: NONE. Live qualification: NOT_RUN. Promotion: NONE.
Provider credential reads, provider API calls, uploads, transcript jobs,
reservations and spend: zero. Runtime activation, execution catalog, new ASR
lineage, G-01/G-02/G-03 and O2: NONE. Production remains NO-GO.

Next safe action: Owner review and controlled merge of this exact governance-only
candidate, followed by fresh exact governance-main CI and final RC28 dual-CI
provenance. Deployment and qualification require later separate authority.
