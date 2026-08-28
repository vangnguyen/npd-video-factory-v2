# Gap register

The canonical, lossless register is [`13_GAP_REGISTER.csv`](13_GAP_REGISTER.csv). This summary is
derived from the audit captured on `2026-08-27`, updated through executable RC-3
`adde8d9c5a7f608db80cbd9d21aecd45f721065e`, governance main
`a73bad37f1f3aa7c2347e6a76503246a46d3c112`, and one failed bounded Vision operation. No
acceptance-axis promotion occurred.

| Severity | Open | In progress | Remediated, gate pending | Total | Production effect |
|---|---:|---:|---:|---:|---|
| P0 | 1 | 8 | 1 | 10 | all unverified P0 work still blocks release-candidate GO |
| P1 | 2 | 3 | 0 | 5 | blocks production hardening/full acceptance |
| P2 | 1 | 0 | 0 | 1 | tracked maintenance risk |
| Total | 4 | 11 | 1 | 16 | default verdict remains NO-GO |

`V3-01-GAP-001` is technically remediated in local/CI and disposable Docker evidence and is merged
through PR #13. V3-01-02 through V3-01-08 are merged through PR #14 through PR #20. GAP-002,
GAP-003, GAP-004, GAP-005, GAP-006, GAP-008, GAP-009, GAP-010, GAP-011, GAP-013 and GAP-016 remain
`IN_PROGRESS`. The bounded G-08 records through PR #24 are exhausted. G-01-A/G-02-A/G-03-A were
consumed only for operation 1; it failed non-retryably without accepted output or a usage receipt.
Operation 2 remains locked, and production remains undeployed and unverified.

## P0 release blockers

| Gap | Short description | Containment |
|---|---|---|
| V3-01-GAP-002 | research/originality/claim-linked script incomplete | measured fixture contract only; no production-ready claim |
| V3-01-GAP-003 | no accepted real ASR/Vision/reframe evidence | one Vision attempt failed before structured output; zero-call schema remediation and a new RC/gate set are required |
| V3-01-GAP-004 | no real stock/AI media/ComfyUI evidence | receipt/decode/relevance fixture contract only; external execution false |
| V3-01-GAP-005 | no accepted Vietnamese voice/music mix | measured fixture audio contract only; eSpeak remains dev/CI |
| V3-01-GAP-006 | no official publish/analytics/Flow C | measured fixture acceptance only; all external actions remain gated |
| V3-01-GAP-007 | no production-like staging or production path | no deployment/route |
| V3-01-GAP-008 | production-like backup/restore/image rollback incomplete | local disposable drill only; no production state touched |
| V3-01-GAP-013 | no accepted real-asset rights coverage | the one RC-3 asset binding held during the failed attempt; broader/final-asset rights remain absent |
| V3-01-GAP-016 | no human full-watch quality acceptance | Flow A/B approval hashes and thresholds enforced; no publish-ready claim |

## P1/P2 work

- `V3-01-GAP-009` (`IN_PROGRESS`): authenticated local operations snapshot, correlation,
  secret-redacted logs, alert previews and retention contracts exist; monitoring backend, accepted
  external alert delivery and the 48-hour locked-RC soak remain.
- `V3-01-GAP-010` (`IN_PROGRESS`): VND budgets, retry/poll/concurrency, circuit breaker, rights hook,
  artifact verification and global cost kill switch pass locally. V3-01-03 adds a PostgreSQL ledger,
  atomic cross-instance reservation, durable circuit/duplicate state, restart recovery and
  retention/health metrics. During operation 1, atomic reservation, one-attempt/no-retry semantics,
  duplicate blocking and circuit state operated as designed. Structured output, actual-cost receipt,
  production-like multi-instance and real-provider acceptance remain.
- `V3-01-GAP-011` (`IN_PROGRESS`): auth rate limiting, URL-import denial and bounded malicious-input
  tests pass. V3-01-03 adds quarantine-before-decoder, archive-signature denial, EICAR contract
  tests, clean-verdict promotion and an internal clamd/WAF design contract; approved internal
  scanner deployment and production public-ingress/WAF evidence remain. Local evidence is
  `EV-V3-MEDIA-SECURITY-001`.
- `V3-01-GAP-012`: GitHub `main` branch protection is disabled.
- `V3-01-GAP-014`: real Agent Hub HTTP bridge acceptance is absent.
- `V3-01-GAP-015`: GitHub Actions runtime deprecation warning.

V3-01-04 adds `EV-V3-FLOW-A-CONTRACT-001`: two distinct redacted fixture runs on one locked commit
pass the measured contract while the real-provider, production-path and human-quality axes remain
`BLOCKED`. It does not close GAP-003, GAP-005 or GAP-016.

V3-01-05 adds `EV-V3-FLOW-B-CONTRACT-001`, and V3-01-06 adds
`EV-V3-FLOW-C-CONTRACT-001`. The Flow C evidence measures provenance, deterministic scoring,
cross-stage hashes, publication safety, nullable analytics, explainable winner scoring and learning
lineage with zero external calls and zero VND spend. It moves GAP-006 to `IN_PROGRESS` only.

V3-01-09 adds `EV-V3-OPENAI-VISION-ADAPTER-001`: exact `gpt-5-mini` request/schema mapping,
bounded image/video frame evidence, request/response/artifact hashes, secret-safe alias resolution,
VND-only cost receipts and central timeout/retry/circuit/duplicate/rights/budget tests pass using
MockTransport. This moves GAP-003 from `OPEN` to `IN_PROGRESS`; ASR, a real Vision call,
production-path evidence and human quality remain absent.

V3-01-10 adds a hash-pinned verified gate loader, exact RC/approval/rights binding, a two-operation
allowlist, exact G-02-A limits, expiry checks and durable restart/atomic-reservation tests. Its one
internally generated RightsRecord was narrowly approved for RC-3 Vision acceptance. Operation 1
was executed once and failed non-retryably; `EV-V3-OPENAI-VISION-OP1-FAILED-001` retains the
secret-free result. The gate/rights/ledger boundaries held, but no structured/provider/usage receipt
was produced. GAP-003, GAP-010 and GAP-013 stay `IN_PROGRESS`; no real-provider axis changes.

No gap is `VERIFIED` or newly closed by V3-01-07 through V3-01-10. `REMEDIATED` means its code and prescribed local/mock
evidence pass on the locked commit; it still needs any applicable
production-path evidence before `VERIFIED`. Owner exceptions must name an expiry and approval record; no implicit
exception exists.
