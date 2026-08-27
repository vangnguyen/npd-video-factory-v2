# Gap register

The canonical, lossless register is [`13_GAP_REGISTER.csv`](13_GAP_REGISTER.csv). This summary is
derived from the audit captured on `2026-08-27`.

| Severity | Open count | Production effect |
|---|---:|---|
| P0 | 10 | blocks release candidate GO |
| P1 | 5 | blocks production hardening/full acceptance |
| P2 | 1 | tracked maintenance risk |
| Total | 16 | default verdict remains NO-GO |

## P0 release blockers

| Gap | Short description | Containment |
|---|---|---|
| V3-01-GAP-001 | interactive auth/RBAC/workspace isolation absent | localhost only |
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
- `V3-01-GAP-011`: upload malware/quarantine/rate-limit/SSRF security suite.
- `V3-01-GAP-012`: GitHub `main` branch protection is disabled.
- `V3-01-GAP-014`: real Agent Hub HTTP bridge acceptance is absent.
- `V3-01-GAP-015`: GitHub Actions runtime deprecation warning.

No gap is closed by this baseline PR. A gap moves from `OPEN` to `VERIFIED` only when its remediation
PR, prescribed test plan and artifact-bound evidence all pass on the locked commit. Owner exceptions
must name an expiry and approval record; no implicit exception exists.
