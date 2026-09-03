# V3-01 provider audit

The historical owner-authorized RC-3 OpenAI Vision operation failed non-retryably and remains
locked. RC-5 operation 1 later executed exactly once: provider execution and the durable
operation/usage/cost ledger succeeded, but post-call evidence serialization failed before the
structured payload and request-level IDs/hashes were retained. It is consumed and permanently
`REVIEW_REQUIRED`, not accepted real-provider evidence. RC-5 operation 2 is permanently locked. No
credential value is present in Git/evidence, and credential presence grants no further authority.
RC-7 operation 1 later entered the provider path exactly once but timed out at the 60-second
boundary. It is consumed/`REVIEW_REQUIRED`, actual cost is unknown, the 500 VND ledger amount is a
safety charge only, and operation 2 remains locked.

RC-10 operations 1 and 2 later completed successfully on the real OpenAI provider with strict
structured output and complete request/response, usage, VND cost, durable ledger and
secret-containment evidence. Both are consumed/succeeded. They form 2/2 consecutive PASS for the
Vision real-provider-tested axis. PR #39 merged as `fd0db431d2e3786b6b07dcb4b47b7bc74cfa7aed`,
exact-main CI `33703619599` passed 5/5, and the executable and receipt hashes remained unchanged, so
that axis is officially closed. No production-path or quality axis is promoted.

V3-01-02 adds a central fail-closed provider safety contract on code commit
`062959287497a5999999adccb65602b88c04947e`. It is exercised only with deterministic fixtures and
mock callables. Media resolution and OpenAI TTS entry points now consult the global external,
paid, rights, budget and kill-switch state; the checked-in configuration makes real execution
impossible outside a separately verified operation scope. Vision now has accepted bounded
real-provider evidence, while production activation and every other provider remain `BLOCKED`.

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
repair the historical missing data. Fresh RC-6 operation IDs and G-01-A/G-02-A/G-03-A records were
verified in a governance bundle. A separately approved operation 1 stopped before credential read,
reservation, ledger mutation or provider dispatch on an authority-limits contract mismatch. It is
not consumed; its authority is retired, operation 2 is locked, and the result was 0 calls/0 VND.
PR #31 then merged V3-01-14 as
`94170ed42f6ffba4432f29750402eafe0d922a45`; exact-main CI `33321003243` passed 5/5 and
`vf-v3-01-rc7` peels to that commit. PR #32 merged the governance-only scope as
`ebe6f91a9ac88364a23871d587ae4564f30283d3` without changing executable RC-7. After separate owner
authority, operation 1 ran once and ended `PROVIDER_TIMEOUT` at about 60 seconds with no provider
request ID or usage receipt. No retry/fallback occurred. V3-01-15 keeps the 60-second envelope and
adds phase/elapsed/dispatch/exception-chain evidence plus deterministic 59/60/61-second mock tests.
PR #33 merged that remediation as `68d4cf90004054075ebf0f33b9311a3419d8af4d`; exact-main CI
`33412301663` passed 5/5 and `vf-v3-01-rc8` peels to that commit. RC-8 remains NO-GO and is retired
from live acceptance because the provider and controller still shared the same 60-second deadline.
PR #34 merged V3-01-16 as `256bda59eed028ddd642cdb0988c409c489fd655`; exact-main CI
`33449162326` passed 5/5 and `vf-v3-01-rc9` peels to that commit. V3-01-16 separates the provider
HTTP deadline at 90 seconds from the controller hard envelope at 120 seconds, with strict canonical
authority fields and virtual 89/90/91 plus 119/120/121 boundary tests. The owner approved the exact
RC-9 G-02 envelope and directed G-01/G-02/G-03 rebind in an unmounted governance bundle. PR #35
merged that governance-only scope as `e48d7edebcbfb1bd4113c2e40ab4ce46c186f6e4`; governance CI
`33499392585` passed 5/5. A separately authorized operation 1 later stopped before credential read,
reservation, ledger mutation or provider dispatch because the bootstrap tried to represent both
the executable RC CI run `33449162326` and governance main CI run `33499392585` with one field.
Operation 1 is not consumed, but its authority is retired; operation 2 is locked. V3-01-17 validates
both CI roles, commit bindings, allowlisted governance diff and identical executable tree offline.

PR #36 merged V3-01-17 as `c2b1aec2d54dd90bcb486f8a68c97746b39963aa`; exact-main CI run
`33527973264` passed 5/5 and annotated `vf-v3-01-rc10` peels to that commit. The fresh RC-10
operations, 90/120-second timeout envelope, 500/1,250 VND limits, asset/RightsRecord and
G-01-A/G-02-A/G-03-A records validate offline under execution-scope SHA
`a77a2e38d604214dbcaf0933cbdbf6f2fafa6ee258369e1a629ef5b0d55c6cc0`. Governance-only PR #37
merged as `fd78a1690a5a2fd7b07e9e7822deda834f02ea6d`; governance-main CI `33532594395` passed, and
dual-CI provenance verified identical executable trees. After a separate exact operation authority,
operation 1 ran once and completed successfully. Receipt
`EV-V3-RC10-VISION-OP1-PASS-001` retains strict structured output, provider request ID, request and
response hashes, 1,996 input/2,134 output tokens, `125.181420 VND` actual cost, 27,790.325 ms
latency, the durable ledger, closed circuit, duplicate block and secret scan. Evidence-only PR #38
merged as `79b14ded0bbd0cd552420e5964647b6fba16f9b7`; exact-main CI `33650857422` passed 5/5 without
changing the executable tree. A separate Operation 2 authority then produced a second complete PASS:
1,996 input/2,781 output tokens, `159.161860 VND`, 33,284.965 ms, no timeout/retry/fallback and a
distinct response hash. The runner stopped and the bundle was unmounted after each attempt.

