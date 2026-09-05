# RC-13 OpenAI ASR acceptance gate rebind

## Decision boundary

This checkpoint rebinds the unchanged Vietnamese ASR acceptance inputs to the executable
candidate containing V3-01-21 diagnostics. It is governance and evidence only.

```text
RC-13: LOCKED / NO-GO / NOT DEPLOYED
ASR real-provider: NOT_TESTED
RC-13 Operation 1: NOT APPROVED / NOT EXECUTED
RC-13 Operation 2: NOT APPROVED / LOCKED / NOT EXECUTED
bundle mounted: false
credential reads: 0
provider calls: 0
reservations: 0 VND
spend: 0 VND
production: NO-GO
```

Neither this document, the annotated tag, the gate bundle, G-01/G-02/G-03 rebind records, CI
success nor G-08 for this governance PR authorizes a provider call. RC-13 Operation 1 requires a
separate owner decision after the governance merge and dual-CI provenance checks.

## Exact candidate and remediation lineage

| Item | Exact evidence |
| --- | --- |
| V3-01-21 PR | PR #46, exact head `7169cc4db55931ee4fc145411e1e04651c004785` |
| PR #46 base | `f765f216f90b0d05071cc7c873a2edb6d5bdcec4` |
| PR #46 merge / RC-13 | `1e0146b44b19a5afcef267132d71d36d24a952e4` |
| Annotated tag | `vf-v3-01-rc13`, tag object `75a8c0f1b59452d47cfd7b36397ba1feb7fb14b2` |
| Exact-head CI | `33974602125`, completed/success, 5/5 jobs |
| Exact-main executable-RC CI | `33976046393`, completed/success, 5/5 jobs |
| Executable-tree SHA-256 | `51231c4c054e52dbde56fb774fb1937ee4c53f8f572cfdc5e1c6e339cb9a78a8` |
| G-08 source approval | `V3-01-APP-052` |

PR #46 intentionally changed the executable response-diagnostics and evidence-scanning path.
RC-13 therefore supersedes RC-12 for any future live ASR acceptance. RC-12 Operation 1 remains
immutable as `CONSUMED / FAILED_RESPONSE_VALIDATION / REVIEW_REQUIRED`; its missing transcript,
usage and actual-cost data remain unknown and are not reconstructed. RC-12 Operation 2 is retired
and locked.

V3-01-21 did not loosen the provider response schema. The synthetic malformed-response fixture is
only a representative diagnostic test and is not presented as the unknown RC-12 raw response.
The next bounded response-validation failure, if any, must identify its exact safe field path and
error code before any schema change is considered.

## Rebound provider and operation scope

| Field | RC-13 binding |
| --- | --- |
| Provider | `openai-transcription` |
| Model | `whisper-1` |
| Capability / language | `asr / vi` |
| Credential reference | `secret://openai/codex-video` alias only; value absent |
| Operation 1 | `v3-01-rc13-openai-transcription-asr-call-01` |
| Operation 2 | `v3-01-rc13-openai-transcription-asr-call-02` |
| Execution-scope SHA-256 | `179624fe3a365e415c41b760e49297da0cd23227cf9b49a634e7fbcaaf90b47e` |
| Gate bundle | [`V3-01-GATE-RC13-OPENAI-ASR-A.json`](V3-01-GATE-RC13-OPENAI-ASR-A.json) |
| Raw bundle SHA-256 | `236262caf3ae4a10c8c3fa760e9caf134837e4327b860b2d4693e08c7031f1b8` |

Operation IDs are freshly derived from exact RC-13 identity, provider, capability and ordinal.
Neither RC-12 operation ID appears in the RC-13 bundle. Each operation is also bound to the exact
asset ID and SHA-256 for its slot.

## Revalidated G-03 inputs

No media, transcript or RightsRecord was regenerated. The rebind preserves the original immutable
owner-confirmed evidence and verifies it again byte-for-byte or canonically as appropriate.

