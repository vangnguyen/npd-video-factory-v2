# V3-01 acceptance matrix

Baseline captured at `2026-08-27T12:02:08Z`; the latest executable acceptance candidate is locked
NO-GO RC-10 `c2b1aec2d54dd90bcb486f8a68c97746b39963aa`. Historical RC-3 operation 1 failed and remains
locked. RC-5 operation 1 later completed provider execution once, but its post-call evidence
serialization failed; it is consumed and permanently `REVIEW_REQUIRED`, and operation 2 is not
approved. V3-01-13 remediates only that serialization path offline. RC-6 operation 1 then stopped
pre-call on an authority-limits contract mismatch with 0 provider calls, 0 VND cost and ledger
`0|0|0|0`; it is not consumed, but the RC-6 authority is retired. V3-01-14 remediates only the
future authority/runner contract offline. RC-7 operation 1 then entered the provider path once and
timed out at about 60 seconds; it is consumed/`REVIEW_REQUIRED`, actual cost is unknown and
operation 2 is locked. V3-01-15 remediates timeout evidence offline. V3-01-16 then splits the
provider HTTP timeout to 90 seconds from the controller hard envelope at 120 seconds and RC-9 bound
that contract, fresh operation IDs and the owner-approved G-02 scope. PR #35 merged the governance
scope, then a separately authorized operation 1 stopped before credential read, reservation, ledger
mutation or provider dispatch because the bootstrap conflated executable-RC CI and governance-main
CI. Operation 1 is not consumed but its authority is retired; operation 2 is locked. V3-01-17 is
merged in RC-10 and exact executable CI passed 5/5. The fresh RC-10 bundle validates offline with
dual-CI roles, but remains unmounted; governance-main CI and operation-1 authority are pending.
These events are fail-closed, not accepted
real-provider output, so no acceptance axis changes. `I/M/R/P/Q` mean
implemented, mock-tested,
real-provider-tested, production-path-tested and quality-accepted. Every PASS cites current-base
static or CI evidence. No status in one axis implies a result in another axis.

The lossless machine-readable register is [02_ACCEPTANCE_MATRIX.csv](02_ACCEPTANCE_MATRIX.csv).

