# V3-01 remediation PR plan

Feature freeze remains active. This plan closes only V3-01 production-acceptance gaps; it is not a
V2-12 feature roadmap. Every PR is small, draft-first, rebased on latest `main`, independently
reversible and prohibited from merge/deploy until its owner gate is recorded.

| Order | Proposed PR | Status | Scope | Gaps | Gate before external action |
|---:|---|---|---|---|---|
| 0 | V3-01-00 baseline/evidence | PR #12 merged at `a9dfe87`; G-08 recorded | documents, schemas, matrix, secret-safe harness | establishes register only | completed repository merge; no runtime authority |
| 1 | V3-01-01 identity/ingress safety | PR #13 retargeted/retested 5/5 CI PASS and merged at `9b66d69`; bounded G-08 consumed | user auth, RBAC, workspace isolation, bounded ingress tests | 001 remediated; 011 in progress | completed repository merge; no deploy/public-ingress authority |
| 2 | V3-01-02 provider safety plane | PR #14 merged at `dee8ac2`; `V3-01-APP-003` consumed; exact-main CI 5/5 PASS | provider metadata, VND budgets, usage, bounded retries, circuit breaker, rights hooks and artifact verification | 010 remains in progress; foundations for 003, 004, 005, 013, 014 | no real-call authority; G-01/G-02/G-03 remain pending |
| 3 | V3-01-03 ingress/media security and durable safety state | PR #15 merged at `4779ddc`; `V3-01-APP-004` consumed; exact-main CI 5/5 PASS | quarantine/malware/archive denial, WAF contract, PostgreSQL provider ledger, atomic reservation, durable circuit/recovery/retention metrics | 010 and 011 remain in progress | completed repository merge; no deploy/public-ingress/real-call authority |
| 4 | V3-01-04 Flow A closure | PR #16 merged at `e06ac3c`; `V3-01-APP-005` consumed; exact-main CI 5/5 PASS | ASR/Vision preflight, measured two-run acceptance contract and redacted zero-call evidence; real owned-media execution remains gated | 003 open; 005/016 in progress; 010/011 in progress | completed repository merge; no real-call/deploy/public-ingress authority; G-01 through G-04 and G-11 remain pending |
| 5 | V3-01-05 Flow B closure | PR #17 merged at `e788864`; `V3-01-APP-006` consumed; exact-main CI 5/5 PASS | quantitative research/claim/originality/media/rights/audio/render evaluator and two locked-commit fixture runs; real providers remain blocked | 002, 004, 005, 013, 016 | completed repository merge; no real-call/deploy/public-ingress authority; G-01 through G-04 and G-11 remain pending |
| 6 | V3-01-06 Flow C closure | PR #18 merged at `f3ef543`; `V3-01-APP-007` consumed; exact-head CI PASS and exact-main regression PASS | provenance/cluster/score/hash/rights/platform/idempotency/receipt/analytics/winner/learning evaluator and two locked-commit fixture runs; no official adapter or remote publish | 006 remains in progress | completed repository merge; G-01 through G-06 and G-11 remain separate and pending |
| 7 | V3-01-07 DR/observability | PR #19 merged at `b132e83`; `V3-01-APP-008` consumed; exact-head and exact-main CI 5/5 PASS | guarded disposable restore, PostgreSQL-backed Redis recovery, 9/9 target hashes, authenticated ops snapshot, correlation, alert previews and retention contract | 007 remains open; 008/009 are in progress only | completed repository merge; G-04/G-09 before production-like target; G-10 accepts DR result |
| 8 | V3-01-08 consolidation/RC gate | PR #20 merged at `f42a170`; `V3-01-APP-009` consumed; exact-head CI 5/5 PASS; `vf-v3-01-rc1` locked | conditional acceptance candidate, consolidated matrix/gaps/gates and provider/staging/cost/rights plans; no runtime action | no gap closed; 007/009/016 remain blockers | completed repository merge/tag only; no G-01 onward authority |
| 9 | V3-01-09 OpenAI Vision adapter | PR #22 merged as `5936aa7`; `V3-01-APP-010` consumed; exact-head and exact-main CI 5/5 PASS; `vf-v3-01-rc2` locked | exact `gpt-5-mini` Responses adapter, bounded frame evidence, strict schema, hashes, VND receipt and fail-closed tests; 0 external calls | 003 in progress; 010/013 unchanged | completed repository merge/tag only; G-01-A/G-02-A preparation does not permit a call |
| 10 | V3-01-10 verified acceptance gate loader | PR #23 merged as `adde8d9`; `V3-01-APP-013` consumed; exact-head/exact-main CI 5/5 PASS; `vf-v3-01-rc3` locked | hash-pinned approval/rights bundle, exact RC, two-operation allowlist, atomic VND reservation and expiry; 0 external calls during implementation | 003/010 remain in progress; operation 1 later ended `REVIEW_REQUIRED` without acceptance-axis change | G-01-A/G-02-A/G-03-A and operation-1 authority consumed; old operation 2 locked |
| 11 | V3-01-11 structured output/error evidence | PR #26 merged as `061ca5d`; `V3-01-APP-018` consumed; exact-main CI `33189441083` PASS 5/5; `vf-v3-01-rc4` locked | required-nullable strict schema audit, redacted typed provider errors, durable attempt JSON and migration; 0 remediation calls/0 VND | 003/010 remain in progress; RC-4 audit exposed stale RC-3 operation IDs | completed repository merge/tag only; RC-4 is blocker evidence and is prohibited from live acceptance |
| 12 | V3-01-12 RC-bound operation allowlist | IN PROGRESS on isolated zero-call branch; G-08 pending | derive immutable operation IDs from exact RC/provider/capability/slot and bind commit/tag/model/scope/asset/window; reject stale/tampered/consumed/expired bundles | 003/010 remain in progress; no acceptance axis changes | separate G-08 before merge; then exact-main regression, RC-5, fresh G-01/G-02/G-03 scope and separate operation-1 decision |

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