| Slot | WAV SHA-256 | Duration | Reference transcript SHA-256 | RightsRecord canonical SHA-256 |
| --- | --- | ---: | --- | --- |
| 1 | `fce31015644960a5f69640d7f5b90a7da078887b15c9d17dc227530d26b875ef` | 120.852 s | `585b460291f11f1eb54c2b9a728bca26953ccce98719859e16ab15c7af9ff36e` | `5fb56c9817595693abea89176362e0efebbcab54867788d427e9f4a76d0a8091` |
| 2 | `dce36c5246c17e0385842006dcb0088a8c97a79d3009796815c2564c075cf20b` | 134.590667 s | `0bff8c2b403cee452fac00f71b84759988ea515027fda6bd49be76ae382c1fef` | `972dcc752b6bc606a655f272472128a8e6c47fa7858f2bd0cc8e9b9f8c4e4323` |

The immutable owner manifest remains
[`V3-01-RC11-ASR-ASSET-MANIFEST.json`](assets/V3-01-RC11-ASR-ASSET-MANIFEST.json), raw SHA-256
`0d7aef962dcb5e34ed5786fadd2e9cfd156cbfb8784d498092262d33b76de7c0`. Both RightsRecords remain
`APPROVED`, have no expiry, authorize only bounded OpenAI ASR acceptance and continue to prohibit
publishing, training, resale and every unrelated use.

## Owner-gate rebind records

| Gate | Record | Canonical record SHA-256 | Meaning |
| --- | --- | --- | --- |
| G-01-ASR | `V3-01-APP-053` | `df317dc6fd6429ad2ee29eb5c63a49145dd5b0a8b82c80cf99a911d1bac6613b` | exact RC-13/provider/model/capability/credential alias only |
| G-02-ASR | `V3-01-APP-054` | `cf5b198895d3bc288da103ec553d07bda0fa27637ccdcc15a8ad08516a7206d3` | exact VND, duration, file-size and timeout envelope |
| G-03-ASR | `V3-01-APP-055` | `ce597576e9844e90200d90b3e4dc14cd2803197b31d6f4471064d43f3bc5f4f9` | exact unchanged assets, transcripts, rights and bounded use |

All three records bind the exact RC-13 commit and the new execution-scope hash. They do not
authorize a runtime attempt.

## Proposed dated safety envelope

The proposed window is `2026-09-06T14:00:00Z` through `2026-09-06T18:00:00Z`, equivalent to
21:00 on 06 September through 01:00 on 07 September 2026 in Asia/Ho_Chi_Minh. It stays within one
UTC budget day and lasts four hours. The window remains non-executable until the governance PR is
merged, exact governance-main CI and executable-tree equality pass, and the owner separately
approves RC-13 Operation 1.

| Control | Bound value |
| --- | ---: |
| Per-operation reservation | 500 VND |
| Acceptance-window ceiling | 1,250 VND |
| Accounting rate | 162 VND/minute |
| Hard media duration | 180 seconds |
| Hard file size | 25,000,000 bytes |
| Provider HTTP timeout | 90 seconds |
| Controller hard envelope | 120 seconds |
| Attempts / concurrency | 1 / 1 |
| Retry / fallback | 0 / 0 |

The two modeled input costs remain below 500 VND individually and below 1,250 VND in aggregate.
Checked-in and production budgets remain zero.

## Verification and post-merge gate

This proposal validates offline that:

- the raw bundle and derived execution-scope hashes are exact;
- embedded G-01/G-02/G-03 and RightsRecords match their external canonical records;
- both WAVs, transcripts, durations, sizes and rights hashes remain unchanged;
- durable and non-durable safety controllers select the same exact asset-bound RightsRecord for
  both RC-13 slots;
- an unapproved asset fails before a durable operation row or reservation can be created;
- checked-in defaults remain fixture-selected, zero-budget and kill-switch engaged;
- no production response schema has been weakened by this governance rebind.

After this governance PR receives G-08 and merges, the required sequence is:

```text
exact governance-main CI PASS
-> bind governance-main CI run and commit
-> prove governance diff is allowlisted
-> prove governance executable tree equals vf-v3-01-rc13
-> verify bundle/scope/assets/rights unchanged
-> verify bundle remains unmounted and ledger has no RC-13 operation row
-> request separate authority for v3-01-rc13-openai-transcription-asr-call-01
```

No RC-14 is created by a governance-only merge if executable-tree equality holds. Operation 2
stays locked until Operation 1 produces complete evidence and receives a separate owner review.
Production remains `NO-GO` regardless of either bounded acceptance operation.
