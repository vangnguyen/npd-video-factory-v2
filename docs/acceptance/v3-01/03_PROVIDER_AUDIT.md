# V3-01 provider audit

No credential value was read and no provider was called. G-01 and G-02 are pending.

| Capability | Current implementation | Current evidence | Real state | Required next gate/test |
|---|---|---|---|---|
| Trend sources | deterministic fixture plus contract-only YouTube/TikTok/Meta/RSS definitions | CI fixture normalization/clustering | `BLOCKED` | G-00/G-01; permitted source and real snapshot |
| ASR | fixture and not-configured contract | mock transcript/word timing | `BLOCKED` | G-01/G-02/G-03; PRO-006 |
| Vision | structured deterministic provider and contract-only live selector | mock frames/OCR/objects/tracks/reframe | `BLOCKED` | G-01/G-02/G-03; PRO-001 |
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
- The ignored local `.env` and GitHub secret names are not authorization and are not evidence that a
  credential is valid.

## Cost and network state

Cost incurred by this baseline/provider audit: `0 VND`. External provider requests: `0`.