| ID | Capability | I | M | R | P | Q | Evidence | Gaps |
|---|---|---|---|---|---|---|---|---|
| FND-01 | Intake API / project creation | PASS | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001 | GAP-007 |
| FND-02 | Authentication, RBAC, workspace isolation | PASS | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-SEC-001 | GAP-001 |
| FND-03 | Durable job state machine | PASS | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001 | GAP-007 |
| FND-04 | Retry, resume, cancellation, idempotency | PASS | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001 | GAP-007 |
| FND-05 | PostgreSQL metadata persistence | PASS | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001 | GAP-007 |
| FND-06 | Redis queue/recovery semantics | PASS | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001 | GAP-007 |
| FND-07 | Object storage and signed asset access | PASS | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001 | GAP-007 |
| FND-08 | Artifact registry, versioning, hashing | PASS | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001 | GAP-007 |
| FND-09 | Worker orchestration and stage isolation | PASS | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001 | GAP-007 |
| FND-10 | Studio UI / status / recovery | PASS | PASS | N/A | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-SEC-001 | GAP-001; GAP-007 |
| TRD-01 | Permitted trend source adapters | PASS | PASS | NOT_TESTED | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-C-CONTRACT-001 | GAP-006 |
| TRD-02 | Signal normalization and snapshots | PASS | PASS | NOT_TESTED | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-C-CONTRACT-001 | GAP-006 |
| TRD-03 | Trend clustering and lifecycle | PASS | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-C-CONTRACT-001 | GAP-006 |
| TRD-04 | Opportunity scoring and evidence | PASS | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-C-CONTRACT-001 | GAP-006 |
| IDE-01 | Idea generation and scoring | PASS | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001 | GAP-002 |
| IDE-02 | Originality / similarity guard | FAIL | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-FLOW-B-CONTRACT-001 | GAP-002 |
| RES-01 | Research / evidence ledger | FAIL | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-FLOW-B-CONTRACT-001 | GAP-002 |
| SCR-01 | Script generation and versioning | FAIL | FAIL | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-B-CONTRACT-001 | GAP-002 |
| SCR-02 | Storyboard and media plan | PASS | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-B-CONTRACT-001 | GAP-004 |
| UPL-01 | Resumable upload / validation | PASS | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-SEC-002-PARTIAL | GAP-007; GAP-011 |
| ASR-01 | Real transcription provider | FAIL | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-A-CONTRACT-001 | GAP-003 |
| EDT-01 | Scene/shot detection | PASS | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-A-CONTRACT-001 | GAP-003 |
| EDT-02 | Silence detection/removal decisions | PASS | PASS | N/A | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001 | GAP-016 |
| EDT-03 | Highlight detection | PASS | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-A-CONTRACT-001 | GAP-003 |
| VIS-01 | Vision AI structured analysis | PASS | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-A-CONTRACT-001; EV-V3-OPENAI-VISION-ADAPTER-001; EV-V3-VERIFIED-GATE-LOADER-001; EV-V3-OPENAI-VISION-OP1-FAILED-001; EV-V3-RC5-VISION-OP1-REVIEW-001; EV-V3-EVIDENCE-SERIALIZATION-001; EV-V3-RC6-OP1-BLOCKED-001; EV-V3-AUTHORITY-LIMITS-001; EV-V3-RC7-VISION-REBIND-001; EV-V3-RC7-VISION-OP1-TIMEOUT-001; EV-V3-PROVIDER-TIMEOUT-001; EV-V3-SPLIT-TIMEOUT-ENVELOPE-001; EV-V3-RC9-VISION-REBIND-001; EV-V3-RC10-VISION-REBIND-001 | GAP-003 |
| REF-01 | Smart reframe / tracking | PASS | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-A-CONTRACT-001 | GAP-003; GAP-016 |
| BRL-01 | B-roll planning and placement | PASS | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-B-CONTRACT-001 | GAP-004; GAP-013 |
| STK-01 | Licensed stock search/download | FAIL | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-B-CONTRACT-001 | GAP-004; GAP-013 |
| CFY-01 | ComfyUI GPU workflow | FAIL | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-B-CONTRACT-001 | GAP-004 |
| IMG-01 | AI image generation | FAIL | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-B-CONTRACT-001 | GAP-004; GAP-013 |
| VID-01 | AI video generation | FAIL | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-B-CONTRACT-001 | GAP-004; GAP-013 |
| TTS-01 | Production TTS / voice | PASS | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-A-CONTRACT-001; EV-V3-FLOW-B-CONTRACT-001 | GAP-005; GAP-016 |
| SUB-01 | Dynamic Vietnamese subtitles | PASS | PASS | N/A | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-A-CONTRACT-001; EV-V3-FLOW-B-CONTRACT-001 | GAP-016 |
| MUS-01 | Music licence / loop / ducking | PASS | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-B-CONTRACT-001 | GAP-005; GAP-013 |
| SFX-01 | SFX licence and mix | FAIL | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001 | GAP-004; GAP-013 |
| TML-01 | Versioned editable timeline | PASS | PASS | N/A | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001 | GAP-007; GAP-016 |
| PRV-01 | Preview render fidelity | PASS | PASS | N/A | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001 | GAP-016 |
| APR-01 | Human approval state/audit | PASS | PASS | N/A | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-A-CONTRACT-001; EV-V3-FLOW-B-CONTRACT-001 | GAP-016 |
| RND-01 | Final Remotion/FFmpeg render | PASS | PASS | N/A | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001 | GAP-007; GAP-016 |
| QC-01 | Technical video/audio QC | PASS | PASS | N/A | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-A-CONTRACT-001; EV-V3-FLOW-B-CONTRACT-001 | GAP-016 |
| QC-02 | Content/factual/brand/policy QC | FAIL | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-FLOW-B-CONTRACT-001 | GAP-002; GAP-013; GAP-016 |
| PUB-01 | Publishing orchestration/idempotency | PASS | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-SAFETY-001; EV-V3-FLOW-C-CONTRACT-001 | GAP-006 |
| PUB-02 | YouTube adapter | FAIL | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-C-CONTRACT-001 | GAP-006 |
| PUB-03 | TikTok adapter | FAIL | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-C-CONTRACT-001 | GAP-006 |
| PUB-04 | Meta / Instagram / Facebook adapter | FAIL | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-C-CONTRACT-001 | GAP-006 |
| ANA-01 | Analytics from real publication | FAIL | PASS | NOT_TESTED | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-C-CONTRACT-001 | GAP-006 |
| ANA-02 | Metric normalization/null semantics | PASS | PASS | NOT_TESTED | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-C-CONTRACT-001 | GAP-006 |
| ANA-03 | Analytics freshness/reconciliation | PASS | PASS | NOT_TESTED | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-C-CONTRACT-001 | GAP-006 |
| WIN-01 | Winner detection | PASS | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-C-CONTRACT-001 | GAP-006 |
| LRN-01 | Learning feedback | PASS | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-SAFETY-001; EV-V3-FLOW-C-CONTRACT-001 | GAP-006 |
| OPS-01 | Provider health/retry/circuit breaker | PASS | PASS | NOT_TESTED | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-PROVIDER-SAFETY-001; EV-V3-VERIFIED-GATE-LOADER-001; EV-V3-OPENAI-VISION-OP1-FAILED-001; EV-V3-RC5-VISION-OP1-REVIEW-001; EV-V3-EVIDENCE-SERIALIZATION-001; EV-V3-RC6-OP1-BLOCKED-001; EV-V3-AUTHORITY-LIMITS-001; EV-V3-RC7-VISION-REBIND-001; EV-V3-RC7-VISION-OP1-TIMEOUT-001; EV-V3-PROVIDER-TIMEOUT-001; EV-V3-SPLIT-TIMEOUT-ENVELOPE-001; EV-V3-RC9-VISION-REBIND-001; EV-V3-RC10-VISION-REBIND-001 | GAP-010 |
| OPS-02 | Secret management / least privilege | FAIL | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-SEC-001; EV-V3-SEC-002-PARTIAL | GAP-001; GAP-007; GAP-011 |
| OPS-03 | Cost budgets / kill switch | PASS | PASS | NOT_TESTED | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-PROVIDER-SAFETY-001; EV-V3-FLOW-B-CONTRACT-001; EV-V3-VERIFIED-GATE-LOADER-001; EV-V3-OPENAI-VISION-OP1-FAILED-001; EV-V3-RC5-VISION-OP1-REVIEW-001; EV-V3-RC6-OP1-BLOCKED-001; EV-V3-AUTHORITY-LIMITS-001; EV-V3-RC7-VISION-REBIND-001; EV-V3-RC7-VISION-OP1-TIMEOUT-001; EV-V3-PROVIDER-TIMEOUT-001; EV-V3-SPLIT-TIMEOUT-ENVELOPE-001; EV-V3-RC9-VISION-REBIND-001; EV-V3-RC10-VISION-REBIND-001 | GAP-010 |
| OPS-04 | Rights and provenance ledger | PASS | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-PROVIDER-SAFETY-001; EV-V3-FLOW-B-CONTRACT-001; EV-V3-VERIFIED-GATE-LOADER-001; EV-V3-OPENAI-VISION-OP1-FAILED-001; EV-V3-RC5-VISION-OP1-REVIEW-001 | GAP-013 |
| OPS-05 | Logs/metrics/traces/alerts | PASS | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-DR-OBS-001 | GAP-009 |
| OPS-06 | Backup creation/integrity | PASS | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-DR-001; EV-V3-DR-OBS-001 | GAP-008 |
| OPS-07 | Isolated restore drill | PASS | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-DR-001; EV-V3-DR-OBS-001 | GAP-008 |
| OPS-08 | Release rollback plan | PASS | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-DR-001; EV-V3-DR-OBS-001 | GAP-008 |
| OPS-09 | Audit/evidence retention | PASS | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-DR-OBS-001; EV-V3-RC5-VISION-OP1-REVIEW-001; EV-V3-EVIDENCE-SERIALIZATION-001 | GAP-009; GAP-013 |
| OPS-10 | 48-hour production-like soak | FAIL | NOT_TESTED | NOT_TESTED | NOT_TESTED | N/A | EV-V3-STATIC-001 | GAP-009 |

## Interpretation

- `PASS` under I/M proves only current code and deterministic tests.
- V3-01-01 through V3-01-09 leave the implemented count at `44 PASS / 16 FAIL` and the mock-tested
  count at `54 PASS / 1 FAIL / 5 NOT_TESTED`; they do not change any real-provider,
  production-path or quality axis.
- The consolidated real-provider axis is `36 NOT_TESTED / 24 N/A`; production-path is
  `60 NOT_TESTED`; quality is `36 NOT_TESTED / 24 N/A`.
- All real-provider, production-path and human quality work remains unproven.
- V3-01-09 proves only a disabled OpenAI Vision adapter contract through MockTransport: no key use,
  external request, real image, provider receipt or quality acceptance occurred.
- `N/A` is used only where the master matrix defines an axis as structurally inapplicable; it does
  not remove the need for G-00 scope approval.
- Current decision remains `NO-GO` because P0 gaps and mandatory gates are open.
