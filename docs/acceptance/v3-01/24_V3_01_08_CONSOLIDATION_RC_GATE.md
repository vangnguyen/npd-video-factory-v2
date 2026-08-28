# V3-01-08 — Consolidation and release-candidate gate

## Decision summary

```text
PRODUCTION VERDICT: NO-GO
RC REVIEW VERDICT: CONDITIONAL-RC FOR CONTROLLED ACCEPTANCE ONLY
RC-1 COMMIT: f42a1709cba6f087369c1636bab9bd06053f7613
RC-1 TAG: vf-v3-01-rc1
RC-1 STATUS: LOCKED FOR CONTROLLED ACCEPTANCE PLANNING ONLY; NOT DEPLOYED
RC IMAGE DIGEST: NOT BUILT OR LOCKED
PRODUCTION-LIKE ENVIRONMENT: NOT AUTHORIZED OR CREATED
REAL PROVIDER EXECUTION: NOT AUTHORIZED
APPROVED REAL-PROVIDER BUDGET: 0 VND
```

The exact `main` commit above contains V3-01-00 through V3-01-08 and is the first locked candidate
for a controlled acceptance sequence. `CONDITIONAL-RC` means only that the repository foundation
may be proposed for an owner-gated, locked acceptance candidate. It is not a production release,
does not satisfy G-09, and does not change the repository production verdict from `NO-GO`.

V3-01-08 adds no product feature. It consolidates the acceptance matrix, gap register, owner-gate
dependencies, future provider/staging plans and current evidence boundaries.

## Exact-main evidence

| Item | Consolidated result |
|---|---|
| PR #20 | merged under `V3-01-APP-009` as `f42a1709cba6f087369c1636bab9bd06053f7613` |
| PR #20 exact-head CI | run `33155313793`; 5/5 PASS |
| Exact-main CI | run `33155981828`; 5/5 PASS on `f42a1709cba6f087369c1636bab9bd06053f7613` |
| RC lock | annotated `vf-v3-01-rc1` peels to exact main `f42a1709cba6f087369c1636bab9bd06053f7613` |
| V3-01-07 exact-head CI | run `33153548402`, 5/5 PASS |
| Local disposable DR | 9/9 recovery hashes, RPO 0 seconds, RTO 33 seconds |
| External calls and cost | 0 calls, 0 VND |
| Runtime action by V3-01-08 | none |
| Main protection | absent; GitHub API returns `Branch not protected` |

CI, mergeability and local DR are repository evidence only. They do not prove a deployed image,
production-like state, real provider, public ingress, remote publication, production analytics,
human quality or a 48-hour soak.

## Consolidated acceptance matrix

The canonical row-level source remains [`02_ACCEPTANCE_MATRIX.csv`](02_ACCEPTANCE_MATRIX.csv).
V3-01-08 changes no matrix axis because it creates no new runtime evidence.

Post-consolidation update: V3-01-09 later merged as RC-2
`5936aa7a9656d728be751d0ee61011fc1a5abc7a`. Its mock-only evidence changes GAP-003 from `OPEN` to
`IN_PROGRESS`, producing a current register of 4 open, 11 in progress and 1 remediated. V3-01-10
is an unmerged gate-loader remediation and does not alter the production verdict or any
real-provider/production-path/quality axis.

| Axis | PASS | FAIL | NOT_TESTED | N/A | Decision |
|---|---:|---:|---:|---:|---|
| Implemented | 44 | 16 | 0 | 0 | incomplete |
| Mock-tested | 54 | 1 | 5 | 0 | strong deterministic foundation, not production evidence |
| Real-provider-tested | 0 | 0 | 36 | 24 | blocked |
| Production-path-tested | 0 | 0 | 60 | 0 | blocked |
| Quality-accepted | 0 | 0 | 36 | 24 | blocked |

The sixteen implemented failures include claim-linked research/originality/script controls, real
ASR and external media adapters, SFX, official publishing adapters, real-publication analytics,
production secret management and the 48-hour soak. The single mock failure is `SCR-01`; five other
mock rows remain `NOT_TESTED`.

## Consolidated gap register

The canonical lossless source remains [`13_GAP_REGISTER.csv`](13_GAP_REGISTER.csv).

