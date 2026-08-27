# Gap register

The canonical, lossless register is [`13_GAP_REGISTER.csv`](13_GAP_REGISTER.csv). This summary is
derived from the audit captured on `2026-08-27` and the V3-01-01 remediation locked to
`9635fb3ecf5d5fc5ba20aef3486708bad5960b8b`.

| Severity | Open | In progress | Remediated, gate pending | Total | Production effect |
|---|---:|---:|---:|---:|---|
| P0 | 9 | 0 | 1 | 10 | all unverified P0 work still blocks release-candidate GO |
| P1 | 4 | 1 | 0 | 5 | blocks production hardening/full acceptance |
| P2 | 1 | 0 | 0 | 1 | tracked maintenance risk |
| Total | 14 | 1 | 1 | 16 | default verdict remains NO-GO |

`V3-01-GAP-001` is technically remediated in local/CI and disposable Docker evidence, but remains
unmerged, undeployed and unverified on a production path. G-08 is still required before merge.

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
- `V3-01-GAP-010`: provider budgets, usage, circuit breaker and global cost kill switch.
- `V3-01-GAP-011` (`IN_PROGRESS`): auth rate limiting, URL-import denial and bounded malicious-input
  tests pass; malware quarantine, decompression-resource acceptance and production ingress remain.
- `V3-01-GAP-012`: GitHub `main` branch protection is disabled.
- `V3-01-GAP-014`: real Agent Hub HTTP bridge acceptance is absent.
- `V3-01-GAP-015`: GitHub Actions runtime deprecation warning.

No gap is `VERIFIED` or closed by V3-01-01. `REMEDIATED` means its code and prescribed local/mock
evidence pass on the locked commit; it still needs G-08, merge and any applicable production-path
evidence before `VERIFIED`. Owner exceptions must name an expiry and approval record; no implicit
exception exists.
