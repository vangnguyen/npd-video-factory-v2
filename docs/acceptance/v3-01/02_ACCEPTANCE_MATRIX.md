# V3-01 acceptance matrix

Baseline captured at `2026-08-27T12:02:08Z`; V3-01-01 through V3-01-03 are merged and V3-01-04
contract/mock evidence was added on `2026-08-28`. `I/M/R/P/Q` mean implemented, mock-tested,
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
| VIS-01 | Vision AI structured analysis | PASS | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-FLOW-A-CONTRACT-001 | GAP-003 |
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
| OPS-01 | Provider health/retry/circuit breaker | PASS | PASS | NOT_TESTED | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-PROVIDER-SAFETY-001 | GAP-010 |
| OPS-02 | Secret management / least privilege | FAIL | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-SEC-001; EV-V3-SEC-002-PARTIAL | GAP-001; GAP-007; GAP-011 |
| OPS-03 | Cost budgets / kill switch | PASS | PASS | NOT_TESTED | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-PROVIDER-SAFETY-001; EV-V3-FLOW-B-CONTRACT-001 | GAP-010 |
| OPS-04 | Rights and provenance ledger | PASS | PASS | NOT_TESTED | NOT_TESTED | NOT_TESTED | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-PROVIDER-SAFETY-001; EV-V3-FLOW-B-CONTRACT-001 | GAP-013 |
| OPS-05 | Logs/metrics/traces/alerts | FAIL | NOT_TESTED | NOT_TESTED | NOT_TESTED | N/A | EV-V3-STATIC-001 | GAP-009 |
| OPS-06 | Backup creation/integrity | PASS | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-DR-001 | GAP-008 |
| OPS-07 | Isolated restore drill | PASS | NOT_TESTED | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-DR-001 | GAP-008 |
| OPS-08 | Release rollback plan | PASS | PASS | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001; EV-V3-CI-001; EV-V3-DR-001 | GAP-008 |
| OPS-09 | Audit/evidence retention | FAIL | FAIL | N/A | NOT_TESTED | N/A | EV-V3-STATIC-001 | GAP-009; GAP-013 |
| OPS-10 | 48-hour production-like soak | FAIL | NOT_TESTED | NOT_TESTED | NOT_TESTED | N/A | EV-V3-STATIC-001 | GAP-009 |

## Interpretation

- `PASS` under I/M proves only current code and deterministic tests.
- V3-01-01 through V3-01-04 keep the implemented count at `42 PASS / 18 FAIL` and the mock-tested
  count to `51 PASS / 2 FAIL / 7 NOT_TESTED`; they do not change any real-provider,
  production-path or quality axis.
- All real-provider, production-path and human quality work remains unproven.
- `N/A` is used only where the master matrix defines an axis as structurally inapplicable; it does
  not remove the need for G-00 scope approval.
- Current decision remains `NO-GO` because P0 gaps and mandatory gates are open.
