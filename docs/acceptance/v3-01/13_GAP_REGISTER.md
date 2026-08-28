# Gap register

The canonical, lossless register is [`13_GAP_REGISTER.csv`](13_GAP_REGISTER.csv). This summary is
derived from the audit captured on `2026-08-27`, exact merged `main`
`f3ef5431fcc14289351163057fbffa407f7bd226`, and V3-01-07 local/CI remediation on
`remediation/v3-01-07-dr-observability`.

| Severity | Open | In progress | Remediated, gate pending | Total | Production effect |
|---|---:|---:|---:|---:|---|
| P0 | 2 | 7 | 1 | 10 | all unverified P0 work still blocks release-candidate GO |
| P1 | 2 | 3 | 0 | 5 | blocks production hardening/full acceptance |
| P2 | 1 | 0 | 0 | 1 | tracked maintenance risk |
| Total | 5 | 10 | 1 | 16 | default verdict remains NO-GO |

`V3-01-GAP-001` is technically remediated in local/CI and disposable Docker evidence and is merged
through PR #13. V3-01-02 through V3-01-06 are merged through PR #14 through PR #18. GAP-002,
GAP-004, GAP-005, GAP-006, GAP-008, GAP-009, GAP-010, GAP-011, GAP-013 and GAP-016 remain
`IN_PROGRESS`. All six bounded G-08 approvals are exhausted;
production remains undeployed and unverified.

## P0 release blockers

| Gap | Short description | Containment |
|---|---|---|
| V3-01-GAP-002 | research/originality/claim-linked script incomplete | measured fixture contract only; no production-ready claim |
| V3-01-GAP-003 | no real ASR/Vision/reframe evidence | measured fixture contract only; real execution gated |
| V3-01-GAP-004 | no real stock/AI media/ComfyUI evidence | receipt/decode/relevance fixture contract only; external execution false |
| V3-01-GAP-005 | no accepted Vietnamese voice/music mix | measured fixture audio contract only; eSpeak remains dev/CI |
| V3-01-GAP-006 | no official publish/analytics/Flow C | measured fixture acceptance only; all external actions remain gated |
| V3-01-GAP-007 | no production-like staging or production path | no deployment/route |
| V3-01-GAP-008 | production-like backup/restore/image rollback incomplete | local disposable drill only; no production state touched |
| V3-01-GAP-013 | no accepted real-asset rights coverage | 100% fixture rights/lineage required; unknown real rights hard-block |
| V3-01-GAP-016 | no human full-watch quality acceptance | Flow A/B approval hashes and thresholds enforced; no publish-ready claim |

## P1/P2 work

- `V3-01-GAP-009` (`IN_PROGRESS`): authenticated local operations snapshot, correlation,
  secret-redacted logs, alert previews and retention contracts exist; monitoring backend, accepted
  external alert delivery and the 48-hour locked-RC soak remain.
- `V3-01-GAP-010` (`IN_PROGRESS`): VND budgets, retry/poll/concurrency, circuit breaker, rights hook,
  artifact verification and global cost kill switch pass locally. V3-01-03 adds a PostgreSQL ledger,
  atomic cross-instance reservation, durable circuit/duplicate state, restart recovery and
  retention/health metrics. `EV-V3-DURABLE-SAFETY-001` passes locally; production-like
  multi-instance and real-provider acceptance remain.
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

No gap is `VERIFIED` or newly closed by V3-01-07. `REMEDIATED` means its code and prescribed local/mock
evidence pass on the locked commit; it still needs any applicable
production-path evidence before `VERIFIED`. Owner exceptions must name an expiry and approval record; no implicit
exception exists.