| Severity | Open | In progress | Remediated locally | Total | Verified on production path |
|---|---:|---:|---:|---:|---:|
| P0 | 2 | 7 | 1 | 10 | 0 |
| P1 | 2 | 3 | 0 | 5 | 0 |
| P2 | 1 | 0 | 0 | 1 | 0 |
| Total | 5 | 10 | 1 | 16 | 0 |

The P0 release blockers remain:

1. `GAP-002` — claim-linked research, originality and immutable script versioning;
2. `GAP-003` — real ASR, Vision and reframe evidence;
3. `GAP-004` — real stock, AI media and ComfyUI evidence;
4. `GAP-005` — accepted Vietnamese production voice and music mix;
5. `GAP-006` — official publishing, production analytics and real Flow C;
6. `GAP-007` — production-like staging and production path;
7. `GAP-008` — production-like backup, restore and image rollback;
8. `GAP-013` — owner-accepted rights coverage for real assets;
9. `GAP-016` — artifact-bound human full-watch/listen acceptance;
10. `GAP-001` — locally remediated identity/RBAC/isolation, still without production-path proof.

No gap is treated as production verified. `REMEDIATED` means local/CI implementation and prescribed
mock evidence passed; it does not imply real-provider, production-path or quality acceptance.

## Module maturity

| Maturity | Modules |
|---|---|
| Implemented and mock-tested | identity/RBAC/workspace isolation; PostgreSQL/Redis/MinIO state; provider safety ledger; quarantine contracts; Flow A/B/C evaluators; publishing dry-run; analytics fixtures; local DR and read-only observability |
| Contract/mock only | trend sources, ASR, Vision, reframe, stock, AI image/video, ComfyUI, production TTS, music/SFX, platform publishing, official analytics, Agent Hub HTTP bridge |
| Missing or incomplete | claim-linked research ledger, enforceable originality guard, immutable claim-linked script versions, accepted production secret/WAF topology, production monitoring delivery and 48-hour soak |
| Human acceptance absent | Vietnamese voice, music balance, subtitle fidelity, visual relevance, brand/factual QC and complete final-video watch/listen |

## Owner-gate dependency map

No gate below is implied by this document. Each decision must bind the same commit, environment,
provider/account, credential alias, rights scope, VND ceiling, expiry and evidence plan.

| Order | Gate | May authorize | Hard prerequisite | Does not authorize |
|---:|---|---|---|---|
| 1 | G-01 | named least-privilege credential aliases and exact provider capabilities | owner-selected providers/accounts and expiry | calls, spend or deployment |
| 2 | G-02 | VND call/day ceilings and retry/poll limits | G-01 aliases plus dated price source | rights, calls above cap or automatic conversion |
| 3 | G-03 | exact owned/licensed inputs and RightsRecord policy | 100% source/consent/licence coverage | unrelated assets or publication |
| 4 | G-04 | isolated production-like staging target | locked commit/images, backup, rollback, no production customer data | production deployment or public ingress |
| 5 | G-09 | deploy one locked RC to the approved staging target | G-04 topology and immutable image digest | provider calls or publication |
| 6 | G-01/G-02/G-03 scoped execution record | one provider/capability acceptance test at a time | gates 1–5, kill switch procedure and operation ID | another provider or later calls |
| 7 | G-10 | accept measured staging DR/RPO/RTO | isolated backup/failure/restore report | production restore |
| 8 | G-05 | bind exact final video, caption and thumbnail hashes | real Flow A/B evidence and rights coverage | publication |
| 9 | G-06 | approve one official target/time/idempotency/takedown envelope | G-05 package; actual send remains held for G-11 | bulk or second publication |
| 10 | G-11 | accept exact artifact quality after full watch/listen | artifact hashes unchanged | editing or a different output |
| 11 | G-06 execution | one owner-approved official publication | G-05, G-06 and G-11 active on the exact artifact | retries beyond envelope or other channels |
| 12 | G-12 | final GO, CONDITIONAL GO or continued NO-GO | complete evidence bundle, 48-hour soak and resolved/excepted P0s | capability outside signed scope |

## Real-provider acceptance plan

Real-provider acceptance may be requested only after the required gates are recorded. Tests are
serial and fail closed; no all-provider activation is permitted.

