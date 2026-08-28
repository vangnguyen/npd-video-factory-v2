# V3-01 provider audit

No real provider was called and no credential value is present in Git/evidence. A separate OpenAI
key has been provisioned in the ignored workstation `.env`, but V3-01-09 tests use only an injected
fake resolver and `MockTransport`. G-01, G-02 and G-03 remain pending; credential presence grants
no execution authority.

V3-01-02 adds a central fail-closed provider safety contract on code commit
`062959287497a5999999adccb65602b88c04947e`. It is exercised only with deterministic fixtures and
mock callables. Media resolution and OpenAI TTS entry points now consult the global external,
paid, rights, budget and kill-switch state; the checked-in configuration makes real execution
impossible. All real states in the table therefore remain `BLOCKED`.

PR #14 merged that contract at exact main `dee8ac279b9ae5f4f94fbb654efb41bfdaf38ae3`.
V3-01-03 replaces its process-local external-operation accounting with a PostgreSQL-backed ledger
for local/CI validation. This changes durability mechanics only; it does not change any real state,
owner gate or execution permission in the table.

PR #20 merged V3-01-08 at exact `main` `f42a1709cba6f087369c1636bab9bd06053f7613`;
`vf-v3-01-rc1` peels to that commit. V3-01-09 adds a minimal OpenAI `gpt-5-mini` Vision adapter on
code-only commit `fe4837bfd2ae0436f5fca557eab6101ca4cf5654`. It remains unmerged, disabled,
mock-tested only and requires a new G-08. If merged, RC-2 must be locked before any live test.

| Capability | Current implementation | Current evidence | Real state | Required next gate/test |
|---|---|---|---|---|
| Trend sources | deterministic fixture plus contract-only YouTube/TikTok/Meta/RSS definitions | CI fixture normalization/clustering | `BLOCKED` | G-00/G-01; permitted source and real snapshot |
| ASR | fixture and not-configured contract | mock transcript/word timing | `BLOCKED` | G-01/G-02/G-03; PRO-006 |
| Vision | structured fixture plus fail-closed OpenAI `gpt-5-mini` Responses adapter | strict mock frames/OCR/composition/objects/safe-crop/quality, hashes, timeout/retry/circuit/duplicate/rights/budget and VND receipt | `BLOCKED` | new G-08, RC-2, then separate G-01-A/G-02-A/G-03-A; PRO-001 |
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

Cost incurred by this baseline/provider audit and V3-01-09: `0 VND`. External provider requests:
`0`. MockTransport calls and simulated VND arithmetic are contract tests, not real usage.

Local evidence `EV-V3-PROVIDER-SAFETY-001` and the pending V3-01-03 locked-commit evidence change
only the implemented/mock-tested state for the control plane. They are not credentials, provider,
production-path or human-quality acceptance. `EV-V3-OPENAI-VISION-ADAPTER-001` changes only the
implemented/mock-tested Vision adapter evidence and leaves GAP-003 `IN_PROGRESS`.
