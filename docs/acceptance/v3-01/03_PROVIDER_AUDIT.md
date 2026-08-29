# V3-01 provider audit

The historical owner-authorized RC-3 OpenAI Vision operation failed non-retryably and remains
locked. RC-5 operation 1 later executed exactly once: provider execution and the durable
operation/usage/cost ledger succeeded, but post-call evidence serialization failed before the
structured payload and request-level IDs/hashes were retained. It is consumed and permanently
`REVIEW_REQUIRED`, not accepted real-provider evidence. RC-5 operation 2 is permanently locked. No
credential value is present in Git/evidence, and credential presence grants no further authority.

V3-01-02 adds a central fail-closed provider safety contract on code commit
`062959287497a5999999adccb65602b88c04947e`. It is exercised only with deterministic fixtures and
mock callables. Media resolution and OpenAI TTS entry points now consult the global external,
paid, rights, budget and kill-switch state; the checked-in configuration makes real execution
impossible. All real states in the table therefore remain `BLOCKED`.

PR #14 merged that contract at exact main `dee8ac279b9ae5f4f94fbb654efb41bfdaf38ae3`.
V3-01-03 replaces its process-local external-operation accounting with a PostgreSQL-backed ledger
for local/CI validation. This changes durability mechanics only; it does not change any real state,
owner gate or execution permission in the table.

PR #23 merged V3-01-10 at exact `main` `adde8d9c5a7f608db80cbd9d21aecd45f721065e`;
`vf-v3-01-rc3` peels to that commit. Exact-main local regression and CI run `33173094529` passed.
Governance-only PR #24 later merged as `a73bad37f1f3aa7c2347e6a76503246a46d3c112` with exact-main
CI run `33175813324` passing 5/5; executable RC-3 did not change. The adapter remains unaccepted as
real-provider-tested. Exact operation evidence is `EV-V3-OPENAI-VISION-OP1-FAILED-001`.
Evidence-only PR #25 then merged as `2ab6b51d63b86c7e4cc9febe347929d8cc3f2e38`; exact-main CI
run `33182052862` passed 5/5. PR #26 merged V3-01-11 as
`061ca5d03248d6721ef8dc7a53cf4608e7ebe79e`; exact-main CI run `33189441083` passed 5/5 and
`vf-v3-01-rc4` peels to that commit. Audit then confirmed RC-4 still hard-coded the consumed/locked
RC-3 operation IDs. RC-4 is retained as fail-closed blocker evidence and cannot be used for live
acceptance. V3-01-12 merged through PR #27 as
`26adafb2eeed4b4de1169db73a13e50a683e094c`; exact-main CI run `33194523231` passed 5/5 and
`vf-v3-01-rc5` peels to that commit. Fresh RC-5 operation IDs and G-01-A/G-02-A/G-03-A hashes are
recorded in a governance bundle. PR #28 merged that governance-only scope as
`8fa96409b0db6ec6d4dc3c04f6e3aaab2f3201ee`; exact-main CI `33226016184` passed 5/5 and executable
RC-5 remained unchanged. After separate owner authority, operation 1 completed provider execution
with one attempt, zero retry/fallback and actual cost `137.6287 VND`. The runner then called
`model_dump()` on dataclass `ProviderVisionFrame`, so request-level evidence was not written.
PR #29 merged the zero-call V3-01-13 remediation as
`8df74a202dc2160e9358ca4cc9be54d989af2292`; exact-main CI run `33261962445` passed 5/5 and
annotated `vf-v3-01-rc6` peels to that commit. V3-01-13 fixes only future serialization and cannot
repair the historical missing data. Fresh RC-6 operation IDs and G-01-A/G-02-A/G-03-A records are
verified in an unmounted bundle. Neither RC-6 operation is authorized; no new provider call or VND
spend occurred.

