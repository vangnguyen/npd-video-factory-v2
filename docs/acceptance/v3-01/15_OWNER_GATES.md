# Owner gate register

G-00 and five completed bounded G-08 actions have approval records. All G-08 approvals are
consumed; every later merge and every other gate remains `PENDING`. Use
`schemas/approval-record.schema.json` for each later decision; no approval is implied by CI success.

| Gate | Decision | Current state | Minimum evidence/decision |
|---|---|---|---|
| G-00 | production acceptance scope and remediation sequence | APPROVED — `V3-01-APP-001` | local/CI remediation and draft PRs only; no merge/deploy/provider/publish authority |
| G-01 | real-provider credential aliases/scopes | PENDING | provider, capability, least privilege, target/region and expiry |
| G-02 | VND provider budgets and cost controls | PENDING | per-provider ceiling, retry/poll limits and hard stop |
| G-03 | owned inputs, rights and provenance policy | PENDING | source ownership, licensing, consent and retention |
| G-04 | production-like staging execution | PENDING | locked commit/images, isolated topology and rollback plan |
| G-05 | exact final video/caption/thumbnail | PENDING | exact artifact hashes and completed quality report |
| G-06 | one official external publication | PENDING | target, visibility, time, idempotency and takedown plan |
| G-07 | takedown/delete if needed | PENDING | remote ID, reason and impact; otherwise no deletion |
| G-08 | remediation PR merge | CONSUMED — `V3-01-APP-002` completed PR #12 → retest #13 → PR #13; `V3-01-APP-003` completed PR #14; `V3-01-APP-004` completed PR #15; `V3-01-APP-005` completed PR #16; `V3-01-APP-006` completed PR #17 | a new explicit G-08 record is required for V3-01-06 or any later merge |
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
#12/#13 sequence and PR #14/#15/#16/#17 merges authorized by the five G-08 records are complete and cannot be reused. Current authority
includes no further merge, deployment, credential use, paid call, public route, publishing,
analytics collection or production write. Records:
[`V3-01-APP-001`](approvals/V3-01-APP-001.json) and
[`V3-01-APP-002`](approvals/V3-01-APP-002.json),
[`V3-01-APP-003`](approvals/V3-01-APP-003.json), and
[`V3-01-APP-004`](approvals/V3-01-APP-004.json), and
[`V3-01-APP-005`](approvals/V3-01-APP-005.json), and
[`V3-01-APP-006`](approvals/V3-01-APP-006.json).
