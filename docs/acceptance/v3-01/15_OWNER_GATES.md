# Owner gate register

No gate is approved merely because the owner asked to begin V3. All gates below are `PENDING`; no
approval record has been created. Use `schemas/approval-record.schema.json` for a bounded decision.

| Gate | Decision | Current state | Minimum evidence/decision |
|---|---|---|---|
| G-00 | production acceptance scope and remediation sequence | PENDING — next gate | owner accepts matrix, gaps, environments and review roles |
| G-01 | real-provider credential aliases/scopes | PENDING | provider, capability, least privilege, target/region and expiry |
| G-02 | VND provider budgets and cost controls | PENDING | per-provider ceiling, retry/poll limits and hard stop |
| G-03 | owned inputs, rights and provenance policy | PENDING | source ownership, licensing, consent and retention |
| G-04 | production-like staging execution | PENDING | locked commit/images, isolated topology and rollback plan |
| G-05 | exact final video/caption/thumbnail | PENDING | exact artifact hashes and completed quality report |
| G-06 | one official external publication | PENDING | target, visibility, time, idempotency and takedown plan |
| G-07 | takedown/delete if needed | PENDING | remote ID, reason and impact; otherwise no deletion |
| G-08 | remediation PR merge | PENDING | PR evidence, CI, rollback and explicit merge decision |
| G-09 | deploy locked RC | PENDING | image digest, migrations, backup and rollback |
| G-10 | accept backup/restore/RPO/RTO | PENDING | completed isolated restore report and measured result |
| G-11 | accept final quality | PENDING | artifact-bound full-watch forms and hashes |
| G-12 | sign GO, CONDITIONAL GO or NO-GO | PENDING | final bundle, complete matrix and gap register |

## Approval semantics

An approval must identify the gate, owner, UTC time, commit/RC, environment, bounded scope, evidence
IDs, expiry and decision. Changing commit, artifact, provider, platform target, budget, environment or
time window invalidates or narrows the approval.

The current allowed scope is repository inspection, static/mock testing, redacted evidence creation
and a draft PR. It authorizes no merge, deployment, credential use, paid call, public route,
publishing, analytics collection or production write.