| Capability | Current implementation | Current evidence | Real state | Required next gate/test |
|---|---|---|---|---|
| Trend sources | deterministic fixture plus contract-only YouTube/TikTok/Meta/RSS definitions | CI fixture normalization/clustering | `BLOCKED` | G-00/G-01; permitted source and real snapshot |
| ASR | fixture and not-configured contract | mock transcript/word timing | `BLOCKED` | G-01/G-02/G-03; PRO-006 |
| Vision | structured fixture plus fail-closed OpenAI `gpt-5-mini` Responses adapter | RC-3 failed; RC-5 provider execution succeeded once but request-level evidence is incomplete; V3-01-13 canonical serializer passes exact-main in locked RC-6; new gate bundle validates offline | `BLOCKED` | merge the governance-only RC-6 rebind under a new G-08, re-verify exact-main/bundle hashes, then obtain separate RC-6 operation-1 authority; PRO-001 |
| Stock | provider protocol and synthetic fixture | rights rejection/ranking tests | `BLOCKED` | G-01/G-02/G-03; PRO-005 |
| AI image | contract/fixture media resolver | mock artifact/provenance tests | `BLOCKED` | G-01/G-02/G-03; PRO-003 |
| AI video | contract/fixture media resolver | mock artifact/provenance tests | `BLOCKED` | G-01/G-02/G-03; PRO-004 |
| ComfyUI | isolated allowlisted bridge; backend disabled | mock queue/result/retry tests | `BLOCKED` | G-04 plus reviewed GPU/workflow/model; PRO-002 |
| TTS | eSpeak dev/CI and OpenAI TTS HTTP adapter | eSpeak E2E plus MockTransport API tests | `BLOCKED` | G-01/G-02/G-03; PRO-007 and human listening |
| Music | project audio asset with rights gate and deterministic mixer | mock licence/mix/QC | `BLOCKED` | G-03; PRO-008 and listening |
| Publishing | dry-run provider and contract-only platform profiles | mock receipts/idempotency | `BLOCKED` | G-04/G-05/G-06; PRO-009 |
| Analytics | deterministic platform fixtures and contract-only official definitions | two fixture snapshots and null semantics | `BLOCKED` | G-01/G-04/G-06; PRO-010 |
| Agent Hub | signed service identity, fixture webhook, HTTP adapter contract | HMAC/replay/rotation/recovery tests | `BLOCKED` for real HTTP | G-04 and exact staging target |

## Provider truth rules

- A fixture/mock PASS remains mock evidence.
- `HTTP 200`, a job ID or an expiring URL is insufficient without downloaded/decoded output.
- Provider/model/workflow, request and artifact hashes, duration, cost and RightsRecord are required.
- External execution remains disabled until explicit gates identify the provider, credential alias,
  target, budget and authorized input rights.
- The authenticated provider-safety snapshot reports durable aggregate operation/attempt/circuit/
  cost metadata only and omits credential aliases, values, payloads and response bodies.
- A returned provider payload is not accepted until its non-empty/size/content-type/SHA-256 checks
  and object-storage receipt consistency pass.
- The ignored local `.env` and GitHub secret names are not authorization and are not evidence that a
  credential is valid.

## Cost and network state

External provider history now contains the failed RC-3 attempt and one successful RC-5 provider
execution, both with zero retry and zero fallback. RC-3 actual cost remains unknown. RC-5 recorded
1,996 input tokens, 2,371 output tokens and `137.6287 VND` actual/charged cost inside a 500 VND
reservation. The RC-5 structured payload/request IDs/hashes were not retained, so cost evidence is
real but the Vision real-provider acceptance axis remains `NOT_TESTED`.

Local evidence `EV-V3-PROVIDER-SAFETY-001` and V3-01-03 locked-commit evidence change
only the implemented/mock-tested state for the control plane. They are not credentials, provider,
production-path or human-quality acceptance. `EV-V3-OPENAI-VISION-ADAPTER-001` changes only the
implemented/mock-tested Vision adapter evidence. `EV-V3-OPENAI-VISION-OP1-FAILED-001` demonstrates
the bounded gate/ledger failure path but does not promote the real-provider axis; GAP-003 remains
`IN_PROGRESS`. Draft evidence `EV-V3-STRUCTURED-ERROR-EVIDENCE-001` proves only the zero-call
V3-01-11 schema/error contract on its code commit and also leaves every real axis unchanged.
`EV-V3-RC5-VISION-OP1-REVIEW-001` records provider success and incomplete evidence without
promotion. `EV-V3-EVIDENCE-SERIALIZATION-001` proves the exact-main V3-01-13 serializer/fallback.
`EV-V3-RC6-VISION-REBIND-001` proves only the offline RC-6 hash/rights/budget binding. No RC-6
operation authority or acceptance-axis promotion follows from either record.
