# V3-01 provider audit

One owner-authorized OpenAI Vision operation was dispatched on exact RC-3 inside the bound window.
It failed non-retryably with `OpenAIVisionResponseError` before structured output or a
provider/usage receipt was available. It is a failed attempt, not accepted real-provider evidence.
No credential value is present in Git/evidence; operation 1 cannot be reused and operation 2 remains
locked. Credential presence grants no further execution authority.

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
run `33182052862` passed 5/5. V3-01-11 is an unmerged zero-call remediation draft that corrects the
strict schema and adds typed redacted error evidence; it grants no new execution authority.

| Capability | Current implementation | Current evidence | Real state | Required next gate/test |
|---|---|---|---|---|
| Trend sources | deterministic fixture plus contract-only YouTube/TikTok/Meta/RSS definitions | CI fixture normalization/clustering | `BLOCKED` | G-00/G-01; permitted source and real snapshot |
| ASR | fixture and not-configured contract | mock transcript/word timing | `BLOCKED` | G-01/G-02/G-03; PRO-006 |
| Vision | structured fixture plus fail-closed OpenAI `gpt-5-mini` Responses adapter | strict mock contract plus one failed, non-retryable live attempt; gate/ledger/rights/duplicate controls held, but no structured/provider/usage receipt exists | `BLOCKED` | zero-call schema/error-evidence remediation, G-08, new RC and newly bound acceptance gates before any later operation; PRO-001 |
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

External provider attempts: `1`, with zero retry and zero fallback. Actual provider billing is
`unknown` because no usage receipt was returned. The durable safety ledger conservatively committed
the reserved `500 VND` as an estimated charge; this must not be represented as actual billed cost.

Local evidence `EV-V3-PROVIDER-SAFETY-001` and V3-01-03 locked-commit evidence change
only the implemented/mock-tested state for the control plane. They are not credentials, provider,
production-path or human-quality acceptance. `EV-V3-OPENAI-VISION-ADAPTER-001` changes only the
implemented/mock-tested Vision adapter evidence. `EV-V3-OPENAI-VISION-OP1-FAILED-001` demonstrates
the bounded gate/ledger failure path but does not promote the real-provider axis; GAP-003 remains
`IN_PROGRESS`. Draft evidence `EV-V3-STRUCTURED-ERROR-EVIDENCE-001` proves only the zero-call
V3-01-11 schema/error contract on its code commit and also leaves every real axis unchanged.
