# RC-15 OpenAI ASR acceptance gate rebind

## Decision boundary

This is a governance/evidence-only proposal after the owner-approved merge of PR #50.
It changes neither executable code nor runtime configuration. The bundle is unmounted.
The rebind records preserve the approved provider, rights and budget limits but do not
authorize a credential read or an operation. The proposed dated window needs governance
G-08 review and a later, separate Operation 1 decision.

```text
RC-15: LOCKED / NOT DEPLOYED
Vision real-provider: 2/2 consecutive PASS (standalone authority retired)
ASR real-provider: NOT_TESTED / 0/2 consecutive PASS
RC-15 Operation 1: NOT APPROVED / NOT EXECUTED
RC-15 Operation 2: NOT APPROVED / LOCKED / NOT EXECUTED
Bundle mounted: false
Credential reads / provider calls / live reservations / spend: 0 / 0 / 0 VND / 0 VND
Production: NO-GO
```

## Exact executable candidate

| Item | Evidence |
| --- | --- |
| Source remediation | [PR #50](https://github.com/vangnguyen/npd-video-factory-v2/pull/50), V3-01-22 zero-duration word timestamp semantics |
| Approved source head | `7fb783291159ab895654c8ea517f2d9eec4cc8fe` |
| Source base | `46937d9fe4804c7c7190995afb2c48377c70f70e` |
| Merge / governance proposal base | `7d1290aacac61df98a51544731243e5e322a8644` |
| Annotated tag | `vf-v3-01-rc15` |
| Tag object | `53e3560d0c4f77a9e53c98f1dd89ca45aa42674c` |
| Tag peeled commit | `7d1290aacac61df98a51544731243e5e322a8644` |
| Exact source-head CI | [34140738281](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34140738281), completed/success, 5/5 jobs |
| Exact-main / executable-RC CI | [34142662132](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34142662132), completed/success, 5/5 jobs |
| Executable-tree SHA-256 | `9fab766b285eb2db580032b914eb2ccdf474d18b3958fd218a73a22fb75701e8` |
| Source G-08 record | [V3-01-APP-060](approvals/V3-01-APP-060.json) |

The exact-main regression includes Python/API/worker/bridge, Studio, Renderer tests/typecheck/
bundle, migration downgrade/replay, acceptance/Flow A/B/C/DR validation, safety and Docker
deterministic E2E. An additional local exact-main Python run passed 471 tests; focused semantics
and historical gate tests passed 23 tests. No provider was called by these tests.

## Timestamp semantics are not downstream acceptance

[V3-01-22 semantics](55_V3_01_22_ASR_ZERO_DURATION_WORD_SEMANTICS.md) permits a
`provider_boundary_point` only when its unchanged timestamp is anchored to an adjacent word
boundary. Positive intervals retain `positive_interval`. There is no epsilon, invented duration,
endpoint swap, dropped word or transcript rewrite. Inverted, negative, out-of-range, unbound,
overlapping or malformed timing remains fail-closed.

`PositiveDurationTranscript` still requires genuine positive intervals for scene/silence,
persistence and edit consumers. A transcript containing provider boundary points cannot enter
that path: `POSITIVE_DURATION_TRANSCRIPT_REQUIRED` is expected. Accepting provider evidence is
not approval to alter timestamps or to bypass downstream checks. Any later downstream design
needs its own review; this governance PR does not implement one.

RC-15 is not presumed PASS. A later authorized ASR attempt must provide a valid transcript,
usage and actual-cost receipts, source/rights binding, complete evidence, WER/critical-term and
timestamp evaluation. ASR aggregate acceptance remains 0/2; production-path and human quality
remain NOT_TESTED.

## Historical RC-14 is immutable

RC-14 Operation 1 received HTTP 200 with 413 word records, including 27 exact equality points.
It remains `REVIEW_REQUIRED / CONSUMED`; actual provider cost is UNKNOWN. The 500 VND safety
charge is not an actual-cost receipt. The historical transcript/usage/cost that was not retained
is not reconstructed and no historical verdict is upgraded.

The original receipt SHA-256 remains
`2d65b3e4c1ec1afc5f6b262a1ea294c811be5dba9718a06992da9fe3a8d2b1bd`.
The [immutable forensic report](../../../evidence/v3-01/vf-v3-01-20260907T145428Z-46937d9-rc14-asr-forensics/rc14-asr-operation-1-word-timestamp-forensics.json)
has file SHA-256 `ef98e46d523529b4a252fc8eb256ddd38cf5a7183a5fe723763b4cb687b2e569`.
Both RC-14 operation IDs, its bundle, window and authority are retired for live acceptance.
RC-14 Operation 2 remains locked and must not run.

## Fresh RC-15 bindings

| Field | Value |
| --- | --- |
| Provider / model | `openai-transcription / whisper-1` |
| Capability / language | `asr / vi` |
| Credential reference | `secret://openai/codex-video` (alias only; no value read) |
| Slot 1 | `v3-01-rc15-openai-transcription-asr-call-01` |
| Slot 2 | `v3-01-rc15-openai-transcription-asr-call-02` |
| Scope SHA-256 | `fee7086afeac45fa38c225365ceeae293f1a80aea1eba73bb261ce34aca350aa` |
| Bundle | [V3-01-GATE-RC15-OPENAI-ASR-A.json](V3-01-GATE-RC15-OPENAI-ASR-A.json) |
| Raw bundle SHA-256 | `d1075d9c22c9a6fb3f608ffcd5bf2de09d81895a2b17680fc981a3680249a966` |
| Canonical budget SHA-256 | `eff5a407da6892a4f3d78afaf84b947210d39c598def1dd2813929a934eaa594` |

The canonical loader derives IDs from RC identity/provider/capability/slot and binds exact
commit/tag, scope, asset and window. Old RC-14 IDs cannot substitute for either RC-15 slot.
Allowlist membership is not operation authority.

## Unchanged owner-confirmed inputs

| Slot | WAV SHA-256 | Bytes / duration | Reference transcript SHA-256 | RightsRecord canonical SHA-256 |
| --- | --- | --- | --- | --- |
| 1 | `fce31015644960a5f69640d7f5b90a7da078887b15c9d17dc227530d26b875ef` | 5,800,940 / 120.852 s | `585b460291f11f1eb54c2b9a728bca26953ccce98719859e16ab15c7af9ff36e` | `5fb56c9817595693abea89176362e0efebbcab54867788d427e9f4a76d0a8091` |
| 2 | `dce36c5246c17e0385842006dcb0088a8c97a79d3009796815c2564c075cf20b` | 6,460,396 / 134.590667 s | `0bff8c2b403cee452fac00f71b84759988ea515027fda6bd49be76ae382c1fef` | `972dcc752b6bc606a655f272472128a8e6c47fa7858f2bd0cc8e9b9f8c4e4323` |

Both WAVs remain mono PCM, 24 kHz, at least 90 seconds and below the 180-second hard cap.
The [owner manifest](assets/V3-01-RC11-ASR-ASSET-MANIFEST.json) remains byte-identical, SHA-256
`0d7aef962dcb5e34ed5786fadd2e9cfd156cbfb8784d498092262d33b76de7c0`. RightsRecords have no expiry,
preserve the owner's bounded voice-processing consent and prohibit publishing, training and resale.
No media/reference transcript/rights file is regenerated or edited.

## Rebind records and proposed window

| Gate | Record | Canonical SHA-256 |
| --- | --- | --- |
| G-01-ASR | [V3-01-APP-061](approvals/V3-01-APP-061.json) | `852e920c4a8ac06681d55bc0062b85f6e43bdcd6d49ceb48546810734149381c` |
| G-02-ASR | [V3-01-APP-062](approvals/V3-01-APP-062.json) | `eb559b549a82885da40e5dddd8189ab10bfdc4362ead99835474fa21e6c67340` |
| G-03-ASR | [V3-01-APP-063](approvals/V3-01-APP-063.json) | `aca0b3ef0ea6cca3f1adadcea264787caa2c5ef84009027639b6f434f33da8f3` |

Proposed window: **2026-09-08 14:00–18:00 UTC**, equivalent to **21:00 on 08 September →
01:00 on 09 September 2026 ICT**. One UTC budget day, at most four hours. This proposal neither
extends old authority nor creates a schedule or operation authority. A changed scope/bundle/window
requires review and rebind; there is no automatic extension.

| Control | Limit |
| --- | --- |
| Per-operation reservation / window ceiling | 500 / 1,250 VND |
| Accounting rate | 162 VND/minute (fixed approved 0.006 USD/minute × 27,000 VND/USD accounting basis) |
| Modeled slot 1 / slot 2 costs | 326.3004 / 363.3948 VND; total 689.6952 VND; estimates, not receipts |
| Duration / file cap | 180 seconds / 25,000,000 bytes; target 90–120 seconds, owner-approved exact durations 120.852 / 134.590667 seconds retained |
| Format | `verbose_json`, native segment + word timestamps, language `vi` |
| Provider HTTP / controller hard timeout | 90 / 120 seconds |
| Attempts / concurrency / retry / fallback | 1 / 1 / 0 / 0 |

Checked-in selectors remain fixture, model empty, external/paid false, budget 0 VND, kill switch
engaged and gate bundle disabled/unmounted. Test-only disposable reservations do not activate
the live acceptance ledger or consume either real operation.

## Offline verification evidence

The [machine-readable gate validation](../../../evidence/v3-01/vf-v3-01-20260907T162407Z-7d1290a-rc15-asr-gate/provider/rc15-asr-gate-validation.json)
and [test-summary snapshot](../../../evidence/v3-01/vf-v3-01-20260907T162407Z-7d1290a-rc15-asr-gate/provider/test-summary.json)
distinguish exact-main regression from the new focused bundle tests. Fresh gate tests passed
18/18; evidence/offline-preparation tests passed 37/37. The subsequent full local governance
branch Python/API/worker/bridge regression passed 489/489. These focused counts overlap the full
suite and must not be summed as distinct tests.

Repository acceptance validation passes for 60 matrix rows, 16 gaps, 63 approval records,
3 RightsRecords and 35 evidence runs. JSON parsing, local Markdown path checks, checksums,
secret scan and whitespace validation passed; no historical evidence was rewritten. These are
offline governance checks, not real-provider or production acceptance. The final draft-head CI
will be reported in the PR; the committed snapshot predates that CI and does not invent its ID.

## Next owner gate

The exact executable-RC CI exists. The future governance-main commit and its CI **do not yet
exist**; dual-CI provenance is `PENDING_POST_MERGE`. Neither the RC CI nor this PR's head CI may
stand in for the post-governance-main CI.

```text
Draft governance PR -> separate owner G-08 -> merge
-> exact governance-main CI PASS, with its own run/commit
-> dual-CI provenance + allowlisted diff + executable-tree equality
-> verify unchanged bundle/scope/assets/transcripts/RightsRecords
-> verify bundle unmounted, live budget untouched and fresh operation unconsumed
-> separate owner authority for RC-15 ASR Operation 1
-> full time-bound preflight before any later attempt
```

Stop at this PR's owner G-08. No merge, RC-16, credential read, provider call, reservation,
automation, Operation 1/2 authority, deployment, publishing or public ingress is created by this
proposal. Production remains **NO-GO**.
