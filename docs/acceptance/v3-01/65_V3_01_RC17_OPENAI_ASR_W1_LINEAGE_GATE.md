# RC-17 OpenAI ASR W1 fresh lineage v2 gate

## Decision boundary

This package materializes one fresh two-slot W1 acceptance lineage after the owner-approved merge
of V3-01-27. It changes only governance, evidence and focused tests. It does not alter the RC-17
executable tree or checked-in runtime configuration. The bundle is committed for review but remains
disabled and unmounted. Its allowlist is not execution authority.

```text
Executable RC: vf-v3-01-rc17 / d08ffc005d7f3ad517d355977b0bc3cc8d686906
Fresh lineage: sequence 1 / al-0001-b82fc34d...ec380329
ASR real-provider: NOT_TESTED / 0/2 consecutive PASS
Historical RC-16 W1 lineage: RETIRED
Fresh Operation 1: NOT APPROVED / NOT EXECUTED
Fresh Operation 2: NOT APPROVED / LOCKED / NOT EXECUTED
Bundle mounted: false
Credential reads / provider calls / live reservations / spend: 0 / 0 / 0 / 0 VND
Vision real-provider: 2/2 consecutive PASS
Production: NO-GO
```

## Exact executable candidate

| Item | Evidence |
| --- | --- |
| Source remediation | [PR #57](https://github.com/vangnguyen/npd-video-factory-v2/pull/57), V3-01-27 Acceptance Lineage Identity Contract |
| Source base | `c0f051c866d329544486e5e757349f0543ace980` |
| Approved source head | `8171c764bfb59432e69ea7cf8c98639d6f0b4e68` |
| Merge / executable RC | `d08ffc005d7f3ad517d355977b0bc3cc8d686906` |
| Annotated tag | `vf-v3-01-rc17` |
| Tag object | `ea67843635dddf94ee25d38111fc06782ad9fd74` |
| Exact source-head CI | [34510687446](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34510687446), completed/success, 5/5 jobs |
| Exact-main / executable-RC CI | [34550127181](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34550127181), completed/success, 5/5 jobs |
| Executable-tree SHA-256 | `ee9831c59bba0df9a8fe975d8f539028d218cc0279b5fcf4acc72724b0910b40` |
| Source G-08 record | [V3-01-APP-068](approvals/V3-01-APP-068.json) |

Exact-main local regression passed Python/API/worker/bridge, Studio, Renderer tests/typecheck/bundle,
migration 0014 upgrade/downgrade/replay, acceptance/Flow A/B/C/DR validation and Docker deterministic
E2E. No provider transport or credential resolver was instantiated. The governance branch must
preserve the executable-tree hash above; otherwise this proposal is invalid and a new RC is needed.

## Canonical lineage identity

The v2 bundle uses sequence `1` and the canonical identity:

`al-0001-b82fc34d364bd33a73c9f7eb9d99a8108d77be25449ab5e35a4df7f1ec380329`

It is derived from the contract marker, exact RC tag and commit, provider
`openai-transcription`, model `whisper-1`, capability `asr` and bounded sequence. It is not a
free-form nonce. The runtime must independently pin the same lineage ID. Missing, tampered, stale,
cross-RC, cross-provider, cross-model or cross-capability identity fails before reservation.

The two derived slots are:

1. `v3-01-rc17-openai-transcription-asr-al-0001-b82fc34d364bd33a73c9f7eb9d99a8108d77be25449ab5e35a4df7f1ec380329-call-01`
2. `v3-01-rc17-openai-transcription-asr-al-0001-b82fc34d364bd33a73c9f7eb9d99a8108d77be25449ab5e35a4df7f1ec380329-call-02`

RC-16 operation IDs cannot be reused in this scope. Slot membership does not authorize either
operation; a separate owner decision is still required for Operation 1, and Operation 2 stays
locked until a clean first result is reviewed.

## Immutable W1 profile and quality rules

Both slots use exactly `asr-whisper-vi-w1-v1`:

> Ngọc Phương Đông, Vinhomes Green Paradise, Cần Giờ, tham quan sa bàn, chính sách bán hàng.

| Binding | Exact value |
| --- | --- |
| Prompt SHA-256 | `6985c297816ea6dc9be2d46b538495704f524ab7ed751f95f9575841c5bd6b48` |
| Canonical profile SHA-256 | `9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1` |
| Model / language | `whisper-1 / vi` |
| Response / timing | `verbose_json / segment + word` |
| Temperature | omitted |

The vocabulary prompt is input context only. WER remains at most 15%, critical-term recall remains
8/8 and asset 02 remains the negative-insertion guard. No fuzzy rescue, transcript correction,
reference rewrite, timestamp relaxation or hidden substitution is introduced.

## Exact assets and rights

| Slot | WAV SHA-256 | Bytes / duration | Reference SHA-256 | RightsRecord canonical SHA-256 |
| --- | --- | --- | --- | --- |
| 1 | `fce31015644960a5f69640d7f5b90a7da078887b15c9d17dc227530d26b875ef` | 5,800,940 / 120.852 s | `585b460291f11f1eb54c2b9a728bca26953ccce98719859e16ab15c7af9ff36e` | `5fb56c9817595693abea89176362e0efebbcab54867788d427e9f4a76d0a8091` |
| 2 | `dce36c5246c17e0385842006dcb0088a8c97a79d3009796815c2564c075cf20b` | 6,460,396 / 134.590667 s | `0bff8c2b403cee452fac00f71b84759988ea515027fda6bd49be76ae382c1fef` | `972dcc752b6bc606a655f272472128a8e6c47fa7858f2bd0cc8e9b9f8c4e4323` |

Owner-approved voice processing remains limited to bounded ASR acceptance. Publishing, training,
resale and any other use remain prohibited. The asset manifest raw SHA-256 remains
`0d7aef962dcb5e34ed5786fadd2e9cfd156cbfb8784d498092262d33b76de7c0`.

## Proposed scope and envelope

| Field | Exact value |
| --- | --- |
| Gate bundle | [V3-01-GATE-RC17-OPENAI-ASR-W1-LINEAGE-A.json](V3-01-GATE-RC17-OPENAI-ASR-W1-LINEAGE-A.json) |
| Raw bundle SHA-256 | `39867efb2a95d22bf5d4be64e041671cf10517a118d02bece010778ab587a76f` |
| Execution-scope SHA-256 | `6b1d5f25684d0b276c06c4b80b5d636f7845a36fdedc24e88adbd5bae7930fc7` |
| Provider-scope SHA-256 | `4d88c5c59c9b5ca9e8c126f0798356eb6ef82a8db2fe16045434af1d69048349` |
| Budget SHA-256 | `fc53ff176baa1d0e6428459b47ef39c22a93d7752af69444fa3248eb3d6f680b` |
| Proposed window | `2026-09-12T14:00:00Z` through `2026-09-12T18:00:00Z` (21:00 12 Sep through 01:00 13 Sep ICT) |
| Reservation / window ceiling | `500 / 1250 VND` |
| Provider / controller timeout | `90 / 120 seconds` |
| Attempts / concurrency / retry / fallback | `1 / 1 / 0 / 0` |

The proposed window is not a schedule or authority. The checked-in defaults keep fixture provider,
empty model and lineage pin, budget zero, external/paid execution false and kill switch engaged.

## Rebound owner gates

- [V3-01-APP-069](approvals/V3-01-APP-069.json): G-01, exact provider/model/capability,
  credential alias, W1 profile, lineage and execution scope.
- [V3-01-APP-070](approvals/V3-01-APP-070.json): G-02, exact 500/1,250 VND, 90/120-second,
  one-attempt and dated lineage scope.
- [V3-01-APP-071](approvals/V3-01-APP-071.json): G-03, exact two WAVs, references,
  RightsRecords, W1 purpose and lineage scope.

These records permit governance review of a future bounded operation. They do not read the alias,
mount the bundle, reserve budget or authorize an API call.

## Historical state and next gate

The RC-16 original W1 lineage is retired. Its Operation 1 remains consumed/failed with HTTP 429
`credit_balance_exhausted` and `REVIEW_REQUIRED`; actual provider cost remains unknown and the
500 VND entry remains only a conservative safety charge. Its Operation 2 remains retired/locked.
No historical ID, receipt or verdict is rewritten.

This package stops at Owner G-08. After an approved merge, exact governance-main CI, dual-CI
provenance, executable-tree equality and unchanged bundle/scope/profile/assets must be verified.
Only then may the owner consider a separate authority for fresh lineage Operation 1. Operation 2
remains locked. Production remains `NO-GO`.