| Capability | Current implementation | Current evidence | Real state | Required next gate/test |
|---|---|---|---|---|
| Trend sources | deterministic fixture plus contract-only YouTube/TikTok/Meta/RSS definitions | CI fixture normalization/clustering | `BLOCKED` | G-00/G-01; permitted source and real snapshot |
| ASR | fixture default plus fail-closed OpenAI transcription adapter; model unselected | recorded/mock Vietnamese transcript/segment/word mapping, compatibility matrix and gate rejection tests | implemented/mock-tested `PASS`; real-provider `NOT_TESTED` | new G-08, merge/exact-main/new RC, then model review and separate G-01/G-02/G-03 plus operation authorities; PRO-006 |
| Vision | structured fixture plus fail-closed OpenAI `gpt-5-mini` Responses adapter | RC-10 operations 1 and 2 PASS with complete evidence; one attempt each, no retry/fallback; 2/2 consecutive PASS; PR #39 and exact-main CI complete | real-provider `PASS`; production path and quality remain `BLOCKED` | standalone Vision acceptance closed; no Operation 3; PRO-001 real-provider sub-scope complete |
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

External provider history contains the failed RC-3 attempt, the incomplete-evidence RC-5 success,
the RC-7 timeout and two complete RC-10 successes, all with zero retry and zero fallback. RC-10
recorded 1,996/2,134 and 1,996/2,781 input/output tokens across Operations 1 and 2. Actual costs were
`125.181420 VND` and `159.161860 VND`, totaling `284.343280 VND` or `22.7474624%` of the 1,250 VND
window. Each 500 VND reservation reconciled to zero. Provider IDs, separate response hashes,
structured output and primary evidence were retained for both operations.

Local evidence `EV-V3-PROVIDER-SAFETY-001` and V3-01-03 locked-commit evidence change
only the implemented/mock-tested state for the control plane. They are not credentials, provider,
production-path or human-quality acceptance. `EV-V3-OPENAI-VISION-ADAPTER-001` changes only the
implemented/mock-tested Vision adapter evidence. `EV-V3-OPENAI-VISION-OP1-FAILED-001` demonstrates
the bounded gate/ledger failure path but does not promote the real-provider axis; GAP-003 remains
`IN_PROGRESS`. Draft evidence `EV-V3-STRUCTURED-ERROR-EVIDENCE-001` proves only the zero-call
V3-01-11 schema/error contract on its code commit and also leaves every real axis unchanged.
`EV-V3-RC5-VISION-OP1-REVIEW-001` records provider success and incomplete evidence without
promotion. `EV-V3-EVIDENCE-SERIALIZATION-001` proves the exact-main V3-01-13 serializer/fallback.
`EV-V3-RC6-VISION-REBIND-001` proves only the offline RC-6 hash/rights/budget binding. A later
separate RC-6 operation-1 authority stopped pre-call on `OPERATION_AUTHORITY_LIMITS_MISMATCH` with
0 provider requests, 0 VND and ledger `0|0|0|0`; this is not an OpenAI/provider-path failure and
does not promote an axis. V3-01-14 unifies the future authority/bundle limits contract offline.
`EV-V3-RC7-VISION-REBIND-001` proves the exact RC-7 tag/commit, fresh operation derivation,
approval/rights hashes and both canonical VND limits offline. It does not mount the bundle, authorize
an operation or promote real-provider, production-path or quality acceptance.
`EV-V3-RC7-VISION-OP1-TIMEOUT-001` freezes the later one-attempt timeout as consumed,
`REVIEW_REQUIRED`, actual cost unknown and safety charge 500 VND. `EV-V3-PROVIDER-TIMEOUT-001`
proves only the zero-call V3-01-15 timeout evidence path and no-retry durable behavior; neither
evidence promotes an acceptance axis. `EV-V3-SPLIT-TIMEOUT-ENVELOPE-001` proves only the zero-call,
mock-tested 90/120 split timeout contract. `EV-V3-RC9-VISION-REBIND-001` proves the exact RC-9,
budget, timeout, asset, approval and scope hashes in an unmounted bundle. It grants no operation
authority; provider, production-path and quality evidence remain absent.
`EV-V3-RC10-VISION-REBIND-001` proves the exact RC-10 tag/commit, executable-RC CI, fresh operation
derivation, dual-CI role separation and the offline bundle hashes. `EV-V3-RC10-VISION-OP1-PASS-001`
then proves the first exact owner-authorized operation completed with complete structured, provider,
usage/cost, rights, ledger, duplicate and secret-containment evidence.
`EV-V3-RC10-VISION-CONSECUTIVE-PASS-001` binds the unchanged first receipt to the second exact
owner-authorized PASS and proves the required 2/2 consecutive Vision operations. Both are consumed;
no further Vision operation is required or authorized. PR #39 and exact-main CI `33703619599`
officially close only the Vision real-provider-tested axis. Production-path and human-quality
acceptance remain absent. PR #40 merged the proposed ASR design with an unchanged executable tree.
V3-01-18 evidence `EV-V3-OPENAI-ASR-ADAPTER-001` now proves only the implemented/mock-tested ASR
adapter, canonical gate contract and offline compatibility matrix. Model selection remains
`PROPOSED_NOT_APPROVED`; real-provider, production-path and quality axes remain `NOT_TESTED`. See
[44_V3_01_18_OPENAI_ASR_COMPATIBILITY_ADAPTER.md](44_V3_01_18_OPENAI_ASR_COMPATIBILITY_ADAPTER.md).
It grants no call, credential, budget or model authority.
