# Owner gate register

G-00 and nine completed bounded G-08 actions have approval records. V3-01-09 is merged and RC-2 is
locked. G-01-A and G-02-A authorize preparation only; neither permits a provider call. G-03-A and a
new G-08 for V3-01-10 remain pending. Use `schemas/approval-record.schema.json` for each later
decision; no approval is implied by CI success.

| Gate | Decision | Current state | Minimum evidence/decision |
|---|---|---|---|
| G-00 | production acceptance scope and remediation sequence | APPROVED — `V3-01-APP-001` | local/CI remediation and draft PRs only; no merge/deploy/provider/publish authority |
| G-01 | real-provider credential aliases/scopes | APPROVED FOR RC-2 PREPARATION ONLY — `V3-01-APP-011`; exact RC-3 runtime binding pending | `openai-vision` / `gpt-5-mini` / `vision` / `secret://openai/codex-video`; no call authority |
| G-02 | VND provider budgets and cost controls | APPROVED FOR RC-2 PREPARATION ONLY — `V3-01-APP-012`; exact dated RC-3 runtime binding pending | 500 VND/operation, 1,250 VND window, two IDs, one image, no retry, concurrency 1, maximum four hours and one UTC day |
| G-03 | owned inputs, rights and provenance policy | PENDING — exact candidate `V3-01-RIGHTS-G03A-001` remains `BLOCKED` | owner must approve the exact image/RightsRecord hashes and bind exact RC-3 |
| G-04 | production-like staging execution | PENDING | locked commit/images, isolated topology and rollback plan |
| G-05 | exact final video/caption/thumbnail | PENDING | exact artifact hashes and completed quality report |
| G-06 | one official external publication | PENDING | target, visibility, time, idempotency and takedown plan |
| G-07 | takedown/delete if needed | PENDING | remote ID, reason and impact; otherwise no deletion |
| G-08 | remediation PR merge | CONSUMED — `V3-01-APP-002` completed PR #12/#13; `V3-01-APP-003` through `V3-01-APP-009` completed PR #14 through PR #20; `V3-01-APP-010` completed PR #22 | a new explicit G-08 record is required for V3-01-10 or any later merge |
| G-09 | deploy locked RC | PENDING | image digest, migrations, backup and rollback |
| G-10 | accept backup/restore/RPO/RTO | PENDING | completed isolated restore report and measured result |
| G-11 | accept final quality | PENDING | artifact-bound full-watch forms and hashes |
| G-12 | sign GO, CONDITIONAL GO or NO-GO | PENDING | final bundle, complete matrix and gap register |

## Approval semantics

An approval must identify the gate, owner, UTC time, commit/RC, environment, bounded scope, evidence
IDs, expiry and decision. Changing commit, artifact, provider, platform target, budget, environment or
time window invalidates or narrows the approval.

The current allowed scope is repository inspection, remediation implementation in LOCAL/CI,
static/mock/security testing, redacted evidence creation and draft PR creation. The exact PR
#12/#13 sequence and PR #14/#15/#16/#17/#18/#19/#20/#22 merges authorized by the nine G-08 records
are complete and cannot be reused. G-01-A permits only the named provider/capability and credential
alias to be prepared; G-02-A permits only the bounded envelope to be prepared. Current authority
includes no further merge, credential-value read, provider call, deployment, public route,
publishing, analytics collection or production write. Records:
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
[`V3-01-APP-012`](approvals/V3-01-APP-012.json).
