# Gap register

The canonical, lossless register is [`13_GAP_REGISTER.csv`](13_GAP_REGISTER.csv). This summary is
derived from the audit captured on `2026-08-27`, exact merged `main`
`dee8ac279b9ae5f4f94fbb654efb41bfdaf38ae3`, and locked V3-01-03 local/CI commit
`0f0854466655d2f36cfa8b57785000097b220c4c`.

| Severity | Open | In progress | Remediated, gate pending | Total | Production effect |
|---|---:|---:|---:|---:|---|
| P0 | 9 | 0 | 1 | 10 | all unverified P0 work still blocks release-candidate GO |
| P1 | 3 | 2 | 0 | 5 | blocks production hardening/full acceptance |
| P2 | 1 | 0 | 0 | 1 | tracked maintenance risk |
| Total | 13 | 2 | 1 | 16 | default verdict remains NO-GO |

`V3-01-GAP-001` is technically remediated in local/CI and disposable Docker evidence and is merged
through PR #13. V3-01-02 is merged through PR #14, while its GAP-010 remains `IN_PROGRESS`.
Both bounded G-08 approvals are exhausted; production remains undeployed and
unverified.

## P0 release blockers

| Gap | Short description | Containment |
|---|---|---|
| V3-01-GAP-002 | research/originality/claim-linked script incomplete | no production-ready claim |
| V3-01-GAP-003 | no real ASR/Vision/reframe evidence | fixtures/contract only |
| V3-01-GAP-004 | no real stock/AI media/ComfyUI evidence | external execution false |
| V3-01-GAP-005 | no accepted Vietnamese voice/music mix | eSpeak dev/CI only |
| V3-01-GAP-006 | no official publish/analytics/Flow C | dry-run only |
| V3-01-GAP-007 | no production-like staging or production path | no deployment/route |
| V3-01-GAP-008 | no backup/restore/rollback drill | no production state touched |
| V3-01-GAP-013 | no accepted real-asset rights coverage | unknown rights hard-block |
| V3-01-GAP-016 | no human full-watch quality acceptance | no publish-ready claim |

## P1/P2 work

- `V3-01-GAP-009`: observability, alerts, retention and 48-hour soak.
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

No gap is `VERIFIED` or newly closed by V3-01-03. `REMEDIATED` means its code and prescribed local/mock
evidence pass on the locked commit; it still needs any applicable
production-path evidence before `VERIFIED`. Owner exceptions must name an expiry and approval record; no implicit
exception exists.
