# RC-16 OpenAI ASR W1 acceptance gate rebind

## Post-execution status — 2026-09-10

The decision boundary below is the immutable pre-operation proposal. PR #55 later merged it as
governance main `5ba7107ba414893467f5e0236ca8a965bdbb8f91`, and a separate owner decision authorized
Operation 1 only. That operation passed preflight, dispatched once and received HTTP 429
`credit_balance_exhausted`; it is now consumed/failed with acceptance `REVIEW_REQUIRED`.
Operation 2 remains not approved/locked. See
[V3-01-26 quota evidence](63_V3_01_26_RC16_ASR_W1_QUOTA_EVIDENCE.md). Nothing in this historical
proposal authorizes another call.

## Decision boundary

This is a governance/evidence/tests-only proposal after the owner-approved merge of PR #54.
It does not change executable code or runtime configuration. The verified bundle is checked in
but remains disabled and unmounted. G-01/G-02/G-03 records bind the exact W1 scope for review;
they do not authorize a credential read, reservation or operation. The proposed dated window
needs its own governance G-08 review and a later, separate Operation 1 decision.

```text
RC-16: LOCKED / NOT DEPLOYED
Vision real-provider: 2/2 consecutive PASS (standalone authority retired)
ASR real-provider: NOT_TESTED / 0/2 consecutive PASS
Historical RC-15 Operation 1: FAIL / CONSUMED; critical terms 5/8
RC-16 Operation 1: NOT APPROVED / NOT EXECUTED
RC-16 Operation 2: NOT APPROVED / LOCKED / NOT EXECUTED
Bundle mounted: false
Credential reads / provider calls / live reservations / spend: 0 / 0 / 0 VND / 0 VND
Production: NO-GO
```

## Exact executable candidate

