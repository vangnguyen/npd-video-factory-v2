# V3-01 remediation PR plan

Feature freeze remains active. This plan closes only V3-01 production-acceptance gaps; it is not a
V2-12 feature roadmap. Every PR is small, draft-first, rebased on latest `main`, independently
reversible and prohibited from merge/deploy until its owner gate is recorded.

| Order | Proposed PR | Status | Scope | Gaps | Gate before external action |
|---:|---|---|---|---|---|
| 0 | V3-01-00 baseline/evidence | PR #12 merged at `a9dfe87`; G-08 recorded | documents, schemas, matrix, secret-safe harness | establishes register only | completed repository merge; no runtime authority |
| 1 | V3-01-01 identity/ingress safety | PR #13 retargeted/retested 5/5 CI PASS and merged at `9b66d69`; bounded G-08 consumed | user auth, RBAC, workspace isolation, bounded ingress tests | 001 remediated; 011 in progress | completed repository merge; no deploy/public-ingress authority |
| 2 | V3-01-02 provider safety plane | draft PR #14; implemented and locally verified at `0629592` | provider metadata, VND budgets, usage, bounded retries, circuit breaker, rights hooks and artifact verification | 010 in progress; foundations for 003, 004, 005, 013, 014 | G-01/G-02/G-03 before real calls; new G-08 before merge |
| 3 | V3-01-03 Flow A closure | planned; not started | owned media, real ASR/Vision/reframe, upload security and two consecutive runs | 003, 005, 011, 016 | G-03/G-04 before real run; G-08 before merge; G-11 for quality |
| 4 | V3-01-04 Flow B closure | planned; not started | research/claims/originality, real media providers, rights and two consecutive runs | 002, 004, 005, 013, 016 | G-01 through G-04 as applicable; G-08 before merge; G-11 for quality |
| 5 | V3-01-05 Flow C closure | planned; not started | official publish/analytics adapters and one bounded platform acceptance | 006 | G-05/G-06 before publish; G-07 before any takedown; G-08 before merge |
| 6 | V3-01-06 DR/observability | planned; not started | isolated restore/rollback, telemetry, alerts, retention | 007, 008, 009 | G-04 target; G-08 before merge; G-10 accepts DR result |
| 7 | V3-01-07 RC acceptance | planned; not started | lock RC, regression, 48-hour soak, final matrix and verdict; no functional fix | 007, 009, 016 | G-08 before merge; G-09 before deploy; G-10/G-11 acceptance; G-12 verdict |

## Governance prerequisite

The owner should enable `main` branch protection before remediation merges: PR required, Video
Factory V2 CI required, up-to-date branch where practical, failed checks blocked, force pushes and
branch deletion disabled. This audit does not pretend the GitHub setting was applied.

## Merge and deployment rule

CI success is evidence, not authorization. The sequence for every PR is static review, local/mock
tests, draft PR, GitHub CI, human review, explicit owner merge approval, then any separately approved
staging action. Production deploy and publishing remain later distinct gates.

If one PR grows across unrelated boundaries, split it. Do not combine identity, paid-provider calls,
official publishing and DR into one omnibus change.