1. Lock the candidate commit and image digest; verify all safety flags still disabled.
2. Approve one provider capability, credential alias, owned input, VND ceiling and expiry.
3. Create one immutable operation ID and request hash; reserve its full VND ceiling atomically.
4. Execute one bounded normal case and one bounded failure/recovery case with retries included in
   cost. Stop at the first safety, rights, decode, hash, usage or receipt failure.
5. Download and decode output; record provider/model/workflow, region, duration, usage, VND cost,
   request/output hashes and RightsRecord linkage without storing a credential or sensitive body.
6. Verify restart recovery, circuit state and duplicate-operation denial before the next provider.
7. Re-engage the kill switch and return external/paid execution to false after each test.

Recommended capability order is ASR, Vision, production TTS, licensed stock/media, optional
ComfyUI/AI media, then official platform publishing and analytics. A failure does not authorize an
automatic retry or the next provider.

## Production-like staging plan

This is a plan, not deployment authority:

- isolated hostname/network, separate PostgreSQL, Redis namespace and object bucket;
- synthetic or explicitly owner-approved media only; no production customer data;
- immutable image digests built from the candidate commit and a migration manifest;
- external ingress disabled initially; if later approved, WAF/rate limits and upload scanner must
  be verified before opening the route;
- credential references mounted from an external secret store, never committed or returned by API;
- backup before deploy, restore target separate from source, rollback image retained;
- structured logs, correlation IDs, queue/disk/provider/cost monitoring and secret redaction;
- staged DR drill, one pending-work recovery, no duplicate external action and owner review;
- fresh non-backdated 48-hour soak after the last runtime-semantic change.

Any unexplained restart, data loss, duplicate operation, rights failure, missing cost, invalid
receipt, alert gap or safety-flag drift fails the staging window.

## Cost envelope

The checked-in effective envelope remains fail-closed:

| Capability | Maximum calls | Per-operation limit | Daily limit | Paid execution |
|---|---:|---:|---:|---|
| Every external provider and platform | 0 | 0 VND | 0 VND | false |

G-02-A later approved a preparation-only envelope for two OpenAI Vision operations: 500 VND per
operation, 1,250 VND per acceptance window, no retry, concurrency one and maximum four hours in a
single UTC budget day. That envelope is inactive and grants no call authority. A runtime record
must still bind exact RC-3, dated pricing/window, operation IDs and G-03-A. Failed, moderated,
timed-out and retried calls count toward spend. Missing usage or cost evidence is a test failure.

## Rights and credential plan

- Credentials stay in an external secret store. Only aliases are persisted in configuration,
  evidence and audit records.
- Create a separate least-privilege alias for each provider capability and environment; no shared
  production-wide token and no credential value in Git, Redis, PostgreSQL, logs or API responses.
- G-01 records account/project, capability, scope, region, owner, creation/expiry and revocation
  procedure. Credential presence is never execution authority.
- Every real input and generated output requires a schema-valid RightsRecord with owner/licence/
  consent basis, territory, duration, terms snapshot, hashes, transformation lineage, reviewer,
  retention and revocation state.
- Unknown, expired, revoked, incompatible or incomplete rights hard-block provider submission,
  final render approval and publication.
- The final artifact manifest requires 100% rights coverage; any edit or asset change invalidates
  the prior approval and G-05/G-11 bindings.

## Final checkpoint verdict

`f42a1709cba6f087369c1636bab9bd06053f7613` is locked as **RC-1 for conditional acceptance
planning**, still subject to G-04/G-09 before any deployment. It is **not suitable for production
deployment or real-provider execution now** because ten P0 gaps remain unverified, all 60
production-path rows are `NOT_TESTED`, 36 real-provider rows and 36 quality rows remain
`NOT_TESTED`, and G-01 through G-07 plus G-09 through G-12 are pending.

This section records the historical V3-01-08 checkpoint. PR #22 later merged the missing OpenAI
Vision adapter and RC-2 was locked. G-01-A/G-02-A now cover preparation only. The exact next
decision is G-03-A for the checked-in owned image plus a new G-08 for V3-01-10. If V3-01-10 merges,
run exact-main regression, lock RC-3 and rebind all runtime records before any separate execution
decision.
