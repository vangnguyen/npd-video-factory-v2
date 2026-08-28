# Owner gate register

G-00 and ten completed bounded G-08 actions have approval records. V3-01-10 is merged and RC-3 is
locked. G-01-A, G-02-A and G-03-A are rebound to one exact RC-3 execution scope and dated window,
but the bundle is unmounted and none permits a provider call without the separate operation-1
decision. Use `schemas/approval-record.schema.json` for each later decision; no approval is implied
by CI success.

| Gate | Decision | Current state | Minimum evidence/decision |
|---|---|---|---|
| G-00 | production acceptance scope and remediation sequence | APPROVED — `V3-01-APP-001` | local/CI remediation and draft PRs only; no merge/deploy/provider/publish authority |
| G-01 | real-provider credential aliases/scopes | RC-3 REBOUND — `V3-01-APP-014`; no call authority | `openai-vision` / `gpt-5-mini` / `vision` / `secret://openai/codex-video`; operation 1 decision pending |
| G-02 | VND provider budgets and cost controls | RC-3 DATED REBIND — `V3-01-APP-015`; inactive in runtime defaults | 500 VND/operation, 1,250 VND window, two IDs, one image, no retry, concurrency 1, `2026-08-28T14:00:00Z`–`18:00:00Z` |
| G-03 | owned inputs, rights and provenance policy | APPROVED FOR ONE ACCEPTANCE ASSET — `V3-01-APP-016` | exact image/RightsRecord/RC-3/scope hashes; Vision acceptance only; no publishing, training, resale or other use |
| G-04 | production-like staging execution | PENDING | locked commit/images, isolated topology and rollback plan |
| G-05 | exact final video/caption/thumbnail | PENDING | exact artifact hashes and completed quality report |
| G-06 | one official external publication | PENDING | target, visibility, time, idempotency and takedown plan |
| G-07 | takedown/delete if needed | PENDING | remote ID, reason and impact; otherwise no deletion |
| G-08 | remediation PR merge | CONSUMED — `V3-01-APP-002` completed PR #12/#13; `V3-01-APP-003` through `V3-01-APP-010` completed PR #14 through PR #22; `V3-01-APP-013` completed PR #23 | a new explicit G-08 record is required for any later merge |
| G-09 | deploy locked RC | PENDING | image digest, migrations, backup and rollback |
| G-10 | accept backup/restore/RPO/RTO | PENDING | completed isolated restore report and measured result |
| G-11 | accept final quality | PENDING | artifact-bound full-watch forms and hashes |
| G-12 | sign GO, CONDITIONAL GO or NO-GO | PENDING | final bundle, complete matrix and gap register |

## Approval semantics

An approval must identify the gate, owner, UTC time, commit/RC, environment, bounded scope, evidence
IDs, expiry and decision. Changing commit, artifact, provider, platform target, budget, environment or
time window invalidates or narrows the approval.

The current allowed scope is repository inspection, LOCAL/CI validation, redacted evidence and
draft governance PR creation. The exact PR #12/#13 sequence and PR #14/#15/#16/#17/#18/#19/#20/
#22/#23 merges are complete and their G-08 records cannot be reused. G-01-A, G-02-A and G-03-A now
bind one exact RC-3 scope, but the secret-free bundle is not mounted and runtime defaults remain
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
[`V3-01-APP-016`](approvals/V3-01-APP-016.json).
