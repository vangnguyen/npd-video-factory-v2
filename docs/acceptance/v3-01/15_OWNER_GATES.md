# Owner gate register

G-00 and the completed bounded G-08 actions through PR #26 have approval records. RC-4 is locked
only as evidence of a fail-closed executable-contract blocker; it is not eligible for live
acceptance. G-01-A, G-02-A, G-03-A and the separate RC-3 operation-1 decision were consumed for
exactly one failed, non-retryable attempt. They grant no further provider-call authority. Use
`schemas/approval-record.schema.json` for each later decision; no approval is implied by CI success,
an RC tag or the failed attempt.

| Gate | Decision | Current state | Minimum evidence/decision |
|---|---|---|---|
| G-00 | production acceptance scope and remediation sequence | APPROVED — `V3-01-APP-001` | local/CI remediation and draft PRs only; no merge/deploy/provider/publish authority |
| G-01 | real-provider credential aliases/scopes | RC-3 OPERATION-1 SCOPE CONSUMED — `V3-01-APP-014`; no further call authority | `openai-vision` / `gpt-5-mini` / `vision` / `secret://openai/codex-video`; operation 2 locked |
| G-02 | VND provider budgets and cost controls | RC-3 OPERATION-1 ENVELOPE CONSUMED — `V3-01-APP-015`; runtime defaults inactive | 500 VND reserved/committed as estimated safety charge; actual provider cost unknown; no operation-2 authority |
| G-03 | owned inputs, rights and provenance policy | RC-3 OPERATION-1 USE CONSUMED — `V3-01-APP-016` | exact image/RightsRecord binding held; no publishing, training, resale or reuse outside a newly approved scope |
| G-04 | production-like staging execution | PENDING | locked commit/images, isolated topology and rollback plan |
| G-05 | exact final video/caption/thumbnail | PENDING | exact artifact hashes and completed quality report |
| G-06 | one official external publication | PENDING | target, visibility, time, idempotency and takedown plan |
| G-07 | takedown/delete if needed | PENDING | remote ID, reason and impact; otherwise no deletion |
| G-08 | remediation PR merge | CONSUMED through PR #26 via `V3-01-APP-018`; PR #26 merged V3-01-11 and exact-main regression passed | a new explicit G-08 record is required before merging V3-01-12 |
| G-09 | deploy locked RC | PENDING | image digest, migrations, backup and rollback |
| G-10 | accept backup/restore/RPO/RTO | PENDING | completed isolated restore report and measured result |
| G-11 | accept final quality | PENDING | artifact-bound full-watch forms and hashes |
| G-12 | sign GO, CONDITIONAL GO or NO-GO | PENDING | final bundle, complete matrix and gap register |

## Approval semantics

An approval must identify the gate, owner, UTC time, commit/RC, environment, bounded scope, evidence
IDs, expiry and decision. Changing commit, artifact, provider, platform target, budget, environment or
time window invalidates or narrows the approval.

The current allowed scope is repository inspection, LOCAL/CI validation, redacted evidence and a
draft V3-01-12 remediation PR. The PR #12/#13 sequence and PR #14/#15/#16/#17/#18/#19/#20/#22/
#23/#24/#25/#26 merges are complete and their G-08 records cannot be reused. The RC-3 operation-1
authority has also been consumed; both RC-3 operation IDs are locked, and RC-4 is prohibited from
live acceptance because its executable operation contract is stale. Runtime defaults remain
disabled. Current authority includes no further merge, credential-value read, provider call,
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
[`V3-01-APP-018`](approvals/V3-01-APP-018.json).
