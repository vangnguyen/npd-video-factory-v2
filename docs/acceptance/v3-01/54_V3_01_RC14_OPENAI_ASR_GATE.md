# RC-14 OpenAI ASR acceptance gate rebind

## Decision boundary

This checkpoint rebinds the unchanged Vietnamese ASR acceptance inputs to the executable
candidate containing V3-01-22 timestamp canonicalization and validation diagnostics. It is
governance and evidence only.

```text
RC-14: LOCKED / NO-GO / NOT DEPLOYED
ASR real-provider: NOT_TESTED
RC-14 Operation 1: NOT APPROVED / NOT EXECUTED
RC-14 Operation 2: NOT APPROVED / LOCKED / NOT EXECUTED
bundle mounted: false
credential reads: 0
provider calls: 0
reservations: 0 VND
spend: 0 VND
production: NO-GO
```

Neither this document, the annotated tag, the gate bundle, G-01/G-02/G-03 rebind records, CI
success nor G-08 for this governance PR authorizes a provider call. RC-14 Operation 1 requires a
separate owner decision after the governance merge and dual-CI provenance checks.

## Exact candidate and remediation lineage

| Item | Exact evidence |
| --- | --- |
| V3-01-22 PR | PR #48, exact head `4f36133399e37683704f1a6605423bc6428159c3` |
| PR #48 base | `b41ed673bc343e33092a3d91253045729b663c7c` |
| PR #48 merge / RC-14 | `0b0965c650f4d06a057acbbb1a7ed9d7b933478b` |
| Annotated tag | `vf-v3-01-rc14`, tag object `d4ee474e02de5146c4a4dd7eea20ac96011abce5` |
| Exact-head CI | `34041347519`, completed/success, 5/5 jobs |
| Exact-main executable-RC CI | `34042079905`, completed/success, 5/5 jobs |
| Executable-tree SHA-256 | `a10dca84ec8a6ae7a1538e467fe72dcefa7fe89e2f0cf7ba2603df50878b3279` |
| G-08 source approval | `V3-01-APP-056` |

PR #48 intentionally changed the executable timestamp canonicalization, validation and diagnostic
path. RC-14 therefore supersedes RC-13 for any future live ASR acceptance. RC-13 Operation 1
remains immutable as `CONSUMED / FAILED_RESPONSE_VALIDATION / REVIEW_REQUIRED`: provider HTTP was
200, 17 segments and 412 words were returned, and 27 words failed the former strict interval
validator. Its transcript, usage and actual provider cost remain unavailable; the 500 VND entry is
only a conservative safety charge. RC-13 Operation 2 is retired and locked.

V3-01-22 does not turn invalid provider timestamps into plausible data. It permits only
representation-safe negative-zero normalization and six-decimal rounding, keeps raw and canonical
values separate, records a reason for every transformation, and continues to reject zero-duration,
inverted, collapsed, missing, non-numeric, overlapping, out-of-segment and out-of-range intervals.
Because RC-13 did not preserve all raw word timestamps, RC-14 Operation 1 is diagnostic-capable
acceptance, not a presumed PASS.

## Rebound provider and operation scope

| Field | RC-14 binding |
| --- | --- |
| Provider | `openai-transcription` |
| Model | `whisper-1` |
| Capability / language | `asr / vi` |
| Credential reference | `secret://openai/codex-video` alias only; value absent |
| Operation 1 | `v3-01-rc14-openai-transcription-asr-call-01` |
| Operation 2 | `v3-01-rc14-openai-transcription-asr-call-02` |
| Execution-scope SHA-256 | `03c2ad3bf2173a890344db0b011ab932fac35a96e98df0f8e501ba7261b7b852` |
| Gate bundle | [`V3-01-GATE-RC14-OPENAI-ASR-A.json`](V3-01-GATE-RC14-OPENAI-ASR-A.json) |
| Raw bundle SHA-256 | `351f1cac3dd90df7ffc8a0b8b70e3c3c9a92480b91d258b012426f570cc410dd` |

Operation IDs are freshly derived from exact RC-14 identity, provider, capability and ordinal.
Neither RC-13 operation ID appears in the RC-14 bundle. Each operation is also bound to the exact
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
| G-01-ASR | `V3-01-APP-057` | `9bac81b21e0a63b5b3f0f2049097695107148ca888731b5f8680c59c252f58f4` | exact RC-14/provider/model/capability/credential alias only |
| G-02-ASR | `V3-01-APP-058` | `ad309166db4f45fdaa4d0fab9a9f14d3f0f503b4bfc3516be6859d505f975766` | exact VND, duration, file-size and timeout envelope |
| G-03-ASR | `V3-01-APP-059` | `dd221a73c5deb11c11a649f15d00b12c6fc4e45fad55aa67c2ff408a6455f1f8` | exact unchanged assets, transcripts, rights and bounded use |

All three records bind the exact RC-14 commit and the new execution-scope hash. They do not
authorize a runtime attempt.

## Proposed dated safety envelope

The proposed window is `2026-09-07T14:00:00Z` through `2026-09-07T18:00:00Z`, equivalent to
21:00 on 07 September through 01:00 on 08 September 2026 in Asia/Ho_Chi_Minh. It stays within one
UTC budget day and lasts four hours. The window remains non-executable until this governance PR is
merged, exact governance-main CI and executable-tree equality pass, and the owner separately
approves RC-14 Operation 1.

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
  both RC-14 slots;
- an unapproved asset fails before a durable operation row or reservation can be created;
- RC-14 timestamp canonicalization retains raw/canonical provenance and remains fail-closed for
  unsafe intervals;
- checked-in defaults remain fixture-selected, zero-budget and kill-switch engaged.

After this governance PR receives G-08 and merges, the required sequence is:

```text
exact governance-main CI PASS
-> bind governance-main CI run and commit
-> prove governance diff is allowlisted
-> prove governance executable tree equals vf-v3-01-rc14
-> verify bundle/scope/assets/rights unchanged
-> verify bundle remains unmounted and ledger has no RC-14 operation row
-> request separate authority for v3-01-rc14-openai-transcription-asr-call-01
```

No RC-15 is created by a governance-only merge if executable-tree equality holds. Operation 2
stays locked until Operation 1 produces complete evidence and receives a separate owner review.
Production remains `NO-GO` regardless of either bounded acceptance operation.