| Item | Evidence |
| --- | --- |
| Source remediation | [PR #54](https://github.com/vangnguyen/npd-video-factory-v2/pull/54), V3-01-25 W1 Prompt Profile Remediation |
| Source base | `b9dbb8fd8f1abcbcc920f0df9fb5a343586b7b0e` |
| Approved source head | `f2760e52f98336f17f67fabcf7f93edc94d88b38` |
| Merge / executable RC | `55b22f773dc108f6c51a1b52db825b1caa8e8a51` |
| Annotated tag | `vf-v3-01-rc16` |
| Tag object | `f18659863bc818c307b4679eec8bc3ec8bc5439a` |
| Tag peeled commit | `55b22f773dc108f6c51a1b52db825b1caa8e8a51` |
| Exact source-head CI | [34250208121](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34250208121), completed/success, 5/5 jobs |
| Exact-main / executable-RC CI | [34302351310](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34302351310), completed/success, 5/5 jobs |
| Executable-tree SHA-256 | `5025279241fb0b55e6fa26cc850c82a1fd5e4dc9fc4e15c43f716f50441e6ecd` |
| Source G-08 record | [V3-01-APP-064](approvals/V3-01-APP-064.json) |

Exact-main regression covers Python/API/worker/bridge, Studio, Renderer tests/typecheck/bundle,
migration 0013 upgrade/downgrade/replay, acceptance/Flow A/B/C/DR validation, safety/compose and
Docker deterministic E2E. Local exact-main verification passed 895 Python tests, 14 Studio tests
and 14 Renderer tests. The checks made no provider call and did not resolve a credential.

PR #54 changed the canonical runtime tree from RC-15
`9fab766b285eb2db580032b914eb2ccdf474d18b3958fd218a73a22fb75701e8` to the RC-16 hash above,
so the new tag is required. This governance branch must preserve that RC-16 executable tree.

## Immutable W1 request profile

The [public profile contract](contracts/V3-01-25-W1-PROMPT-PROFILE.v1.json) has raw file
SHA-256 `6f10a3f058a3d30bab690693a820672df62c9e6e9b0e006545cddf3ee61149a6`.
The canonical profile is shared unchanged by both asset slots:

> Ngọc Phương Đông, Vinhomes Green Paradise, Cần Giờ, tham quan sa bàn, chính sách bán hàng.

| Binding | Exact value |
| --- | --- |
| Profile ID | `asr-whisper-vi-w1-v1` |
| Prompt SHA-256 | `6985c297816ea6dc9be2d46b538495704f524ab7ed751f95f9575841c5bd6b48` |
| Canonical full-profile SHA-256 | `9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1` |
| Model / language | `whisper-1 / vi` |
| Response / timing | `verbose_json / segment + word` |
| Temperature | omitted |
| Pinned tokenizer | `tiktoken==0.12.0`; verified local Whisper multilingual ranks |
| Ordinary raw/context tokens | `34 / 33` |

The profile is input vocabulary context only. It is not transcript post-correction and does not
weaken quality acceptance. WER must remain at most 15% and all 8/8 critical terms must match.
There is no fuzzy rescue, synonym/semantic matching, reference rewrite, timestamp rewrite or
hidden substitution. Asset 02 remains the negative-insertion guard: none of the five prompt
phrases occurs in its owner-confirmed reference, so any inserted occurrence fails the W1 guard.
If Operation 1 later passes, Operation 2 must use the same profile and hashes.

## Historical RC-15 remains immutable

RC-15 Operation 1 remains provider-execution `SUCCESS` and durable `SUCCEEDED`, but official
acceptance is `FAIL / CONSUMED`: WER and timestamp validation passed while critical-term recall
was only 5/8. Actual cost remains `326.294996 VND`. Operation 2 is not approved/locked and RC-15
authority, IDs, bundle and window are retired. No receipt, reference transcript or historical
verdict is rewritten by this rebind. ASR consecutive acceptance remains 0/2.

## Fresh RC-16 scope

| Field | Value |
| --- | --- |
| Provider / model | `openai-transcription / whisper-1` |
| Capability / language | `asr / vi` |
| Credential reference | `secret://openai/codex-video` (alias only; no value read) |
| W1 profile | `asr-whisper-vi-w1-v1`; canonical SHA `9c4a7609...76ab1` |
| Slot 1 | `v3-01-rc16-openai-transcription-asr-call-01` |
| Slot 2 | `v3-01-rc16-openai-transcription-asr-call-02` |
| Scope SHA-256 | `c40b2f6a055dcdae7391c997b255c72fd85960899eabb7e7559e0e8ff623c93c` |
| Bundle | [V3-01-GATE-RC16-OPENAI-ASR-W1-A.json](V3-01-GATE-RC16-OPENAI-ASR-W1-A.json) |
| Raw bundle SHA-256 | `2362943a9535a1fbea7f4c45dfd15520635a8eb406b9d4097ece72277bb41a0d` |
| Canonical provider-scope SHA-256 | `4d88c5c59c9b5ca9e8c126f0798356eb6ef82a8db2fe16045434af1d69048349` |
| Canonical budget SHA-256 | `a8193d044551999cc03983f0bed860ac14011cf21c65b03453d7c2bd53c5379e` |

The canonical loader derives both IDs from exact RC tag/provider/capability/slot and binds exact
commit, W1 profile/hash, asset hash, RightsRecord hashes, budget and window. A W0 scope, an RC-15
operation ID, a modified prompt or a mismatched profile hash fails before reservation. Allowlist
membership is not an operation authority.

## Revalidated owner-confirmed inputs

| Slot | WAV SHA-256 | Bytes / duration | Reference SHA-256 | RightsRecord canonical SHA-256 |
| --- | --- | --- | --- | --- |
| 1 | `fce31015644960a5f69640d7f5b90a7da078887b15c9d17dc227530d26b875ef` | 5,800,940 / 120.852 s | `585b460291f11f1eb54c2b9a728bca26953ccce98719859e16ab15c7af9ff36e` | `5fb56c9817595693abea89176362e0efebbcab54867788d427e9f4a76d0a8091` |
| 2 | `dce36c5246c17e0385842006dcb0088a8c97a79d3009796815c2564c075cf20b` | 6,460,396 / 134.590667 s | `0bff8c2b403cee452fac00f71b84759988ea515027fda6bd49be76ae382c1fef` | `972dcc752b6bc606a655f272472128a8e6c47fa7858f2bd0cc8e9b9f8c4e4323` |

Both WAVs remain mono PCM, 24 kHz, at least 90 seconds and below 180 seconds. The owner manifest
remains byte-identical at SHA-256
`0d7aef962dcb5e34ed5786fadd2e9cfd156cbfb8784d498092262d33b76de7c0`.
Both RightsRecords remain approved without expiry and permit only bounded OpenAI ASR acceptance.
Publishing, training, resale and every other use remain prohibited. No asset, reference or rights
file was regenerated or edited.

## Rebind records and proposed window

| Gate | Record | Canonical SHA-256 |
| --- | --- | --- |
| G-01-ASR | [V3-01-APP-065](approvals/V3-01-APP-065.json) | `1d43b0ab7aa16fdba2957415033935fc0533b9f66c11289fd7e308b0389da47f` |
| G-02-ASR | [V3-01-APP-066](approvals/V3-01-APP-066.json) | `4e7264df710d334596a9a9d6fa559922ed3b5007773f8d10d4c15787c642a1aa` |
| G-03-ASR | [V3-01-APP-067](approvals/V3-01-APP-067.json) | `0cb99f777daade871cdad570f0736a0df3e49e46c8bbcd4e32ef347c3b549c03` |

Proposed window: **2026-09-10 14:00–18:00 UTC**, equivalent to **21:00 on 10 September →
01:00 on 11 September 2026 ICT**. It remains within one UTC budget day and four hours. This is
only a reviewable binding: it does not create a scheduler entry, extend prior authority or permit
either operation. Any scope/profile/bundle/window mutation requires another review and rebind.

| Control | Limit |
| --- | --- |
| Per-operation reservation / window ceiling | 500 / 1,250 VND |
| Accounting rate | 162 VND/minute (approved 0.006 USD/minute × fixed 27,000 VND/USD basis) |
| Modeled slot 1 / slot 2 | 326.3004 / 363.3948 VND; total 689.6952 VND; estimates, not receipts |
| Duration / file cap | 180 seconds / 25,000,000 bytes |
| Provider HTTP / controller hard timeout | 90 / 120 seconds |
| Attempts / concurrency / retry / fallback | 1 / 1 / 0 / 0 |

Checked-in selectors remain fixture, model/profile empty, external/paid execution false, budget
0 VND, kill switch engaged and verified gate disabled. Offline disposable reservations in tests
do not touch a live ledger or consume either real operation.

## Offline verification and next gate

Focused RC-16 bundle/profile/rights tests pass 19/19. They verify the raw bundle hash, re-derived
scope, external approval records, exact assets/references/RightsRecords, same W1 profile across
both slots, asset-02 negative control, durable/non-durable parity, fail-closed defaults, stale-ID
rejection, profile tamper rejection and pre-reservation denials. The full governance-branch and
draft-head CI results are recorded separately when available; no result is invented in advance.

The future governance-main commit and its CI do not yet exist. Dual-CI provenance is therefore
`PENDING_POST_MERGE`; the executable-RC CI and this draft PR's head CI cannot substitute for that
later governance-main role.

```text
Draft governance PR -> separate owner G-08 -> merge
-> exact governance-main CI PASS on its exact commit
-> dual-CI provenance + allowlisted diff + executable-tree equality
-> verify unchanged W1 profile/bundle/scope/assets/references/RightsRecords
-> verify bundle unmounted, live budget untouched and both operations absent from live ledger
-> separate owner authority for RC-16 ASR Operation 1
-> full time-bound preflight before any later attempt
```

Stop at this PR's Owner G-08. Do not merge this governance PR, read a credential, reserve live
budget, call a provider, create an automation, authorize Operation 1/2, deploy, publish or expose
public ingress. Production remains **NO-GO**.
