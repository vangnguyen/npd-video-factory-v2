# RC-12 OpenAI ASR acceptance gate rebind

## Decision boundary

This checkpoint rebinds the existing bounded Vietnamese ASR acceptance inputs to the new
executable candidate after V3-01-20. It is governance and evidence only.

```text
RC-12: LOCKED / NO-GO / NOT DEPLOYED
ASR real-provider: NOT_TESTED
RC-12 Operation 1: NOT APPROVED / NOT EXECUTED
RC-12 Operation 2: NOT APPROVED / LOCKED / NOT EXECUTED
bundle mounted: false
credential reads: 0
provider calls: 0
reservations: 0 VND
spend: 0 VND
production: NO-GO
```

Neither this document, the annotated tag, the gate bundle, G-01/G-02/G-03 rebind records, CI
success nor G-08 for this PR authorizes a provider call. RC-12 Operation 1 requires a separate
owner decision after the governance merge and dual-CI provenance checks.

## Exact candidate and remediation lineage

| Item | Exact evidence |
| --- | --- |
| V3-01-20 PR | PR #44, exact head `a5666703fe7d0c0fe9a78deadc7eefd5bd848e61` |
| PR #44 base | `090f9085ccccf8ef30b926d7cc04a6c8a402128e` |
| PR #44 merge / RC-12 | `ca5483c889742c27af3368b9b487350d7daa217d` |
| Annotated tag | `vf-v3-01-rc12`, peeling to the exact merge commit above |
| Exact-head CI | `33888514088`, completed/success, 5/5 jobs |
| Exact-main executable-RC CI | `33889772222`, completed/success, 5/5 jobs |
| G-08 source approval | `V3-01-APP-047` |

PR #44 intentionally changed the executable provider-safety tree. RC-12 therefore supersedes
RC-11 for any future live ASR acceptance. RC-11 Operation 1 remains an immutable
`BLOCKED_PRE_CALL / NOT CONSUMED / 0 CALLS / 0 VND` receipt; its authority, window, operation IDs
and live use of its bundle are retired. RC-11 Operation 2 remains locked.

## Rebound provider and operation scope

| Field | RC-12 binding |
| --- | --- |
| Provider | `openai-transcription` |
| Model | `whisper-1` |
| Capability / language | `asr / vi` |
| Credential reference | `secret://openai/codex-video` alias only; value absent |
| Operation 1 | `v3-01-rc12-openai-transcription-asr-call-01` |
| Operation 2 | `v3-01-rc12-openai-transcription-asr-call-02` |
| Execution-scope SHA-256 | `6f0aecf227df30d493566a8d089a6097f83c454993b6ce25eb00eeb887fb9cc4` |
| Gate bundle | [`V3-01-GATE-RC12-OPENAI-ASR-A.json`](V3-01-GATE-RC12-OPENAI-ASR-A.json) |
| Raw bundle SHA-256 | `218e06d245f43733a2659aff35f4ea0e7e73dcd17258f663d351b198aebf3db1` |

Operation IDs are freshly derived from exact RC-12 identity, provider, capability and ordinal.
Neither RC-11 operation ID appears in the RC-12 bundle. Each operation is also bound to the exact
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
`0d7aef962dcb5e34ed5786fadd2e9cfd156cbfb8784d498092262d33b76de7c0`. Its RC-11 name records
provenance; it does not make the old runtime authority reusable. Both RightsRecords remain
`APPROVED`, have no expiry, authorize only bounded OpenAI ASR acceptance and continue to prohibit
publishing, training, resale and every unrelated use.

## Owner-gate rebind records

| Gate | Record | Canonical record SHA-256 | Meaning |
| --- | --- | --- | --- |
| G-01-ASR | `V3-01-APP-048` | `dc3b2a60d2feabdb9bb3bd84305fcc29e63627c1d3dbf2bdf4c7a5ac4321c6e6` | exact RC-12/provider/model/capability/credential alias only |
| G-02-ASR | `V3-01-APP-049` | `c8499dfd63a1fff8b203b3ea5eb7357b520528178dedf61f1d603f8a67052191` | exact VND, duration, file-size and timeout envelope |
| G-03-ASR | `V3-01-APP-050` | `88a9b5525d2131ac7c45b3ae5c566b38922c61ba8e5b83130302f90649977422` | exact unchanged assets, transcripts, rights and bounded use |

All three records bind the exact RC-12 commit and the exact new execution-scope hash. They do not
authorize a runtime attempt.

## Proposed dated safety envelope

The proposed window is `2026-09-05T14:00:00Z` through `2026-09-05T18:00:00Z`, equivalent to
21:00 on 05 September through 01:00 on 06 September 2026 in Asia/Ho_Chi_Minh. It stays within one
UTC budget day and lasts four hours. The window remains non-executable until the governance PR is
merged, exact governance-main CI and executable-tree equality pass, and the owner separately
approves RC-12 Operation 1.

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
  both RC-12 slots;
- an unapproved asset fails before a durable operation row or reservation can be created;
- checked-in defaults remain fixture-selected, zero-budget and kill-switch engaged.

After this governance PR receives G-08 and merges, the required sequence is:

```text
exact governance-main CI PASS
-> bind governance-main CI run and commit
-> prove governance diff is allowlisted
-> prove governance executable tree equals vf-v3-01-rc12
-> verify bundle/scope/assets/rights unchanged
-> verify bundle remains unmounted and ledger has no RC-12 operation row
-> request separate authority for v3-01-rc12-openai-transcription-asr-call-01
```

No RC-13 is created by a governance-only merge if executable-tree equality holds. Operation 2
stays locked until Operation 1 produces complete evidence and receives a separate owner review.
Production remains `NO-GO` regardless of either bounded acceptance operation.
