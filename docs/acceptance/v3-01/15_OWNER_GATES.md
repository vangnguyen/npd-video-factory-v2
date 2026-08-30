# Owner gate register

G-00 and the completed bounded G-08 actions through PR #30 have approval records or recorded owner
decisions. RC-4 remains
evidence of a fail-closed executable-contract blocker. RC-5 operation 1 consumed its exact G-01-A,
G-02-A, G-03-A and separate operation authority; provider execution succeeded but acceptance
evidence is incomplete, so the result is permanently `REVIEW_REQUIRED`. Operation 2 is not
approved. RC-6 is locked; its separately authorized operation 1 stopped pre-call/not consumed on a
limits-contract mismatch, and that authority is retired. Operation 2 is locked. Historical RC-3,
RC-5 and RC-6 authorities grant no further call. Use
`schemas/approval-record.schema.json` for each later decision; no approval is implied by CI success,
an RC tag or the failed attempt.

| Gate | Decision | Current state | Minimum evidence/decision |
|---|---|---|---|
| G-00 | production acceptance scope and remediation sequence | APPROVED — `V3-01-APP-001` | local/CI remediation and draft PRs only; no merge/deploy/provider/publish authority |
| G-01 | real-provider credential aliases/scopes | RC-6 scope rebound by `V3-01-APP-026`; failed-window operation authority retired; credential value remained unread | any future call requires RC-7 rebind and a new separate operation authority |
| G-02 | VND provider budgets and cost controls | RC-6 envelope rebound by `V3-01-APP-027`; no reservation occurred; checked-in runtime budget remains 0 | future RC-7 envelope must enforce distinct per-operation and acceptance-window caps through the canonical contract |
| G-03 | owned inputs, rights and provenance policy | RC-6 asset/RightsRecord rebound by `V3-01-APP-028`; no publishing rights | exact image/RightsRecord hash verified; no training, resale, publishing or other use |
| G-04 | production-like staging execution | PENDING | locked commit/images, isolated topology and rollback plan |
| G-05 | exact final video/caption/thumbnail | PENDING | exact artifact hashes and completed quality report |
| G-06 | one official external publication | PENDING | target, visibility, time, idempotency and takedown plan |
| G-07 | takedown/delete if needed | PENDING | remote ID, reason and impact; otherwise no deletion |
| G-08 | remediation PR merge | CONSUMED through governance-only PR #30; V3-01-14 merge not approved | a new explicit G-08 decision is required before merging V3-01-14 |
| G-09 | deploy locked RC | PENDING | image digest, migrations, backup and rollback |
| G-10 | accept backup/restore/RPO/RTO | PENDING | completed isolated restore report and measured result |
| G-11 | accept final quality | PENDING | artifact-bound full-watch forms and hashes |
| G-12 | sign GO, CONDITIONAL GO or NO-GO | PENDING | final bundle, complete matrix and gap register |

## Approval semantics

An approval must identify the gate, owner, UTC time, commit/RC, environment, bounded scope, evidence
IDs, expiry and decision. Changing commit, artifact, provider, platform target, budget, environment or
time window invalidates or narrows the approval.

The current allowed scope is repository inspection, LOCAL/CI validation, redacted evidence and a
draft source-only V3-01-14 remediation PR. The PR #12/#13 sequence and PR #14/#15/#16/#17/
#18/#19/#20/#22/#23/#24/#25/#26/#27/#28/#29/#30 merges are complete and their G-08 decisions cannot be
reused. RC-3 IDs are locked, RC-4 remains blocker evidence, and RC-5 operation 1 is consumed/
`REVIEW_REQUIRED`; RC-5 operation 2 is locked. RC-6 operation 1 is blocked pre-call/not consumed,
its failed-window authority is retired, and operation 2 is locked. Runtime defaults remain disabled. Current authority includes no
further merge, credential-value read, provider call,
deployment, public route, publishing, analytics collection or production write. Records:
[`V3-01-APP-001`](approvals/V3-01-APP-001.json) and
[`V3-01-APP-002`](approvals/V3-01-APP-002.json),
[`V3-01-APP-003`](approvals/V3-01-APP-003.json), and
[`V3-01-APP-004`](approvals/V3-01-APP-004.json), and
[`V3-01-APP-005`](approvals/V3-01-APP-005.json), and
[`V3-01-APP-006`](approvals/V3-01-APP-006.json), and
[`V3-01-APP-007`](approvals/V3-01-APP-007.json), and
[`V3-01-APP-008`](approvals/V3-01-APP-008.json), and
[`V3-01-APP-009`](approvals/V3-01-APP-009.json),
[`V3-01-APP-010`](approvals/V3-01-APP-010.json),
[`V3-01-APP-011`](approvals/V3-01-APP-011.json), and
[`V3-01-APP-012`](approvals/V3-01-APP-012.json),
[`V3-01-APP-013`](approvals/V3-01-APP-013.json),
[`V3-01-APP-014`](approvals/V3-01-APP-014.json),
[`V3-01-APP-015`](approvals/V3-01-APP-015.json), and
[`V3-01-APP-016`](approvals/V3-01-APP-016.json), and
[`V3-01-APP-017`](approvals/V3-01-APP-017.json), and
[`V3-01-APP-018`](approvals/V3-01-APP-018.json),
[`V3-01-APP-019`](approvals/V3-01-APP-019.json),
[`V3-01-APP-020`](approvals/V3-01-APP-020.json),
[`V3-01-APP-021`](approvals/V3-01-APP-021.json),
[`V3-01-APP-022`](approvals/V3-01-APP-022.json),
[`V3-01-APP-023`](approvals/V3-01-APP-023.json),
[`V3-01-APP-024`](approvals/V3-01-APP-024.json),
[`V3-01-APP-025`](approvals/V3-01-APP-025.json),
[`V3-01-APP-026`](approvals/V3-01-APP-026.json),
[`V3-01-APP-027`](approvals/V3-01-APP-027.json), and
[`V3-01-APP-028`](approvals/V3-01-APP-028.json).
